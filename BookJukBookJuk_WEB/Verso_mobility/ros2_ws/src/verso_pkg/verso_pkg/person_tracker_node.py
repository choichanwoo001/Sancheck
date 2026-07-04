"""
person_tracker_node.py

ROS2 node: subscribes to rear RealSense color + depth images,
runs YOLOv8 + BotSort (ByteTrack + OSNet Re-ID), and publishes:

  /verso/person/position   — geometry_msgs/PointStamped  (camera frame)
  /verso/person/velocity   — geometry_msgs/Vector3Stamped (estimated velocity)
  /verso/person/status     — std_msgs/String  (TRACKING | SEARCHING | LOST)
  /verso/person/track_id   — std_msgs/Int32
  /verso/detection_image   — sensor_msgs/Image (visualization, throttled)

Services:
  /verso/select_target     — std_srvs/SetBool
      True  → auto-select nearest person as new target
      False → release current target (robot stops)

Camera frame convention (RealSense D435i, rear-mounted, facing backward):
  z: depth (distance from camera lens toward person)
  x: right in camera view  (= robot's LEFT if camera is rear-facing)
  y: down in camera view

The escort_controller_node receives position/velocity and converts them
into cmd_vel commands.
"""

from __future__ import annotations

import time
from collections import deque

import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped, Vector3Stamped
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Int32, String
from std_srvs.srv import SetBool

import cv2
import message_filters

from sensor_msgs.msg import CompressedImage
from verso_pkg.human_detector import HumanDetector


