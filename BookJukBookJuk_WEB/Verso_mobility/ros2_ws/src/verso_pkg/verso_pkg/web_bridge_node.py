"""
web_bridge_node.py

웹(rosbridge) ↔ mission_manager 인터페이스 노드.
JSON 직렬화/역직렬화만 담당하며 상태 로직은 mission_manager에 위임한다.

외부 토픽 (rosbridge를 통해 웹과 통신):
  Subscribe:
    /verso/waypoints — std_msgs/String (JSON)  웹 → 로봇
    /verso/command   — std_msgs/String (JSON)  웹 → 로봇
  Publish:
    /verso/status    — std_msgs/String (JSON)  로봇 → 웹 (1 Hz)
    /verso/event     — std_msgs/String (JSON)  로봇 → 웹 (트리거)
    /verso/path      — std_msgs/String (JSON)  로봇 → 웹 (경로 갱신 시)

내부 토픽 (mission_manager와 통신):
  Publish:
    /verso/internal/waypoints — String (JSON)  웨이포인트 목록
    /verso/internal/command   — String (JSON)  명령
  Subscribe:
    /verso/internal/event     — String (JSON)  이벤트 수신
    /verso/internal/wp_status — String (JSON)  현재 웨이포인트 정보
    /verso/mission/state      — String         현재 상태

위치 정보:
  Subscribe:
    /amcl_pose — geometry_msgs/PoseWithCovarianceStamped
    /cmd_vel   — geometry_msgs/Twist  (is_moving 판단용)

웹 메시지 포맷:
  status  : {"type":"status","position":{"x":...,"y":...,"heading":...},
             "current_waypoint_id":..., "remaining_waypoints":...,
             "mode":..., "is_moving":...}
  event   : {"type":"event","event":..., ...}
"""

from __future__ import annotations

import json
import math

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from std_msgs.msg import String


