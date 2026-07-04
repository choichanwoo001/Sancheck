"""
mission_manager_node.py

전체 시스템 상태 머신 + Nav2 액션 클라이언트.

상태:
  GUIDANCE — 사람 따라가기 (escort_controller 제어)
  ESCORT   — 웨이포인트 순차 주행 (Nav2 제어)
            사람 소실 시 /speed_limit으로 감속, 재감지 시 정상 속도 복귀
  REPLAN   — 경로 이탈. GUIDANCE 전환 + 즉시 재경로
  STOPPED  — stop 명령 또는 waypoint_arrived 대기. resume/waypoints로 재개

내부 토픽 (web_bridge ↔ mission_manager):
  Subscribe:
    /verso/internal/waypoints — String (JSON) 웨이포인트 목록
    /verso/internal/command   — String (JSON) 명령
    /verso/person/position    — PointStamped
    /verso/person/status      — String
    /plan                     — Path
  Publish:
    /verso/internal/event     — String (JSON) 이벤트 → web_bridge
    /verso/internal/wp_status — String (JSON) 현재 웨이포인트 정보 → web_bridge
    /verso/mission/mode       — String ('GUIDANCE'|'ESCORT') → cmd_vel_mux
    /verso/mission/state      — String (현재 상태, 디버그용)
  Nav2 Action:
    navigate_to_pose
"""

from __future__ import annotations

import json
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

import rclpy
from geometry_msgs.msg import Point, PointStamped, PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Path
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

import tf2_ros
import tf2_geometry_msgs  # noqa: F401  (registers transform functions)


class State:
    GUIDANCE = 'GUIDANCE'
    ESCORT   = 'ESCORT'
    REPLAN   = 'REPLAN'
    STOPPED  = 'STOPPED'


def _escort_mode(is_end_session: bool) -> str:
    """ESCORT 상태에서 cmd_vel_mux에 보낼 모드 결정.

    일반 웨이포인트 주행 → 'GUIDED_ESCORT' (사람 속도 기반 스케일링)
    홈 복귀(end_session)  → 'ESCORT'       (Nav2 직통, 사람 추적 불필요)
    """
    return 'ESCORT' if is_end_session else 'GUIDED_ESCORT'


@dataclass
class Waypoint:
    id:    str
    x:     float
    y:     float
    label: str = ''


