"""
escort_controller_node.py

Escort controller for Scout Mini.
Subscribes to person position (camera frame) and odom, publishes cmd_vel.

Escort semantics
----------------
The robot LEADS the person (robot in FRONT, person follows behind).
The rear RealSense camera sees the person behind the robot.

Control architecture (odom-frame target tracking)
--------------------------------------------------
1. Person position (camera frame) is transformed to odom frame via TF.
2. Target point = person_odom + (robot - person).normalized * target_distance
   → This is the point the robot should occupy: directly in front of person.
3. Bearing error = bearing_to_target - robot_yaw  (odom frame, stable reference)
4. Angular control drives heading_error → 0.
5. Linear control drives dist_error → 0, attenuated during sharp turns.

Why odom frame?
---------------
Camera-frame angular control suffers positive feedback:
  robot turns → camera rotates → person_x shifts → more turning commanded.
In odom frame the person's coordinate is world-stable, so turning the robot
naturally reduces heading_error (negative feedback). ✓

Mecanum-like lateral repositioning
-----------------------------------
When the person turns, the target point moves laterally.
The robot arcs toward the new target (forward + turn simultaneously),
approximating holonomic lateral displacement with differential drive.

Safety
------
  - TF unavailable → fall back to stop angular (linear only)
  - LOST for > lost_timeout → zero Twist (full stop)
  - Grace period decay when SEARCHING

Topics
------
  Subscriptions:
    /verso/person/position   PointStamped  (camera frame)
    /verso/person/velocity   Vector3Stamped
    /verso/person/status     String
    /odom                    Odometry
  Publications:
    /cmd_vel                 Twist
    /verso/escort/debug      String (JSON)
"""

from __future__ import annotations

import json
import math
import time

import numpy as np
import rclpy
import tf2_ros
import tf2_geometry_msgs
from geometry_msgs.msg import PointStamped, Twist, Vector3Stamped
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String


SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


def _yaw_from_quat(q) -> float:
    """Extract yaw from geometry_msgs quaternion."""
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z),
    )


def _wrap_angle(a: float) -> float:
    """Wrap angle to [-π, π]."""
    return math.atan2(math.sin(a), math.cos(a))


