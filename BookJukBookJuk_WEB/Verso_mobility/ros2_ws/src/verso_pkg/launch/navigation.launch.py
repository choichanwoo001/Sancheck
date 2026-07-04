"""
navigation.launch.py

Scout Mini 전체 Navigation 스택 통합 런치.
Nav2 / AMCL / Keepout Filter 포함, Human Guidance 제외 (별도 런치).

사전 준비 (한 번만, sudo 필요):
  sudo bash src/verso_pkg/scripts/setup_can.sh

기동:
  ros2 launch verso_pkg navigation.launch.py

포함 항목:
  1. scout_base        — Scout Mini CAN 드라이버
  2. sllidar_ros2      — A1 LiDAR
  3. TF: base_link → base_footprint   (z=-0.15)
  4. TF: base_footprint → laser       (z=0.55, yaw=180°)
  5. Nav2 bringup      — AMCL + map_server + controller + planner 등
  6. map_server_keepout       — Keepout Filter 마스크 맵 서버 (lifecycle)
  7. costmap_filter_info_server       — Keepout 코스트맵 필터 정보 서버 (lifecycle)
  8. lifecycle_manager_keepout        — 6·7번 자동 configure/activate
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


# ── 경로 상수 ────────────────────────────────────────────────────────────────
MAP_FILE        = '/home/ivl1/verso/maps/b2floor_edited.yaml'
NAV2_PARAMS     = '/home/ivl1/verso/config/scout_nav2_params.yaml'
KEEPOUT_MASK    = '/home/ivl1/verso/maps/keepout_mask.yaml'
LIDAR_PORT      = '/dev/ttyUSB0'


def generate_launch_description() -> LaunchDescription:

    # ── Launch 인수 ──────────────────────────────────────────────────────────
    args = [
        DeclareLaunchArgument(
            'use_sim_time', default_value='False',
            description='시뮬레이션 시계 사용 여부'),
        DeclareLaunchArgument(
            'autostart', default_value='True',
            description='Nav2 lifecycle 자동 시작'),
        DeclareLaunchArgument(
            'map', default_value=MAP_FILE,
            description='Nav2 맵 파일 경로'),
        DeclareLaunchArgument(
            'params_file', default_value=NAV2_PARAMS,
            description='Nav2 파라미터 파일 경로'),
    ]

    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart    = LaunchConfiguration('autostart')
    nav2_map     = LaunchConfiguration('map')
    params_file  = LaunchConfiguration('params_file')

    # ── 1. Scout Mini base ────────────────────────────────────────────────────
    # cmd_vel_mux / guided_escort_node → /cmd_vel_robot → scout_base_node
    # (모든 속도 명령이 mux 또는 guided_escort를 통해 라우팅되도록 리맵)
    scout_base = Node(
        package='scout_base',
        executable='scout_base_node',
        name='scout_base_node',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'port_name':       'can0',
            'odom_frame':      'odom',
            'base_frame':      'base_link',
            'odom_topic_name': 'odom',
            'is_scout_mini':   True,
            'is_omni_wheel':   False,
            'simulated_robot': False,
            'control_rate':    50,
        }],
        remappings=[
            ('/cmd_vel', '/cmd_vel_robot'),
        ],
    )

    # ── 2. LiDAR (SLAMTEC A1) ────────────────────────────────────────────────
    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('sllidar_ros2'),
                         'launch', 'sllidar_a1_launch.py')
        ),
        launch_arguments={
            'serial_port': LIDAR_PORT,
        }.items(),
    )

    # ── 3. TF: base_link → base_footprint ────────────────────────────────────
    #   Scout Mini base_footprint는 base_link 아래 z=-0.15 에 위치
    tf_base_footprint = Node(
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

    # ── 4. TF: base_footprint → laser ────────────────────────────────────────
    #   LiDAR: z=0.55, yaw=180° (마운트 방향에 따른 회전)
    tf_laser = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_footprint_to_laser',
        output='screen',
        arguments=[
            '--x', '0.15', '--y', '0', '--z', '1.35',
            '--roll', '0', '--pitch', '0', '--yaw', '3.1416',
            '--frame-id', 'base_footprint',
            '--child-frame-id', 'laser',
        ],
    )

    # ── 5. Nav2 bringup ───────────────────────────────────────────────────────
    # controller_server 출력: /cmd_vel → /cmd_vel_nav2 (cmd_vel_mux로 전달)
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('nav2_bringup'),
                         'launch', 'bringup_launch.py')
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'autostart':    autostart,
            'map':          nav2_map,
            'params_file':  params_file,
        }.items(),
    )

    # ── 6. Keepout Filter 마스크 맵 서버 (lifecycle node) ─────────────────────
    #   토픽: map → keepout_filter_mask (remap)
    map_server_keepout = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server_keepout',
        output='screen',
        parameters=[{
            'yaml_filename': KEEPOUT_MASK,
            'use_sim_time': False,
        }],
        remappings=[('map', 'keepout_filter_mask')],
    )

    # ── 7. Costmap Filter Info 서버 (lifecycle node) ───────────────────────────
    costmap_filter_info = Node(
        package='nav2_map_server',
        executable='costmap_filter_info_server',
        name='costmap_filter_info_server',
        output='screen',
        parameters=[{
            'use_sim_time':      False,
            'type':              0,           # 0 = keepout filter
            'filter_info_topic': '/costmap_filter_info',
            'mask_topic':        '/keepout_filter_mask',
            'base':              0.0,
            'multiplier':        1.0,
        }],
    )

    # ── 8. Lifecycle Manager (6·7번 자동 configure → activate) ────────────────
    lifecycle_manager_keepout = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_keepout',
        output='screen',
        parameters=[{
            'use_sim_time': False,
            'autostart':    True,
            'node_names':   ['map_server_keepout', 'costmap_filter_info_server'],
        }],
    )

    return LaunchDescription(args + [
        # TF 먼저 (드라이버보다 빨리 떠야 안전)
        tf_base_footprint,
        tf_laser,
        # 하드웨어 드라이버
        scout_base,
        lidar,
        # Navigation (Nav2가 /cmd_vel에 직접 발행 — cmd_vel_mux는 NAV 모드에서 침묵)
        nav2,
        # Keepout Filter
        map_server_keepout,
        costmap_filter_info,
        lifecycle_manager_keepout,
    ])
