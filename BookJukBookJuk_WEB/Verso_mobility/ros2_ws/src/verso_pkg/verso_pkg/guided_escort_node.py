"""
guided_escort_node.py

Guided Escort 모드 (B) — Nav2 속도 스케일러

Nav2가 전역 경로(방향/조향)를 제어하고, 사람과의 거리 기반 PD 로 선속도를 스케일링.
사람이 멈추면 로봇도 멈추고, 사람이 걸으면 로봇이 앞서 이동한다.

동작:
  GUIDED_ESCORT 모드에서만 /cmd_vel_robot 발행. 다른 모드에서는 침묵.

속도 제어 로직:
  1. Nav2 → /cmd_vel (조향 방향 사용)
  2. 사람 위치(/verso/person/position) → base_footprint 변환 → 거리 계산
  3. dist_error = target_distance - dist_person
  4. raw_linear = kp * dist_error + kd * d(dist_error)/dt   (escort_controller와 동일)
  5. angular  = nav_cmd.angular.z * (smooth_linear / max_linear_vel)  (비례 스케일링)

사람 LOST 시:
  lost_timeout 이내: 감속 (grace period)
  lost_timeout 초과: 완전 정지

토픽:
  Subscribe:
    /cmd_vel                — Nav2 최종 속도 출력 (방향 정보 사용)
    /verso/person/position  — PointStamped (카메라 프레임)
    /verso/person/status    — String ('TRACKING' | 'LOST')
    /verso/mission/mode     — String ('GUIDANCE'|'ESCORT'|'GUIDED_ESCORT')
  Publish:
    /cmd_vel_robot          — 최종 로봇 속도 명령 (GUIDED_ESCORT 모드에서만)
"""

from __future__ import annotations

import math
import time

import rclpy
import tf2_ros
import tf2_geometry_msgs  # noqa: F401
from geometry_msgs.msg import PointStamped, Twist
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String


SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

MODE_GUIDED_ESCORT = 'GUIDED_ESCORT'


