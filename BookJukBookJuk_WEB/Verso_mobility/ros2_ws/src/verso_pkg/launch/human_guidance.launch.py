"""
human_guidance.launch.py

후방 RealSense + YOLOv8 + ByteTrack + OSNet Re-ID 기반 Human Guidance 스택.
Collision Monitor + cmd_vel Mux + Mission Manager + Web Bridge 포함.
Nav2 / AMCL 없이 독립 실행. (Nav2 스택은 navigation.launch.py 참조)

기동:
  ros2 launch verso_pkg human_guidance.launch.py

주요 옵션:
  device:=cpu              GPU 없을 때
  yolo_model:=yolov8s.pt   더 정확한 모델
  target_distance:=2.0     에스코트 거리 변경
  use_rviz:=true           RViz2 함께 실행
  launch_realsense:=false  RealSense 이미 실행 중일 때
  rosbridge_port:=9090     rosbridge WebSocket 포트

데이터 흐름:
  GUIDANCE 모드:
    escort_controller → /cmd_vel_escort
      → collision_monitor ← /scan
      → /cmd_vel_safe
      → cmd_vel_mux (GUIDANCE: 전달)
      → /cmd_vel_robot → 로봇

  GUIDED_ESCORT 모드 (웨이포인트 주행 + 사람 속도):
    Nav2 → /cmd_vel → guided_escort_node (사람 거리 기반 선속도 스케일)
      → /cmd_vel_robot → 로봇   (cmd_vel_mux 침묵)

  ESCORT 모드 (홈 복귀, 사람 추적 불필요):
    Nav2 → /cmd_vel → cmd_vel_mux (ESCORT: 전달)
      → /cmd_vel_robot → 로봇

  웹 ↔ 로봇:
    웹 → rosbridge → /verso/waypoints, /verso/command
      → web_bridge_node → mission_manager
    mission_manager → web_bridge_node
      → /verso/status (1Hz), /verso/event
      → rosbridge → 웹

후방 카메라 TF (base_footprint → camera_rear_link):
  위치 : x=-0.18, y=0, z=0.53 (단위: m)
  자세 : yaw=180° (후방), pitch=0°
"""

import math
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


# ── 카메라 마운트 위치 (base_footprint 기준) ────────────────────────────────
CAMERA_X = -0.18
CAMERA_Y =  0.00
CAMERA_Z =  1.12


def quat_from_rpy(roll: float, pitch: float, yaw: float) -> tuple:
    """RPY → quaternion (qx, qy, qz, qw)."""
    cr, sr = math.cos(roll  / 2), math.sin(roll  / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw   / 2), math.sin(yaw   / 2)
    return (
        sr * cp * cy - cr * sp * sy,   # qx
        cr * sp * cy + sr * cp * sy,   # qy
        cr * cp * sy - sr * sp * cy,   # qz
        cr * cp * cy + sr * sp * sy,   # qw
    )