def _quat_to_yaw(q) -> float:
    """geometry_msgs Quaternion → yaw (rad)."""
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class WebBridgeNode(Node):

    def __init__(self) -> None:
        super().__init__('web_bridge')

        # ── 내부 상태 캐시 ────────────────────────────────────────────────────
        self._pos_x:               float        = 0.0
        self._pos_y:               float        = 0.0
        self._heading:             float        = 0.0
        self._is_moving:           bool         = False
        self._mission_state:       str          = 'GUIDANCE'
        self._current_waypoint_id: str | None   = None
        self._remaining_waypoints: int          = 0

        # ── 내부 Publishers (→ mission_manager) ──────────────────────────────
        self._int_wp_pub  = self.create_publisher(
            String, '/verso/internal/waypoints', 10)
        self._int_cmd_pub = self.create_publisher(
            String, '/verso/internal/command', 10)

        # ── 외부 Publishers (→ 웹) ────────────────────────────────────────────
        self._status_pub = self.create_publisher(String, '/verso/status', 10)
        self._event_pub  = self.create_publisher(String, '/verso/event',  10)
        self._path_pub   = self.create_publisher(String, '/verso/path',   10)

        # ── 외부 Subscribers (웹 →) ───────────────────────────────────────────
        self.create_subscription(
            String, '/verso/waypoints', self._web_waypoints_cb, 10)
        self.create_subscription(
            String, '/verso/command',   self._web_command_cb,   10)

        # ── 내부 Subscribers (← mission_manager) ─────────────────────────────
        self.create_subscription(
            String, '/verso/internal/event',     self._internal_event_cb,  10)
        self.create_subscription(
            String, '/verso/internal/wp_status', self._wp_status_cb,       10)
        self.create_subscription(
            String, '/verso/mission/state',      self._mission_state_cb,   10)

        # ── 위치 / 이동 상태 / 경로 ──────────────────────────────────────────
        self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._amcl_cb, 10)
        self.create_subscription(
            Odometry, '/odom',                       self._odom_cb, 10)
        self.create_subscription(
            Path,     '/plan',                       self._plan_cb, 10)

        # ── 1 Hz status 발행 타이머 ───────────────────────────────────────────
        self.create_timer(1.0, self._publish_status)

        self.get_logger().info("WebBridgeNode ready")

    # ──────────────────────────────────────────────────────────────────────────
    # 외부 수신 (웹 → 내부 전달)
    # ──────────────────────────────────────────────────────────────────────────

    def _web_waypoints_cb(self, msg: String) -> None:
        """웹에서 받은 waypoints JSON 유효성 검사 후 mission_manager로 전달."""
        try:
            data = json.loads(msg.data)
            if data.get('type') != 'waypoints':
                self.get_logger().warn(
                    f"Unexpected waypoints message type: {data.get('type')}")
                return
            # 필수 필드 확인
            for wp in data.get('waypoints', []):
                if not all(k in wp for k in ('id', 'x', 'y')):
                    raise ValueError(f"Waypoint missing required fields: {wp}")
        except (json.JSONDecodeError, ValueError) as e:
            self.get_logger().warn(f"Invalid waypoints from web: {e}")
            return

        self._int_wp_pub.publish(String(data=msg.data))
        self.get_logger().info(
            f"Forwarded {len(data.get('waypoints', []))} waypoints to mission_manager")

    def _web_command_cb(self, msg: String) -> None:
        """웹에서 받은 command JSON 유효성 검사 후 mission_manager로 전달."""
        VALID_ACTIONS = {'stop', 'resume', 'set_mode', 'end_session'}
        VALID_MODES   = {'guidance', 'escort'}

        try:
            data   = json.loads(msg.data)
            action = data.get('action')
            if action not in VALID_ACTIONS:
                raise ValueError(f"Unknown action: {action}")
            if action == 'set_mode' and data.get('mode') not in VALID_MODES:
                raise ValueError(f"Unknown mode: {data.get('mode')}")
            if action == 'end_session':
                if 'x' not in data or 'y' not in data:
                    raise ValueError("end_session requires 'x' and 'y' fields")
                float(data['x'])
                float(data['y'])
        except (json.JSONDecodeError, ValueError) as e:
            self.get_logger().warn(f"Invalid command from web: {e}")
            return

        self._int_cmd_pub.publish(String(data=msg.data))
        self.get_logger().info(f"Forwarded command '{action}' to mission_manager")

    # ──────────────────────────────────────────────────────────────────────────
    # 내부 수신 (mission_manager → 웹 전달)
    # ──────────────────────────────────────────────────────────────────────────

    def _internal_event_cb(self, msg: String) -> None:
        """mission_manager 이벤트 → 웹으로 그대로 전달."""
        self._event_pub.publish(msg)

    def _wp_status_cb(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            self._current_waypoint_id = data.get('current_waypoint_id')
            self._remaining_waypoints = data.get('remaining_waypoints', 0)
        except json.JSONDecodeError:
            pass

    def _mission_state_cb(self, msg: String) -> None:
        self._mission_state = msg.data

    # ──────────────────────────────────────────────────────────────────────────
    # 센서 수신
    # ──────────────────────────────────────────────────────────────────────────

    def _amcl_cb(self, msg: PoseWithCovarianceStamped) -> None:
        p = msg.pose.pose
        self._pos_x   = p.position.x
        self._pos_y   = p.position.y
        self._heading = _quat_to_yaw(p.orientation)

    def _odom_cb(self, msg: Odometry) -> None:
        """실제 이동 여부를 /odom 기반으로 판단 (RC 조작 포함)."""
        self._is_moving = (
            abs(msg.twist.twist.linear.x)  > 0.01 or
            abs(msg.twist.twist.angular.z) > 0.01
        )

    def _plan_cb(self, msg: Path) -> None:
        """Nav2 global path 수신 → 단순화된 JSON으로 웹에 발행."""
        poses = [
            {'x': round(ps.pose.position.x, 3),
             'y': round(ps.pose.position.y, 3)}
            for ps in msg.poses
        ]
        payload = {'type': 'path', 'poses': poses}
        self._path_pub.publish(String(data=json.dumps(payload)))

    # ──────────────────────────────────────────────────────────────────────────
    # 상태 발행 (1 Hz → 웹)
    # ──────────────────────────────────────────────────────────────────────────

    def _state_to_web_mode(self) -> str:
        """내부 상태 → 웹 스펙 mode 문자열 변환."""
        if self._mission_state in ('GUIDANCE', 'STOPPED'):
            return 'guidance'
        return 'escort'  # ESCORT, REPLAN

    def _publish_status(self) -> None:
        payload = {
            'type': 'status',
            'position': {
                'x':       round(self._pos_x, 3),
                'y':       round(self._pos_y, 3),
                'heading': round(self._heading, 4),
            },
            'current_waypoint_id': self._current_waypoint_id,
            'remaining_waypoints': self._remaining_waypoints,
            'mode':                self._state_to_web_mode(),
            'is_moving':           self._is_moving,
        }
        self._status_pub.publish(String(data=json.dumps(payload)))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WebBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