# QoS profile for sensor data (best-effort, keep-last-1)
SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class PersonTrackerNode(Node):

    def __init__(self) -> None:
        super().__init__('person_tracker_node')

        # ── Parameters ──────────────────────────────────────────────────────
        self._declare_params()
        p = self._get_params()

        self.get_logger().info(
            f"PersonTrackerNode starting  yolo={p['yolo_model']}  "
            f"reid={p['reid_model']}  device={p['device']}"
        )

        # ── Detector ────────────────────────────────────────────────────────
        self.detector = HumanDetector(
            yolo_weights=p['yolo_model'],
            reid_weights=p['reid_model'],
            device=p['device'],
            conf_threshold=p['detection_confidence'],
            half=p['use_half_precision'],
        )

        self.auto_select = p['auto_select_nearest']
        self.lost_reselect_frames: int = p['lost_reselect_frames']

        # ── Camera intrinsics ────────────────────────────────────────────────
        self.K: np.ndarray | None = None          # 3×3 camera matrix
        self.camera_frame_id: str = 'camera_rear_color_optical_frame'

        # ── Velocity estimation ──────────────────────────────────────────────
        history_size: int = p['velocity_history_size']
        # deque of (x, y, z, timestamp_sec)
        self.pos_history: deque = deque(maxlen=history_size)

        # ── Depth filtering ──────────────────────────────────────────────────
        self.min_depth: float = p['min_person_depth']
        self.max_depth: float = p['max_person_depth']

        # ── CV Bridge ────────────────────────────────────────────────────────
        self.bridge = CvBridge()
        self.viz_every_n: int = p['viz_every_n_frames']
        self._frame_count: int = 0

        prefix: str = p['camera_topic_prefix']

        # ── Subscribers ──────────────────────────────────────────────────────
        # depth_topic: full topic path, configurable because align_depth changes the name
        depth_topic: str = p['depth_topic'] or f'{prefix}/aligned_depth_to_color/image_raw'

        # compressed 토픽 구독: raw image(~900KB)는 DDS 전송 병목 발생,
        # compressed(~50-100KB JPEG)는 30fps 안정 전송 가능
        color_sub = message_filters.Subscriber(
            self, CompressedImage, f'{prefix}/color/image_raw/compressed',
            qos_profile=SENSOR_QOS)
        depth_sub = message_filters.Subscriber(
            self, Image, depth_topic,
            qos_profile=SENSOR_QOS)

        self.ts = message_filters.ApproximateTimeSynchronizer(
            [color_sub, depth_sub], queue_size=5, slop=0.05)
        self.ts.registerCallback(self._image_cb)

        self.create_subscription(
            CameraInfo, f'{prefix}/color/camera_info',
            self._camera_info_cb, 10)

        # ── Publishers ───────────────────────────────────────────────────────
        self.pos_pub   = self.create_publisher(PointStamped,   '/verso/person/position',  10)
        self.vel_pub   = self.create_publisher(Vector3Stamped, '/verso/person/velocity',  10)
        self.stat_pub  = self.create_publisher(String,         '/verso/person/status',    10)
        self.id_pub    = self.create_publisher(Int32,          '/verso/person/track_id',  10)
        self.viz_pub   = self.create_publisher(Image,          '/verso/detection_image',  10)

        # ── Service ──────────────────────────────────────────────────────────
        self.create_service(SetBool, '/verso/select_target', self._select_target_srv)

        self.get_logger().info("PersonTrackerNode ready.")

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------

    def _declare_params(self) -> None:
        D = ParameterDescriptor

        self.declare_parameter('camera_topic_prefix',    '/camera_rear',
            D(description='RealSense topic prefix'))
        self.declare_parameter('yolo_model',             'yolov8n.pt',
            D(description='YOLOv8 weights file or model name'))
        self.declare_parameter('reid_model',             'osnet_x0_25_msmt17.pt',
            D(description='OSNet Re-ID weights for BotSort'))
        self.declare_parameter('device',                 'cuda',
            D(description='Inference device: cuda or cpu'))
        self.declare_parameter('detection_confidence',   0.50,
            D(description='YOLO confidence threshold'))
        self.declare_parameter('use_half_precision',     True,
            D(description='FP16 inference (CUDA only)'))
        self.declare_parameter('auto_select_nearest',    True,
            D(description='Auto-lock nearest person on first detection'))
        self.declare_parameter('lost_reselect_frames',   60,
            D(description='Re-select target after N frames without it'))
        self.declare_parameter('velocity_history_size',  10,
            D(description='Frames kept for velocity estimation'))
        self.declare_parameter('min_person_depth',       0.3,
            D(description='Minimum valid depth (m)'))
        self.declare_parameter('max_person_depth',       8.0,
            D(description='Maximum valid depth (m)'))
        self.declare_parameter('viz_every_n_frames',     3,
            D(description='Publish visualization every N frames'))
        # Leave empty to auto-derive from camera_topic_prefix
        self.declare_parameter('depth_topic',            '',
            D(description='Full depth image topic (empty = auto: prefix/aligned_depth_to_color/image_raw)'))

    def _get_params(self) -> dict:
        names = [
            'camera_topic_prefix', 'yolo_model', 'reid_model', 'device',
            'detection_confidence', 'use_half_precision', 'auto_select_nearest',
            'lost_reselect_frames', 'velocity_history_size',
            'min_person_depth', 'max_person_depth', 'viz_every_n_frames',
            'depth_topic',
        ]
        return {n: self.get_parameter(n).value for n in names}

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _camera_info_cb(self, msg: CameraInfo) -> None:
        if self.K is None:
            self.K = np.array(msg.k).reshape(3, 3)
            self.camera_frame_id = msg.header.frame_id
            self.get_logger().info(
                f"Camera intrinsics received  fx={self.K[0,0]:.1f} "
                f"fy={self.K[1,1]:.1f}  cx={self.K[0,2]:.1f}  cy={self.K[1,2]:.1f}"
            )

    def _image_cb(self, color_msg: CompressedImage, depth_msg: Image) -> None:
        if self.K is None:
            self.get_logger().warn("Waiting for camera_info …", throttle_duration_sec=5.0)
            return

        self._frame_count += 1
        stamp = color_msg.header.stamp

        # ── Convert ROS images → OpenCV ──────────────────────────────────
        # CompressedImage → BGR (JPEG decode)
        np_arr    = np.frombuffer(color_msg.data, np.uint8)
        frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        depth_image = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding='passthrough')
        # depth_image: uint16 (millimetres) from RealSense

        frame_h, frame_w = frame_bgr.shape[:2]

        # ── Detection + Tracking ─────────────────────────────────────────
        tracks = self.detector.update(frame_bgr)

        # ── Target selection ─────────────────────────────────────────────
        if not self.detector.is_target_locked and self.auto_select and tracks:
            self.detector.auto_select_target(tracks, frame_w)

        # Auto re-select if target lost for too long
        if (self.detector.is_target_locked
                and self.detector.frames_without_target >= self.lost_reselect_frames
                and tracks):
            self.get_logger().info("Target lost — re-selecting nearest person.")
            self.detector.auto_select_target(tracks, frame_w)

        target = self.detector.get_target_track(tracks)

        # ── Publish status ────────────────────────────────────────────────
        if target is None:
            if self.detector.is_target_locked:
                status = 'SEARCHING'
            else:
                status = 'LOST'
        else:
            status = 'TRACKING'

        self.stat_pub.publish(String(data=status))

        if target is None:
            self._publish_zero_velocity()
            self._publish_viz(frame_bgr, tracks, None, stamp)
            return

        # ── 3-D position from depth ───────────────────────────────────────
        point_3d = self._pixel_to_3d(
            target.cx, target.cy, depth_image,
            bbox=(target.x1, target.y1, target.x2, target.y2),
        )
        if point_3d is None:
            self.get_logger().warn(
                "Invalid depth for target bbox.", throttle_duration_sec=2.0)
            self._publish_viz(frame_bgr, tracks, target, stamp)
            return

        x3d, y3d, z3d = point_3d

        # ── Velocity estimation ───────────────────────────────────────────
        now = stamp.sec + stamp.nanosec * 1e-9
        self.pos_history.append((x3d, y3d, z3d, now))
        vx, vy, vz = self._estimate_velocity()

        # ── Publish position ──────────────────────────────────────────────
        pos_msg = PointStamped()
        pos_msg.header.stamp    = stamp
        pos_msg.header.frame_id = self.camera_frame_id
        pos_msg.point.x = x3d
        pos_msg.point.y = y3d
        pos_msg.point.z = z3d
        self.pos_pub.publish(pos_msg)

        # ── Publish velocity ──────────────────────────────────────────────
        vel_msg = Vector3Stamped()
        vel_msg.header.stamp    = stamp
        vel_msg.header.frame_id = self.camera_frame_id
        vel_msg.vector.x = vx
        vel_msg.vector.y = vy
        vel_msg.vector.z = vz
        self.vel_pub.publish(vel_msg)

        # ── Publish track ID ──────────────────────────────────────────────
        self.id_pub.publish(Int32(data=target.id))

        # ── Visualization ─────────────────────────────────────────────────
        self._publish_viz(frame_bgr, tracks, target, stamp)

    # ------------------------------------------------------------------
    # Depth projection
    # ------------------------------------------------------------------

    def _pixel_to_3d(
        self,
        cx: float,
        cy: float,
        depth_image: np.ndarray,
        bbox: tuple | None = None,
    ) -> tuple[float, float, float] | None:
        """
        Back-project a pixel + depth to 3-D in camera frame.

        RealSense depth images are uint16 in millimetres.
        Sampling strategy:
          1. 중앙 21×21 패치에서 유효값 탐색
          2. 없으면 bbox 중앙 50% 영역(상반신 제외, 몸통 위주)에서 탐색
        Returns (x, y, z) in metres, or None if depth is invalid.
        """
        h, w = depth_image.shape[:2]
        ix, iy = int(round(cx)), int(round(cy))
        ix = np.clip(ix, 0, w - 1)
        iy = np.clip(iy, 0, h - 1)

        # 1단계: 중앙 21×21 패치
        r = 10
        y0, y1 = max(0, iy - r), min(h, iy + r + 1)
        x0, x1 = max(0, ix - r), min(w, ix + r + 1)
        patch = depth_image[y0:y1, x0:x1].astype(np.float32)
        valid = patch[patch > 0]

        # 2단계: 패치에 유효값 없으면 bbox 중앙 50% 영역으로 확장
        if valid.size < 5 and bbox is not None:
            bx1, by1, bx2, by2 = bbox
            bw = bx2 - bx1
            bh = by2 - by1
            # 몸통 영역: 가로 중앙 50%, 세로 중앙 40~80%
            rx0 = int(np.clip(bx1 + bw * 0.25, 0, w - 1))
            rx1 = int(np.clip(bx2 - bw * 0.25, 0, w))
            ry0 = int(np.clip(by1 + bh * 0.40, 0, h - 1))
            ry1 = int(np.clip(by1 + bh * 0.80, 0, h))
            region = depth_image[ry0:ry1, rx0:rx1].astype(np.float32)
            valid = region[region > 0]
            # 이 영역의 대표 픽셀을 투영 기준점으로 재계산
            if valid.size > 0:
                ix = int((rx0 + rx1) / 2)
                iy = int((ry0 + ry1) / 2)

        if valid.size == 0:
            return None

        depth_mm = float(np.median(valid))
        depth_m  = depth_mm / 1000.0

        if not (self.min_depth <= depth_m <= self.max_depth):
            self.get_logger().warn(
                f"Depth out of range: {depth_m:.2f}m "
                f"(valid: {self.min_depth}~{self.max_depth}m)",
                throttle_duration_sec=2.0)
            return None

        fx, fy   = self.K[0, 0], self.K[1, 1]
        cx0, cy0 = self.K[0, 2], self.K[1, 2]

        x = (cx - cx0) * depth_m / fx
        y = (cy - cy0) * depth_m / fy
        z = depth_m
        return (x, y, z)

    # ------------------------------------------------------------------
    # Velocity estimation
    # ------------------------------------------------------------------

    def _estimate_velocity(self) -> tuple[float, float, float]:
        """
        Estimate linear velocity (m/s) from position history.
        Uses a simple least-squares regression over the stored history.
        """
        if len(self.pos_history) < 3:
            return (0.0, 0.0, 0.0)

        history = np.array(self.pos_history)   # N×4: [x, y, z, t]
        t  = history[:, 3] - history[0, 3]    # relative time (seconds)
        dt = t[-1] - t[0]
        if dt < 1e-3:
            return (0.0, 0.0, 0.0)

        # Fit linear model (y = a·t + b) for each axis
        A = np.vstack([t, np.ones(len(t))]).T
        vx = np.linalg.lstsq(A, history[:, 0], rcond=None)[0][0]
        vy = np.linalg.lstsq(A, history[:, 1], rcond=None)[0][0]
        vz = np.linalg.lstsq(A, history[:, 2], rcond=None)[0][0]
        return (float(vx), float(vy), float(vz))

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def _publish_viz(self, frame_bgr, tracks, target, stamp) -> None:
        if self._frame_count % self.viz_every_n != 0:
            return
        vis = self.detector.draw_tracks(frame_bgr, tracks, target)
        try:
            viz_msg = self.bridge.cv2_to_imgmsg(vis, encoding='bgr8')
            viz_msg.header.stamp = stamp
            self.viz_pub.publish(viz_msg)
        except Exception as e:
            self.get_logger().warn(f"Viz publish failed: {e}")

    def _publish_zero_velocity(self) -> None:
        self.vel_pub.publish(Vector3Stamped())

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------

    def _select_target_srv(
        self, request: SetBool.Request, response: SetBool.Response
    ) -> SetBool.Response:
        if request.data:
            self.detector.release_target()
            self.pos_history.clear()
            response.success = True
            response.message = "Target released — will auto-select on next detection."
        else:
            self.detector.release_target()
            response.success = True
            response.message = "Target released."
        return response


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PersonTrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
