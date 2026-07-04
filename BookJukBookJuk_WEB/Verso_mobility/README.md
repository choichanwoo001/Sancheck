# Verso Robot

## 환경 세팅 (최초 1회)

### 1. 클론
git clone https://github.com/yourteam/verso.git
cd verso

### 2. 외부 패키지 받기
sudo apt install python3-vcstool
vcs import < verso.repos

### 3. 의존성 설치
sudo apt install -y \
    ros-humble-nav2-bringup \
    ros-humble-slam-toolbox \
    ros-humble-teleop-twist-keyboard \
    ros-humble-unique-identifier-msgs \
    can-utils

### 4. empy 버전 맞추기 (conda 환경인 경우)
pip install empy==3.3.4

### 5. 빌드
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install

## 실행

### SLAM 매핑
ros2 launch ...

### 자율주행
ros2 launch ...