def generate_launch_description() -> LaunchDescription:

    pkg_verso = get_package_share_directory('verso_pkg')
    cfg_file  = os.path.join(pkg_verso, 'config', 'human_guidance.yaml')
    cm_cfg    = os.path.join(pkg_verso, 'config', 'collision_monitor.yaml')

    # ── Launch 인수 ──────────────────────────────────────────────────────────
    args = [
        DeclareLaunchArgument(
            'device', default_value='cuda',
            description='추론 장치: cuda | cpu'),
        DeclareLaunchArgument(
            'yolo_model', default_value='yolov8n.pt',
            description='YOLOv8 가중치 파일명'),
        DeclareLaunchArgument(
            'reid_model', default_value='osnet_x0_25_msmt17.pt',
            description='OSNet Re-ID 가중치'),
        DeclareLaunchArgument(
            'target_distance', default_value='1.5',
            description='사람 앞 에스코트 유지 거리 [m]'),
        DeclareLaunchArgument(
            'use_rviz', default_value='false',
            description='RViz2 함께 실행 여부'),
        DeclareLaunchArgument(
            'launch_realsense', default_value='true',
            description='RealSense 드라이버 함께 실행 (이미 실행 중이면 false)'),
        DeclareLaunchArgument(
            'rosbridge_port', default_value='9090',
            description='rosbridge WebSocket 포트'),
    ]

    # ── base_link → base_footprint Static TF ─────────────────────────────────
    # scout_base: odom → base_link 발행
    # 이 TF 없으면 odom → camera 체인이 끊김
    base_footprint_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_base_link_to_footprint',
        output='screen',
        arguments=[
            '--x', '0', '--y', '0', '--z', '-0.15',
            '--roll', '0', '--pitch', '0', '--yaw', '0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'base_footprint',
        ],
    )

    # ── 후방 카메라 Static TF ─────────────────────────────────────────────────
    # yaw = π (180°): 카메라가 로봇 후방을 바라봄
    CAMERA_PITCH_DEG = 0.0   # ← 기울기 확정 후 수정
    pitch_rad = math.radians(CAMERA_PITCH_DEG)
    qx, qy, qz, qw = quat_from_rpy(0.0, -pitch_rad, math.pi)

    camera_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='camera_rear_tf',
        output='screen',
        arguments=[
            '--x',        str(CAMERA_X),
            '--y',        str(CAMERA_Y),
            '--z',        str(CAMERA_Z),
            '--qx',       str(round(qx, 6)),
            '--qy',       str(round(qy, 6)),
            '--qz',       str(round(qz, 6)),
            '--qw',       str(round(qw, 6)),
            '--frame-id', 'base_footprint',
            '--child-frame-id', 'camera_rear_link',
        ],
    )

    # ── RealSense D435i (후방) ────────────────────────────────────────────────
    realsense_node = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('realsense2_camera'),
                         'launch', 'rs_launch.py')
        ),
        condition=IfCondition(LaunchConfiguration('launch_realsense')),
        launch_arguments={
            'camera_name':            'camera_rear',
            'camera_namespace':       'camera',      # 토픽: /camera/camera_rear/...
            'enable_color':           'true',
            'enable_depth':           'true',
            'enable_infra1':          'false',
            'enable_infra2':          'false',
            'enable_gyro':            'false',
            'enable_accel':           'false',
            'align_depth.enable':     'false',
            'enable_sync':            'false',
            'depth_module.profile':   '640x480x30',
            'rgb_camera.profile':     '640x480x30',
            'pointcloud.enable':      'false',
            'publish_tf':             'true',
            'base_frame_id':          'camera_rear_link',
        }.items(),
    )

    # ── person_tracker_node ───────────────────────────────────────────────────
    tracker_node = Node(
        package='verso_pkg',
        executable='person_tracker',
        name='person_tracker',
        output='screen',
        emulate_tty=True,
        additional_env={'CUDA_VISIBLE_DEVICES': '0'},
        parameters=[
            cfg_file,
            {
                'device':     LaunchConfiguration('device'),
                'yolo_model': LaunchConfiguration('yolo_model'),
                'reid_model': LaunchConfiguration('reid_model'),
            },
        ],
    )

    # ── escort_controller_node ────────────────────────────────────────────────
    # /cmd_vel → /cmd_vel_escort 로 리맵:
    #   collision_monitor가 /cmd_vel_escort를 입력으로 받음
    controller_node = Node(
        package='verso_pkg',
        executable='escort_controller',
        name='escort_controller',
        output='screen',
        emulate_tty=True,
        parameters=[
            cfg_file,
            {
                'target_distance': LaunchConfiguration('target_distance'),
            },
        ],
        remappings=[
            ('/cmd_vel', '/cmd_vel_escort'),
        ],
    )

    # ── collision_monitor ─────────────────────────────────────────────────────
    # 입력: /cmd_vel_escort  출력: /cmd_vel_safe
    # ESCORT 모드 전용 (NAV 모드는 Nav2 자체 costmap 장애물 회피)
    collision_monitor_node = Node(
        package='nav2_collision_monitor',
        executable='collision_monitor',
        name='collision_monitor',
        output='screen',
        parameters=[cm_cfg],
    )

    # ── lifecycle_manager (collision_monitor 자동 configure/activate) ─────────
    lifecycle_manager_cm = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_collision_monitor',
        output='screen',
        parameters=[{
            'use_sim_time': False,
            'autostart':    True,
            'node_names':   ['collision_monitor'],
        }],
    )

    # ── cmd_vel_mux_node ──────────────────────────────────────────────────────
    # GUIDANCE: /cmd_vel_safe → /cmd_vel 전달
    # ESCORT:   침묵 (Nav2가 /cmd_vel에 직접 발행)
    mux_node = Node(
        package='verso_pkg',
        executable='cmd_vel_mux',
        name='cmd_vel_mux',
        output='screen',
        emulate_tty=True,
    )

    # ── mission_manager_node ──────────────────────────────────────────────────
    # GUIDANCE ↔ ESCORT ↔ REPLAN ↔ STOPPED 상태 머신 + Nav2 액션 클라이언트
    mission_manager_node = Node(
        package='verso_pkg',
        executable='mission_manager',
        name='mission_manager',
        output='screen',
        emulate_tty=True,
        parameters=[cfg_file],
    )

    # ── guided_escort_node ────────────────────────────────────────────────────
    # GUIDED_ESCORT 모드: Nav2 /cmd_vel 조향 유지 + 사람 거리 기반 선속도 스케일
    # /cmd_vel (Nav2) + /verso/person/position → /cmd_vel_robot
    guided_escort_node = Node(
        package='verso_pkg',
        executable='guided_escort',
        name='guided_escort',
        output='screen',
        emulate_tty=True,
        parameters=[cfg_file],
    )

    # ── web_bridge_node ───────────────────────────────────────────────────────
    # 웹(rosbridge) ↔ mission_manager JSON 인터페이스
    # /verso/waypoints, /verso/command 수신
    # /verso/status (1Hz), /verso/event 발행
    web_bridge_node = Node(
        package='verso_pkg',
        executable='web_bridge',
        name='web_bridge',
        output='screen',
        emulate_tty=True,
    )

    # ── rosbridge_server ──────────────────────────────────────────────────────
    # 웹 클라이언트가 WebSocket으로 연결하는 브릿지 서버
    rosbridge_node = Node(
        package='rosbridge_server',
        executable='rosbridge_websocket',
        name='rosbridge_websocket',
        output='screen',
        parameters=[{
            'port': LaunchConfiguration('rosbridge_port'),
        }],
    )

    # ── RViz2 (옵션) ──────────────────────────────────────────────────────────
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_rviz')),
    )

    return LaunchDescription(args + [
        SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', '0'),
        base_footprint_tf,
        camera_tf_node,
        realsense_node,
        tracker_node,
        controller_node,
        collision_monitor_node,
        lifecycle_manager_cm,
        mux_node,
        guided_escort_node,
        mission_manager_node,
        web_bridge_node,
        rosbridge_node,
        rviz_node,
    ])