class EscortControllerNode(Node):

    def __init__(self) -> None:
        super().__init__('escort_controller_node')

        self._declare_params()
        p = self._get_params()

        # Control gains and limits
        self.target_distance: float = p['target_distance']
        self.kp_linear: float       = p['kp_linear']
        self.kd_linear: float       = p['kd_linear']
        self.kp_angular: float      = p['kp_angular']
        self.max_linear: float      = p['max_linear_vel']
        self.max_angular: float     = p['max_angular_vel']
        self.kd_omega: float         = p['kd_omega']
        self.arc_vel: float          = p['arc_vel']
        self.heading_deadband: float = p['heading_deadband']
        self.lost_timeout: float     = p['lost_timeout']
        self.cmd_rate: float        = p['cmd_rate']
        self.alpha: float           = p['velocity_smoothing_alpha']

        # State
        self._last_pos: PointStamped | None   = None
        self._last_vel: Vector3Stamped | None = None
        self._status: str                     = 'LOST'
        self._last_status_time: float         = time.monotonic()
        self._odom: Odometry | None           = None

        # Smoothed velocity commands
        self._smooth_linear: float  = 0.0
        self._smooth_angular: float = 0.0

        # Derivative term for linear control
        self._prev_dist_error: float = 0.0
        self._prev_time: float       = time.monotonic()

        # ── TF ───────────────────────────────────────────────────────────────
        self.tf_buffer   = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # ── Subscribers ──────────────────────────────────────────────────────
        self.create_subscription(
            PointStamped, '/verso/person/position',
            self._position_cb, SENSOR_QOS)
        self.create_subscription(
            Vector3Stamped, '/verso/person/velocity',
            self._velocity_cb, SENSOR_QOS)
        self.create_subscription(
            String, '/verso/person/status',
            self._status_cb, 10)
        self.create_subscription(
            Odometry, '/odom',
            self._odom_cb, 10)

        # ── Publishers ───────────────────────────────────────────────────────
        self.cmd_pub   = self.create_publisher(Twist,  '/cmd_vel',            10)
        self.debug_pub = self.create_publisher(String, '/verso/escort/debug', 10)

        # ── Control timer ────────────────────────────────────────────────────
        self.create_timer(1.0 / self.cmd_rate, self._control_loop)

        self.get_logger().info(
            f"EscortControllerNode ready  "
            f"target_dist={self.target_distance}m  "
            f"cmd_rate={self.cmd_rate}Hz"
        )

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------

    def _declare_params(self) -> None:
        D = ParameterDescriptor

        self.declare_parameter('target_distance',          1.5,
            D(description='Desired escort distance in front of person (m)'))
        self.declare_parameter('max_linear_vel',           0.5,
            D(description='Maximum forward velocity (m/s)'))
        self.declare_parameter('max_angular_vel',          0.6,
            D(description='Maximum angular velocity (rad/s)'))
        self.declare_parameter('kp_linear',                0.5,
            D(description='Proportional gain for linear velocity'))
        self.declare_parameter('kd_linear',                0.1,
            D(description='Derivative gain for linear velocity'))
        self.declare_parameter('kp_angular',               1.2,
            D(description='Proportional gain for angular velocity (body-frame lateral)'))
        self.declare_parameter('kd_omega',                 0.5,
            D(description='Damping gain on robot angular velocity (suppresses feedback loop)'))
        self.declare_parameter('arc_vel',                  0.25,
            D(description='Minimum forward speed for arc-based lateral correction (m/s)'))
        self.declare_parameter('heading_deadband',         0.08,
            D(description='Lateral angle deadband (rad) — ignore small errors'))
        self.declare_parameter('lost_timeout',             2.0,
            D(description='Stop after this many seconds without target (s)'))
        self.declare_parameter('cmd_rate',                 20.0,
            D(description='Control loop frequency (Hz)'))
        self.declare_parameter('velocity_smoothing_alpha', 0.25,
            D(description='Low-pass filter coefficient (0–1)'))

    def _get_params(self) -> dict:
        names = [
            'target_distance', 'max_linear_vel', 'max_angular_vel',
            'kp_linear', 'kd_linear', 'kp_angular', 'kd_omega', 'heading_deadband',
            'arc_vel', 'lost_timeout', 'cmd_rate', 'velocity_smoothing_alpha',
        ]
        return {n: self.get_parameter(n).value for n in names}

    # ------------------------------------------------------------------
    # Subscriber callbacks
    # ------------------------------------------------------------------

    def _position_cb(self, msg: PointStamped) -> None:
        self._last_pos = msg

    def _velocity_cb(self, msg: Vector3Stamped) -> None:
        self._last_vel = msg

    def _status_cb(self, msg: String) -> None:
        if msg.data != self._status:
            self.get_logger().info(f"Tracking status: {self._status} → {msg.data}")
        self._status = msg.data
        if msg.data == 'TRACKING':
            self._last_status_time = time.monotonic()

    def _odom_cb(self, msg: Odometry) -> None:
        self._odom = msg

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------

    def _control_loop(self) -> None:
        now = time.monotonic()

        # ── Safety: target lost ───────────────────────────────────────────
        if self._status != 'TRACKING':
            elapsed = now - self._last_status_time
            if elapsed >= self.lost_timeout:
                self._publish_stop("Target LOST > timeout")
                return
            # Grace period: decay smoothly
            self._smooth_linear  *= 0.85
            self._smooth_angular *= 0.85
            self._publish_twist(self._smooth_linear, self._smooth_angular)
            return

        if self._last_pos is None or self._odom is None:
            self._publish_stop("No position or odom data")
            return

        # ── Transform person to odom frame ───────────────────────────────
        person_odom = self._transform_to_odom(self._last_pos)
        if person_odom is None:
            # TF not ready: camera-frame fallback (distance only, no angular)
            self._fallback_linear_only()
            return

        # ── Robot state from odom ─────────────────────────────────────────
        rx  = self._odom.pose.pose.position.x
        ry  = self._odom.pose.pose.position.y
        yaw = _yaw_from_quat(self._odom.pose.pose.orientation)

        px = person_odom.point.x
        py = person_odom.point.y

        # ── Person → robot body frame (odom-stable) ──────────────────────
        # odom frame의 사람 위치를 body frame으로 변환
        # person_body_x < 0 : 사람이 로봇 뒤 (정상)
        # person_body_y > 0 : 사람이 로봇 왼쪽
        dx = px - rx
        dy = py - ry
        dist_person = math.hypot(dx, dy)

        if dist_person < 0.05:
            self._publish_stop("Too close to person")
            return

        person_body_x =  math.cos(yaw) * dx + math.sin(yaw) * dy
        person_body_y = -math.sin(yaw) * dx + math.cos(yaw) * dy

        # ── Lateral angle ─────────────────────────────────────────────────
        # 사람이 정후방(body -x)에서 벗어난 각도
        # 왼쪽 양수 → 왼쪽 선회, 오른쪽 음수 → 오른쪽 선회
        safe_rear = max(-person_body_x, 0.3)
        lateral_angle = math.atan2(person_body_y, safe_rear)

        # Deadband: 직진 중 미세 진동 억제
        if abs(lateral_angle) < self.heading_deadband:
            lateral_angle = 0.0

        # ── Angular velocity (body-frame lateral + omega 댐핑) ────────────
        # kd_omega * omega: 로봇 자체 회전이 카메라 측방향 오차를 증폭하는
        # 양성 피드백을 속도 댐핑으로 억제
        omega_robot = self._odom.twist.twist.angular.z
        raw_angular = float(np.clip(
            self.kp_angular * lateral_angle - self.kd_omega * omega_robot,
            -self.max_angular, self.max_angular,
        ))

        # ── Linear velocity ───────────────────────────────────────────────
        dt = now - self._prev_time
        if dt < 1e-4:
            dt = 1e-4

        dist_error = self.target_distance - dist_person  # + when person too close
        d_dist_error = (dist_error - self._prev_dist_error) / dt

        # 거리 기반 PD (사람이 가까우면 가속, 멀면 감속)
        dist_linear = self.kp_linear * dist_error + self.kd_linear * d_dist_error

        # Arc speed: 측방 오차가 있을 때 전진 유지 → 호 운동으로 측방 재배치
        # sin(lateral_angle): 0(직진) → 1(90°), 측방 오차 크면 더 빠른 호
        arc_linear = self.arc_vel * abs(math.sin(lateral_angle))

        # 두 값 중 큰 값 사용 (거리 제어 또는 호 운동 중 우선순위 높은 것)
        raw_linear = float(np.clip(
            max(dist_linear, arc_linear),
            0.0, self.max_linear,
        ))

        self._prev_dist_error = dist_error
        self._prev_time = now

        # ── Low-pass smoothing ────────────────────────────────────────────
        a = self.alpha
        self._smooth_linear  = a * raw_linear  + (1 - a) * self._smooth_linear
        self._smooth_angular = a * raw_angular + (1 - a) * self._smooth_angular

        self._publish_twist(self._smooth_linear, self._smooth_angular)

        # ── Debug ─────────────────────────────────────────────────────────
        debug = {
            'dist_person':   round(dist_person, 3),
            'dist_err':      round(dist_error, 3),
            'lat_angle_deg': round(math.degrees(lateral_angle), 1),
            'omega_robot':   round(omega_robot, 3),
            'hdg_scale':     round(heading_scale, 3),
            'lin_raw':       round(raw_linear, 3),
            'ang_raw':       round(raw_angular, 3),
            'lin_out':       round(self._smooth_linear, 3),
            'ang_out':       round(self._smooth_angular, 3),
        }
        self.debug_pub.publish(String(data=json.dumps(debug)))

    # ------------------------------------------------------------------
    # TF helper
    # ------------------------------------------------------------------

    def _transform_to_odom(self, point: PointStamped) -> PointStamped | None:
        try:
            transform = self.tf_buffer.lookup_transform(
                'odom',
                point.header.frame_id,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.05),
            )
            return tf2_geometry_msgs.do_transform_point(point, transform)
        except Exception as e:
            self.get_logger().warn(
                f"TF lookup failed: {e}", throttle_duration_sec=2.0)
            return None

    def _fallback_linear_only(self) -> None:
        """No TF: use camera-frame depth for distance only, zero angular."""
        if self._last_pos is None:
            self._publish_stop("No position")
            return
        person_z = self._last_pos.point.z
        dist_error = self.target_distance - person_z
        raw = float(np.clip(self.kp_linear * dist_error, 0.0, self.max_linear))
        self._smooth_linear  = self.alpha * raw + (1 - self.alpha) * self._smooth_linear
        self._smooth_angular *= 0.8  # decay angular
        self._publish_twist(self._smooth_linear, self._smooth_angular)

    # ------------------------------------------------------------------
    # Publish helpers
    # ------------------------------------------------------------------

    def _publish_twist(self, linear_x: float, angular_z: float) -> None:
        msg = Twist()
        msg.linear.x  = linear_x
        msg.angular.z = angular_z
        self.cmd_pub.publish(msg)

    def _publish_stop(self, reason: str = '') -> None:
        if self._smooth_linear != 0.0 or self._smooth_angular != 0.0:
            self.get_logger().info(f"STOP — {reason}", throttle_duration_sec=2.0)
        self._smooth_linear  = 0.0
        self._smooth_angular = 0.0
        self._prev_dist_error = 0.0
        self.cmd_pub.publish(Twist())


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EscortControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