class MissionManagerNode(Node):

    def __init__(self) -> None:
        super().__init__('mission_manager')

        self._declare_params()
        p = self._get_params()

        self.deviation_threshold: float = p['deviation_threshold']
        self.replan_cooldown:     float = p['replan_cooldown']

        # ── 상태 ─────────────────────────────────────────────────────────────
        self.state:          str                = State.GUIDANCE
        self._prev_state:    str                = State.GUIDANCE  # STOPPED 복귀용
        self._waypoints:     Deque[Waypoint]    = deque()
        self._current_wp:    Optional[Waypoint] = None
        self.global_path:    Optional[Path]     = None
        self.person_status:  str                = 'LOST'
        self._last_replan:   float              = 0.0
        self._nav_handle                        = None
        self._is_end_session: bool              = False

        # ── TF ───────────────────────────────────────────────────────────────
        self.tf_buffer   = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # ── Nav2 Action Client ────────────────────────────────────────────────
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # ── Subscribers ───────────────────────────────────────────────────────
        self.create_subscription(
            String,       '/verso/internal/waypoints', self._waypoints_cb, 10)
        self.create_subscription(
            String,       '/verso/internal/command',   self._command_cb,   10)
        self.create_subscription(
            PointStamped, '/verso/person/position',    self._person_cb,    10)
        self.create_subscription(
            String,       '/verso/person/status',      self._status_cb,    10)
        self.create_subscription(
            Path,         '/plan',                     self._path_cb,      10)

        # ── Publishers ────────────────────────────────────────────────────────
        self.event_pub     = self.create_publisher(String, '/verso/internal/event',     10)
        self.wp_status_pub = self.create_publisher(String, '/verso/internal/wp_status', 10)
        self.mode_pub      = self.create_publisher(String, '/verso/mission/mode',       10)
        self.state_pub     = self.create_publisher(String, '/verso/mission/state',      10)

        # ── 상태 발행 타이머 ──────────────────────────────────────────────────
        self.create_timer(0.5, self._publish_state)

        self.get_logger().info("MissionManagerNode ready  initial=GUIDANCE")

    # ──────────────────────────────────────────────────────────────────────────
    # Parameters
    # ──────────────────────────────────────────────────────────────────────────

    def _declare_params(self) -> None:
        D = ParameterDescriptor
        self.declare_parameter('deviation_threshold', 2.0,
            D(description='사람이 경로에서 이 거리(m) 이상 벗어나면 이탈로 판정'))
        self.declare_parameter('replan_cooldown', 5.0,
            D(description='연속 재경로 방지 쿨다운 (초)'))

    def _get_params(self) -> dict:
        return {
            'deviation_threshold': self.get_parameter('deviation_threshold').value,
            'replan_cooldown':     self.get_parameter('replan_cooldown').value,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Subscriber callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def _waypoints_cb(self, msg: String) -> None:
        """웨이포인트 목록 수신 → 최근접 이웃 정렬 → ESCORT 모드 전환 + 첫 목적지 주행 시작."""
        try:
            data = json.loads(msg.data)
            wps = [
                Waypoint(id=w['id'], x=float(w['x']), y=float(w['y']),
                         label=w.get('label', ''))
                for w in data.get('waypoints', [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.get_logger().warn(f"Invalid waypoints message: {e}")
            return

        if not wps:
            return

        # 마지막 웨이포인트(계산대 등 고정 종착지)는 정렬에서 제외
        if len(wps) > 1:
            *to_sort, endpoint = wps
            wps = self._sort_nearest_neighbor(to_sort) + [endpoint]
        else:
            wps = self._sort_nearest_neighbor(wps)

        self._waypoints = deque(wps)
        self.get_logger().info(f"Waypoints updated: {len(self._waypoints)} points")

        self._cancel_nav_goal()
        self._transition(State.ESCORT)
        self._send_next_waypoint()

    def _command_cb(self, msg: String) -> None:
        """명령 수신 처리."""
        try:
            data   = json.loads(msg.data)
            action = data.get('action')
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"Invalid command message: {e}")
            return

        if action == 'stop':
            self._handle_stop()
        elif action == 'resume':
            self._handle_resume()
        elif action == 'set_mode':
            self._handle_set_mode(data.get('mode', ''))
        elif action == 'end_session':
            self._handle_end_session(float(data['x']), float(data['y']))
        else:
            self.get_logger().warn(f"Unknown command action: {action}")

    def _person_cb(self, msg: PointStamped) -> None:
        """사람 위치 수신 → ESCORT 상태일 때 이탈 감시."""
        if self.state != State.ESCORT:
            return
        if self.global_path is None:
            return

        person_map = self._transform_to_map(msg)
        if person_map is None:
            return

        dist = self._min_dist_to_path(person_map, self.global_path)
        if dist > self.deviation_threshold:
            now = time.monotonic()
            if now - self._last_replan < self.replan_cooldown:
                return
            self._last_replan = now
            self.get_logger().info(f"Person deviated {dist:.2f}m → REPLAN")
            self._publish_event('route_deviated')
            self._handle_deviation()

    def _status_cb(self, msg: String) -> None:
        """사람 추적 상태 수신 → tracking_lost / tracking_recovered 이벤트."""
        new_status = msg.data
        if new_status != self.person_status:
            if new_status == 'LOST':
                self._publish_event('tracking_lost')
            elif self.person_status == 'LOST':
                self._publish_event('tracking_recovered')
        self.person_status = new_status

    def _path_cb(self, msg: Path) -> None:
        """Nav2 global path 수신. REPLAN 상태에서 새 경로 도착 → ESCORT 복귀."""
        self.global_path = msg
        if self.state == State.REPLAN and len(msg.poses) > 0:
            self.get_logger().info("New path received → ESCORT resumed")
            self._transition(State.ESCORT)

    # ──────────────────────────────────────────────────────────────────────────
    # Command handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_stop(self) -> None:
        if self.state == State.STOPPED:
            return
        self._prev_state = self.state
        self._cancel_nav_goal()
        self._transition(State.STOPPED)

    def _handle_resume(self) -> None:
        if self.state != State.STOPPED:
            return
        if self._prev_state == State.ESCORT:
            if self._current_wp is not None:
                # 중단된 웨이포인트로 재주행
                self._transition(State.ESCORT)
                self._send_nav_goal_pose(self._current_wp.x, self._current_wp.y)
            elif self._waypoints:
                self._transition(State.ESCORT)
                self._send_next_waypoint()
            else:
                self._transition(State.GUIDANCE)
        else:
            self._transition(State.GUIDANCE)

    def _handle_set_mode(self, mode: str) -> None:
        if mode == 'guidance':
            self._cancel_nav_goal()
            self._waypoints.clear()
            self._current_wp    = None
            self._is_end_session = False
            self._transition(State.GUIDANCE)
        elif mode == 'escort':
            if self._waypoints:
                self._cancel_nav_goal()
                self._transition(State.ESCORT)
                self._send_next_waypoint()
            else:
                self.get_logger().warn("set_mode:escort — no waypoints available")
        else:
            self.get_logger().warn(f"Unknown mode: {mode}")

    def _handle_end_session(self, home_x: float, home_y: float) -> None:
        """홈 복귀 후 session_ended / home_reached 이벤트 발행."""
        self._cancel_nav_goal()
        self._waypoints.clear()
        self._current_wp     = None
        self._is_end_session = True
        self._transition(State.ESCORT)
        self._send_nav_goal_pose(home_x, home_y)

    # ──────────────────────────────────────────────────────────────────────────
    # State transitions
    # ──────────────────────────────────────────────────────────────────────────

    def _transition(self, new_state: str) -> None:
        if new_state == self.state:
            return
        self.get_logger().info(f"State: {self.state} → {new_state}")
        self.state = new_state

        # cmd_vel_mux 모드 결정
        # GUIDANCE / REPLAN : escort_controller → collision_monitor → cmd_vel_mux
        # ESCORT (waypoints) : Nav2 + guided_escort_node (사람 속도 스케일)
        # ESCORT (end_session): Nav2 직통
        # STOPPED            : 침묵
        if new_state in (State.GUIDANCE, State.REPLAN):
            self._publish_mode('GUIDANCE')
        elif new_state == State.ESCORT:
            self._publish_mode(_escort_mode(self._is_end_session))
        else:  # STOPPED
            self._publish_mode('ESCORT')

    def _handle_deviation(self) -> None:
        """경로 이탈 처리: GUIDANCE 전환 + 즉시 재경로."""
        self._transition(State.REPLAN)
        self._cancel_nav_goal()
        if self._current_wp is not None:
            self._send_nav_goal_pose(self._current_wp.x, self._current_wp.y)

    # ──────────────────────────────────────────────────────────────────────────
    # Nav2 action
    # ──────────────────────────────────────────────────────────────────────────

    def _send_next_waypoint(self) -> None:
        if not self._waypoints:
            self.get_logger().info("No more waypoints → GUIDANCE")
            self._current_wp = None
            self._transition(State.GUIDANCE)
            return

        self._current_wp = self._waypoints.popleft()
        self.get_logger().info(
            f"Navigating to '{self._current_wp.id}' ({self._current_wp.label})"
            f"  x={self._current_wp.x:.2f} y={self._current_wp.y:.2f}"
            f"  remaining={len(self._waypoints)}")
        self._publish_wp_status()
        self._send_nav_goal_pose(self._current_wp.x, self._current_wp.y)

    def _send_nav_goal_pose(self, x: float, y: float) -> None:
        pose = PoseStamped()
        pose.header.frame_id    = 'map'
        pose.header.stamp       = self.get_clock().now().to_msg()
        pose.pose.position.x    = x
        pose.pose.position.y    = y
        pose.pose.orientation.w = 1.0
        self._send_nav_goal(pose)

    def _send_nav_goal(self, goal_pose: PoseStamped) -> None:
        if not self._nav_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn("Nav2 action server not available")
            return

        goal_msg       = NavigateToPose.Goal()
        goal_msg.pose  = goal_pose

        future = self._nav_client.send_goal_async(
            goal_msg, feedback_callback=self._nav_feedback_cb)
        future.add_done_callback(self._nav_goal_response_cb)

    def _nav_goal_response_cb(self, future) -> None:
        handle = future.result()
        if not handle.accepted:
            self.get_logger().warn("Nav2 goal rejected")
            self._publish_event('navigation_failed')
            self._transition(State.GUIDANCE)
            return
        self._nav_handle = handle
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._nav_result_cb)

    def _nav_result_cb(self, future) -> None:
        result = future.result()
        status = result.status  # 3=SUCCEEDED 4=CANCELED 5=ABORTED

        if status == 4:  # 의도적 취소 (재경로 / stop 등)
            return

        if status == 3:  # SUCCEEDED
            if self._is_end_session:
                self._is_end_session = False
                self._current_wp     = None
                self._publish_event('home_reached')
                self._publish_event('session_ended')
                self._transition(State.GUIDANCE)
                return

            # 일반 웨이포인트 도착
            wp = self._current_wp
            if wp:
                self._publish_event('waypoint_arrived',
                                    waypoint_id=wp.id, label=wp.label)

            # 다음 웨이포인트가 있으면 STOPPED(대기), 없으면 GUIDANCE
            if self._waypoints:
                self._current_wp = None  # 도착 완료 → 다음 resume 시 _waypoints에서 팝
                self._prev_state = State.ESCORT
                self._transition(State.STOPPED)
            else:
                self._current_wp = None
                self._transition(State.GUIDANCE)

        elif status == 5:  # ABORTED
            self.get_logger().warn("Nav2 goal aborted")
            self._publish_event('navigation_failed')
            self._current_wp = None
            self._transition(State.GUIDANCE)

    def _nav_feedback_cb(self, feedback_msg) -> None:
        pass

    def _cancel_nav_goal(self) -> None:
        if self._nav_handle is not None:
            self._nav_handle.cancel_goal_async()
            self._nav_handle = None

    # ──────────────────────────────────────────────────────────────────────────
    # Publishers
    # ──────────────────────────────────────────────────────────────────────────

    def _publish_event(self, event: str, **kwargs) -> None:
        payload = {'type': 'event', 'event': event}
        payload.update(kwargs)
        self.event_pub.publish(String(data=json.dumps(payload)))
        self.get_logger().info(f"Event: {event}  {kwargs}")

    def _publish_mode(self, mode: str) -> None:
        self.mode_pub.publish(String(data=mode))

    def _publish_wp_status(self) -> None:
        payload = {
            'current_waypoint_id': self._current_wp.id if self._current_wp else None,
            'remaining_waypoints': len(self._waypoints),
        }
        self.wp_status_pub.publish(String(data=json.dumps(payload)))

    def _publish_state(self) -> None:
        """0.5Hz 주기 발행: 상태 + 모드 (늦게 뜨는 노드 대비)."""
        self.state_pub.publish(String(data=self.state))
        if self.state in (State.GUIDANCE, State.REPLAN):
            mux_mode = 'GUIDANCE'
        elif self.state == State.ESCORT:
            mux_mode = _escort_mode(self._is_end_session)
        else:  # STOPPED
            mux_mode = 'ESCORT'
        self._publish_mode(mux_mode)

        self._publish_wp_status()

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_robot_xy(self) -> tuple:
        """현재 로봇 위치를 map 프레임에서 (x, y)로 반환. 실패 시 (None, None)."""
        try:
            t = self.tf_buffer.lookup_transform(
                'map', 'base_footprint',
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.5),
            )
            return t.transform.translation.x, t.transform.translation.y
        except Exception as e:
            self.get_logger().warn(f"Robot position TF failed: {e}")
            return None, None

    def _sort_nearest_neighbor(self, waypoints: list) -> list:
        """현재 로봇 위치 기준 최근접 이웃 알고리즘으로 웨이포인트 순서 최적화.

        TF 실패 시 입력 순서 그대로 반환.
        """
        if len(waypoints) <= 1:
            return waypoints

        rx, ry = self._get_robot_xy()
        if rx is None:
            self.get_logger().warn("Cannot get robot position — using original waypoint order")
            return waypoints

        unvisited = list(waypoints)
        sorted_wps: list = []
        cx, cy = rx, ry

        while unvisited:
            nearest = min(unvisited,
                          key=lambda wp: (wp.x - cx) ** 2 + (wp.y - cy) ** 2)
            sorted_wps.append(nearest)
            unvisited.remove(nearest)
            cx, cy = nearest.x, nearest.y

        ids_before = [w.id for w in waypoints]
        ids_after  = [w.id for w in sorted_wps]
        if ids_before != ids_after:
            self.get_logger().info(
                f"Waypoints reordered (nearest-neighbor): {ids_after}")

        return sorted_wps

    def _transform_to_map(self, point_stamped: PointStamped) -> Optional[Point]:
        try:
            transformed = self.tf_buffer.transform(
                point_stamped, 'map',
                timeout=rclpy.duration.Duration(seconds=0.1))
            return transformed.point
        except Exception:
            return None

    def _min_dist_to_path(self, point: Point, path: Path) -> float:
        min_d = float('inf')
        for pose_stamped in path.poses:
            p = pose_stamped.pose.position
            d = math.sqrt((point.x - p.x) ** 2 + (point.y - p.y) ** 2)
            if d < min_d:
                min_d = d
        return min_d


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