class GuidedEscortNode(Node):

    def __init__(self) -> None:
        super().__init__('guided_escort')

        self._declare_params()
        p = self._get_params()

        self.target_distance: float = p['target_distance']
        self.kp_linear:       float = p['kp_linear']
        self.kd_linear:       float = p['kd_linear']
        self.max_linear_vel:  float = p['max_linear_vel']
        self.lost_timeout:    float = p['lost_timeout']
        self.cmd_rate:        float = p['cmd_rate']
        self.alpha:           float = p['velocity_smoothing_alpha']

        # 상태
        self._nav_cmd:             Twist | None        = None
        self._last_pos:            PointStamped | None = None
        self._status:              str                 = 'LOST'
        self._last_tracking_time:  float               = time.monotonic()
        self._mode:                str                 = ''

        # PD / 스무딩 상태
        self._smooth_linear:   float = 0.0
        self._prev_dist_error: float = 0.0
        self._prev_time:       float = time.monotonic()

        # TF
        self.tf_buffer   = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # ── Subscribers ──────────────────────────────────────────────────────
        self.create_subscription(Twist, '/cmd_vel',
                                 self._nav_cmd_cb, 10)
        self.create_subscription(PointStamped, '/verso/person/position',
                                 self._position_cb, SENSOR_QOS)
        self.create_subscription(String, '/verso/person/status',
                                 self._status_cb, 10)
        self.create_subscription(String, '/verso/mission/mode',
                                 self._mode_cb, 10)

        # ── Publisher ────────────────────────────────────────────────────────
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel_robot', 10)

        # ── 제어 타이머 ──────────────────────────────────────────────────────
        self.create_timer(1.0 / self.cmd_rate, self._control_loop)

        self.get_logger().info(
            f"GuidedEscortNode ready  "
            f"target_dist={self.target_distance}m  rate={self.cmd_rate}Hz"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Parameters
    # ──────────────────────────────────────────────────────────────────────────

    def _declare_params(self) -> None:
        D = ParameterDescriptor
        self.declare_parameter('target_distance',          1.5,
            D(description='사람과의 목표 유지 거리 [m]'))
        self.declare_parameter('kp_linear',                0.5,
            D(description='선속도 P 게인'))
        self.declare_parameter('kd_linear',                0.1,
            D(description='선속도 D 게인'))
        self.declare_parameter('max_linear_vel',           0.5,
            D(description='최대 선속도 [m/s]'))
        self.declare_parameter('lost_timeout',             2.0,
            D(description='추적 소실 후 정지까지 유예 시간 [s]'))
        self.declare_parameter('cmd_rate',                 20.0,
            D(description='제어 루프 주기 [Hz]'))
        self.declare_parameter('velocity_smoothing_alpha', 0.20,
            D(description='속도 저역통과 필터 계수 (0~1)'))

    def _get_params(self) -> dict:
        names = [
            'target_distance', 'kp_linear', 'kd_linear', 'max_linear_vel',
            'lost_timeout', 'cmd_rate', 'velocity_smoothing_alpha',
        ]
        return {n: self.get_parameter(n).value for n in names}

    # ──────────────────────────────────────────────────────────────────────────
    # Subscriber callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def _nav_cmd_cb(self, msg: Twist) -> None:
        self._nav_cmd = msg

    def _position_cb(self, msg: PointStamped) -> None:
        self._last_pos = msg

    def _status_cb(self, msg: String) -> None:
        if msg.data != self._status:
            self.get_logger().info(f"Person status: {self._status} → {msg.data}")
        self._status = msg.data
        if msg.data == 'TRACKING':
            self._last_tracking_time = time.monotonic()

    def _mode_cb(self, msg: String) -> None:
        new_mode = msg.data
        if new_mode != self._mode:
            self.get_logger().info(f"Mode: {self._mode!r} → {new_mode!r}")
            if new_mode != MODE_GUIDED_ESCORT:
                # 모드 이탈 시 상태 초기화 (다음 활성화를 위해)
                self._smooth_linear   = 0.0
                self._prev_dist_error = 0.0
        self._mode = new_mode

    # ──────────────────────────────────────────────────────────────────────────
    # 제어 루프
    # ──────────────────────────────────────────────────────────────────────────

    def _control_loop(self) -> None:
        if self._mode != MODE_GUIDED_ESCORT:
            return  # 침묵

        if self._nav_cmd is None:
            return  # Nav2 아직 미수신

        now = time.monotonic()

        # ── 안전: 추적 소실 ───────────────────────────────────────────────────
        if self._status != 'TRACKING':
            elapsed = now - self._last_tracking_time
            if elapsed >= self.lost_timeout:
                self._publish_zero("Person LOST > timeout")
                return
            # Grace period: 감속
            self._smooth_linear *= 0.85
            self._publish_scaled(self._smooth_linear)
            return

        if self._last_pos is None:
            self._publish_zero("No person position data")
            return

        # ── 사람 거리 계산 ────────────────────────────────────────────────────
        dist_person = self._get_person_distance()
        if dist_person is None:
            # TF 실패 시 카메라 프레임 depth 폴백
            dist_person = self._last_pos.point.z
            if dist_person <= 0.0:
                self._publish_zero("Invalid depth fallback")
                return

        if dist_person < 0.1:
            self._publish_zero("Person too close")
            return

        # ── 선속도 PD (escort_controller와 동일 로직) ─────────────────────────
        dt = now - self._prev_time
        if dt < 1e-4:
            dt = 1e-4

        dist_error    = self.target_distance - dist_person   # + 사람이 목표보다 가까움
        d_dist_error  = (dist_error - self._prev_dist_error) / dt
        raw_linear    = self.kp_linear * dist_error + self.kd_linear * d_dist_error
        raw_linear    = max(0.0, min(raw_linear, self.max_linear_vel))

        self._prev_dist_error = dist_error
        self._prev_time       = now

        # ── 저역통과 필터 ─────────────────────────────────────────────────────
        self._smooth_linear = (self.alpha * raw_linear
                               + (1.0 - self.alpha) * self._smooth_linear)

        self._publish_scaled(self._smooth_linear)

    # ──────────────────────────────────────────────────────────────────────────
    # 발행 헬퍼
    # ──────────────────────────────────────────────────────────────────────────

    def _publish_scaled(self, linear: float) -> None:
        """선속도에 비례해 Nav2 각속도도 스케일링해 발행.

        정지 시(linear=0) 각속도도 0 → 제자리 회전 방지.
        주행 중에는 Nav2 조향 각속도 그대로 사용.
        """
        if self._nav_cmd is None:
            return
        scale   = linear / max(self.max_linear_vel, 1e-3)
        angular = self._nav_cmd.angular.z * scale
        msg = Twist()
        msg.linear.x  = linear
        msg.angular.z = angular
        self.cmd_pub.publish(msg)

    def _publish_zero(self, reason: str = '') -> None:
        if self._smooth_linear != 0.0:
            self.get_logger().info(f"STOP — {reason}", throttle_duration_sec=2.0)
        self._smooth_linear   = 0.0
        self._prev_dist_error = 0.0
        self.cmd_pub.publish(Twist())

    # ──────────────────────────────────────────────────────────────────────────
    # TF 헬퍼
    # ──────────────────────────────────────────────────────────────────────────

    def _get_person_distance(self) -> float | None:
        """사람 PointStamped → base_footprint 변환 후 2D 거리 반환."""
        if self._last_pos is None:
            return None
        try:
            transform = self.tf_buffer.lookup_transform(
                'base_footprint',
                self._last_pos.header.frame_id,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.05),
            )
            transformed = tf2_geometry_msgs.do_transform_point(self._last_pos, transform)
            return math.hypot(transformed.point.x, transformed.point.y)
        except Exception:
            return None


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GuidedEscortNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
