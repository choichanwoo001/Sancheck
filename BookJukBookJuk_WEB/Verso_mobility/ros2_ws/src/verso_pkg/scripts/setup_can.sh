#!/bin/bash
# setup_can.sh
# navigation.launch.py 실행 전에 한 번만 실행하면 됩니다.
# 사용법: sudo bash scripts/setup_can.sh
#      또는: chmod +x scripts/setup_can.sh && sudo ./scripts/setup_can.sh

set -e

echo "[setup_can] gs_usb 모듈 로드..."
modprobe gs_usb

echo "[setup_can] CAN 인터페이스 활성화 (bitrate 500000)..."
ip link set can0 up type can bitrate 500000

echo "[setup_can] /dev/ttyUSB0 권한 설정..."
chmod 666 /dev/ttyUSB0

echo "[setup_can] 완료."
