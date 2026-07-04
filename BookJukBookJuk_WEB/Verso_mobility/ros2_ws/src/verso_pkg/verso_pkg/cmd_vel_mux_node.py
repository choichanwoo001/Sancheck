"""
cmd_vel_mux_node.py

속도 명령 라우터. 모드에 따라 소스를 선택해 /cmd_vel_robot으로 전달.

모드별 동작:
  GUIDANCE      : /cmd_vel_safe (collision_monitor 출력) → /cmd_vel_robot
  ESCORT        : /cmd_vel      (Nav2 출력 직통)         → /cmd_vel_robot
  GUIDED_ESCORT : 침묵 (guided_escort_node가 /cmd_vel_robot에 직접 발행)
  STOPPED       : 침묵 (mission_manager가 Nav2 목표 취소)

모드 전환 시 /cmd_vel_robot에 즉시 zero Twist 발행 → 잔류 속도 제거.

토픽:
  Subscribe:
    /cmd_vel_safe        — collision_monitor 출력 (GUIDANCE 경로)
    /cmd_vel             — Nav2 출력 (ESCORT 경로)
    /verso/mission/mode  — 'GUIDANCE' | 'ESCORT' | 'GUIDED_ESCORT'
  Publish:
    /cmd_vel_robot       — 로봇 최종 속도 명령
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String


class CmdVelMuxNode(Node):

    GUIDANCE       = 'GUIDANCE'
    ESCORT         = 'ESCORT'
    GUIDED_ESCORT  = 'GUIDED_ESCORT'

    # 침묵 모드 (발행하지 않음)
    _SILENT_MODES = frozenset([GUIDED_ESCORT])

    def __init__(self) -> None:
        super().__init__('cmd_vel_mux')

        self.mode = self.GUIDANCE

        self.create_subscription(Twist,  '/cmd_vel_safe',       self._safe_cb,  10)
        self.create_subscription(Twist,  '/cmd_vel',            self._nav_cb,   10)
        self.create_subscription(String, '/verso/mission/mode', self._mode_cb,  10)

        self.pub = self.create_publisher(Twist, '/cmd_vel_robot', 10)

        self.get_logger().info(f"CmdVelMuxNode ready  initial_mode={self.mode}")

    def _safe_cb(self, msg: Twist) -> None:
        """collision_monitor 출력 — GUIDANCE 모드에서만 전달."""
        if self.mode == self.GUIDANCE:
            self.pub.publish(msg)

    def _nav_cb(self, msg: Twist) -> None:
        """Nav2 출력 — ESCORT 모드에서만 전달."""
        if self.mode == self.ESCORT:
            self.pub.publish(msg)

    def _mode_cb(self, msg: String) -> None:
        new_mode = msg.data
        if new_mode not in (self.GUIDANCE, self.ESCORT, self.GUIDED_ESCORT):
            self.get_logger().warn(f"Unknown mode: {new_mode}")
            return
        if new_mode != self.mode:
            self.get_logger().info(f"Mode: {self.mode} → {new_mode}")
            # 모드 전환 시 즉시 정지 명령 → 잔류 속도 제거
            self.pub.publish(Twist())
        self.mode = new_mode


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CmdVelMuxNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
