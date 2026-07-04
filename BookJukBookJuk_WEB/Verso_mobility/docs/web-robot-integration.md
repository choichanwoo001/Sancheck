# 웹 ↔ 로봇 연동 가이드

> 로봇 측 담당: 0jinson  
> 최종 수정: 2026-06-04

---

## 1. 연결 설정

| 항목 | 값 |
|------|-----|
| 프로토콜 | rosbridge v2 (WebSocket) |
| 기본 주소 | `ws://<로봇IP>:9090` |
| 포트 변경 | 런치 시 `rosbridge_port:=<포트>` 인자로 지정 가능 |
| 권장 클라이언트 라이브러리 | [roslibjs](https://github.com/RobotWebTools/roslibjs) |

```javascript
const ros = new ROSLIB.Ros({ url: 'ws://로봇IP:9090' });

ros.on('connection', () => console.log('로봇 연결됨'));
ros.on('error',      (e) => console.error('연결 오류', e));
ros.on('close',      () => console.log('연결 종료'));
```

---

## 2. 웹 → 로봇 (발행)

### 2-1. `/verso/waypoints` — 경유지 목록 전달

- **타입**: `std_msgs/String` (JSON)
- **발행 시점**: 세션 시작 시, 경유지 변경 시
- **동작**: 수신 즉시 기존 경로 취소 → 첫 번째 경유지부터 재시작

```json
{
  "type": "waypoints",
  "waypoints": [
    {"id": "book_001", "x": 12.3, "y": 4.5, "label": "채식주의자"},
    {"id": "book_002", "x": 8.1,  "y": 2.3, "label": "82년생 김지영"},
    {"id": "checkout", "x": 0.0,  "y": 0.0, "label": "계산대"}
  ]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `type` | string | ✓ | 항상 `"waypoints"` |
| `waypoints[].id` | string | ✓ | 고유 식별자 |
| `waypoints[].x` | float | ✓ | map frame x 좌표 (m) |
| `waypoints[].y` | float | ✓ | map frame y 좌표 (m) |
| `waypoints[].label` | string | - | 표시용 이름 |

> **주의**: 경유지 추가/삭제 시 수정된 **전체 목록**을 재전송. 부분 업데이트 없음.
>
> **방문 이력 관리는 웹 책임**: 로봇은 수신한 목록을 그대로 방문한다. 이미 방문한 경유지를 다시 포함해 전송하면 재방문한다. `waypoint_arrived` 이벤트로 완료 여부를 추적해 **미방문 경유지만** 목록에 포함할 것.
>
> **경로 순서 최적화**: 로봇이 현재 위치 기준 최근접 이웃 알고리즘으로 방문 순서를 자동 최적화한다. **단, 목록의 마지막 항목(계산대 등 종착지)은 정렬에서 제외되어 항상 마지막으로 유지된다.**

---

### 2-2. `/verso/command` — 명령

- **타입**: `std_msgs/String` (JSON)

#### stop
```json
{"type": "command", "action": "stop"}
```
현재 동작 즉시 중단. `resume` 또는 새 `waypoints` 수신 전까지 정지 유지.

#### resume
```json
{"type": "command", "action": "resume"}
```
`stop` 또는 `waypoint_arrived` 대기 상태에서 재개.

| 진입 조건 | resume 시 동작 |
|-----------|---------------|
| `stop` 명령 | 중단 전 모드로 복귀 |
| `waypoint_arrived` 대기 | 다음 경유지로 주행 |

#### set_mode
```json
{"type": "command", "action": "set_mode", "mode": "guidance"}
{"type": "command", "action": "set_mode", "mode": "escort"}
```

| mode | 동작 |
|------|------|
| `guidance` | 사람 따라가기 모드. 진행 중인 경유지 주행 취소. |
| `escort` | 웨이포인트 주행 모드. 웨이포인트가 없으면 무시됨. |

#### end_session
```json
{"type": "command", "action": "end_session", "x": -2.0, "y": 1.0}
```
모든 경유지 취소 후 지정 좌표(홈)로 복귀. 도착 시 `home_reached` + `session_ended` 이벤트 발행.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `x` | float | ✓ | 홈 위치 x 좌표 (map frame, m) |
| `y` | float | ✓ | 홈 위치 y 좌표 (map frame, m) |

---

## 3. 로봇 → 웹 (구독)

### 3-1. `/verso/status` — 로봇 상태 (1 Hz)

- **타입**: `std_msgs/String` (JSON)

```json
{
  "type": "status",
  "position": {
    "x": 12.3,
    "y": 4.5,
    "heading": 1.57
  },
  "current_waypoint_id": "book_001",
  "remaining_waypoints": 2,
  "mode": "escort",
  "is_moving": true
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `position.x/y` | float | 현재 위치, map frame (m) |
| `position.heading` | float | 현재 방향, yaw (rad) |
| `current_waypoint_id` | string \| null | 현재 주행 중인 경유지 ID. 없으면 `null` |
| `remaining_waypoints` | int | 남은 경유지 수 (현재 제외) |
| `mode` | string | `"guidance"` \| `"escort"` |
| `is_moving` | bool | 로봇이 실제로 이동 중인지 여부 |

---

### 3-2. `/verso/event` — 이벤트 (트리거 발생 시)

- **타입**: `std_msgs/String` (JSON)

```json
{"type": "event", "event": "waypoint_arrived", "waypoint_id": "book_001", "label": "채식주의자"}
{"type": "event", "event": "route_deviated"}
{"type": "event", "event": "tracking_lost"}
{"type": "event", "event": "tracking_recovered"}
{"type": "event", "event": "navigation_failed"}
{"type": "event", "event": "home_reached"}
{"type": "event", "event": "session_ended"}
```

| 이벤트 | 추가 필드 | 발생 시점 |
|--------|-----------|-----------|
| `waypoint_arrived` | `waypoint_id`, `label` | 경유지 도착. 로봇 대기 상태 진입 |
| `route_deviated` | - | 사용자가 계획 경로에서 이탈 |
| `tracking_lost` | - | 사람 추적 유실 |
| `tracking_recovered` | - | 사람 추적 재개 |
| `navigation_failed` | - | Nav2 경로 주행 실패 |
| `home_reached` | - | 홈 복귀 완료 |
| `session_ended` | - | 세션 종료 완료 (`home_reached` 직후 발행) |

---

### 3-3. `/verso/path` — Nav2 계획 경로 (경로 갱신 시)

- **타입**: `std_msgs/String` (JSON)
- **발행 시점**: 새 경로 계산 시 (1Hz 아님)

```json
{
  "type": "path",
  "poses": [
    {"x": 1.2, "y": 3.4},
    {"x": 1.5, "y": 3.8},
    {"x": 2.0, "y": 4.1}
  ]
}
```

> 좌표계: map frame (m)

---

## 4. 모드 전환 흐름

```
세션 시작
  └─▶ guidance  (사람 따라가기)
        │
        │  waypoints 수신
        ▼
      escort  (웨이포인트 순차 주행)
        │
        │  경유지 도착 → waypoint_arrived 이벤트
        ▼
      stopped (대기)
        ├─▶ resume 수신          → 다음 경유지 주행 (escort)
        └─▶ waypoints 갱신      → 새 경로로 escort
        
      모든 경유지 소진
        └─▶ guidance 복귀
        
      stop 수신 (어느 상태에서든)
        └─▶ stopped
              ├─▶ resume          → 중단 전 모드 복귀
              └─▶ waypoints 갱신 → escort
              
      end_session 수신
        └─▶ 홈 복귀 주행
              └─▶ home_reached + session_ended 이벤트
                    └─▶ guidance 복귀
```

---

## 5. 3D 맵 경로 시각화

현재 위치는 `/verso/status`에서 1Hz로 수신합니다. 지나온 경로와 남은 경로를 구분하려면 웹에서 다음과 같이 처리합니다:

**지나온 경로**: `status.position`을 누적해 직접 폴리라인으로 그림

**남은 경로**: `/verso/path`의 poses 중 현재 위치와 가장 가까운 점 이후 구간만 렌더링

```javascript
// 현재 위치와 가장 가까운 경로 점 찾기
function splitPath(poses, currentX, currentY) {
  let minDist = Infinity, splitIdx = 0;
  poses.forEach((p, i) => {
    const d = Math.hypot(p.x - currentX, p.y - currentY);
    if (d < minDist) { minDist = d; splitIdx = i; }
  });
  return {
    traveled:  poses.slice(0, splitIdx),
    remaining: poses.slice(splitIdx),
  };
}
```

> 1Hz 위치 해상도가 부족하다면 요청 시 발행 주기 조정 가능.

---

## 6. roslibjs 연동 예시

```javascript
const ros = new ROSLIB.Ros({ url: 'ws://로봇IP:9090' });

// ── 발행 ──────────────────────────────────────────────────────────────────
const waypointsPub = new ROSLIB.Topic({
  ros, name: '/verso/waypoints', messageType: 'std_msgs/String'
});
const commandPub = new ROSLIB.Topic({
  ros, name: '/verso/command', messageType: 'std_msgs/String'
});

// 경유지 전송
waypointsPub.publish(new ROSLIB.Message({
  data: JSON.stringify({
    type: 'waypoints',
    waypoints: [
      { id: 'book_001', x: 12.3, y: 4.5, label: '채식주의자' },
      { id: 'checkout', x: 0.0,  y: 0.0, label: '계산대' },
    ]
  })
}));

// 정지 명령
commandPub.publish(new ROSLIB.Message({
  data: JSON.stringify({ type: 'command', action: 'stop' })
}));

// ── 구독 ──────────────────────────────────────────────────────────────────
const statusSub = new ROSLIB.Topic({
  ros, name: '/verso/status', messageType: 'std_msgs/String'
});
statusSub.subscribe(msg => {
  const status = JSON.parse(msg.data);
  // status.position.x, status.position.y, status.mode, ...
});

const eventSub = new ROSLIB.Topic({
  ros, name: '/verso/event', messageType: 'std_msgs/String'
});
eventSub.subscribe(msg => {
  const event = JSON.parse(msg.data);
  if (event.event === 'waypoint_arrived') {
    console.log(`도착: ${event.label}`);
  }
});

const pathSub = new ROSLIB.Topic({
  ros, name: '/verso/path', messageType: 'std_msgs/String'
});
pathSub.subscribe(msg => {
  const { poses } = JSON.parse(msg.data);
  // poses: [{x, y}, ...]
});
```

---

## 7. 지도 좌표계

로봇 지도(`b2floor_edited.yaml`) 기준:

| 항목 | 값 |
|------|-----|
| 해상도 | 0.05 m/pixel |
| 원점 (x, y) | (-53.4, -19.1) m |
| 원점 기준 | 지도 이미지 좌하단 모서리 |

3D 맵 좌표 변환:
```
map_x = pixel_x * 0.05 + (-53.4)
map_y = pixel_y * 0.05 + (-19.1)
```

> 웨이포인트 및 로봇 위치 좌표는 모두 이 map frame 기준입니다.

---

## 8. 주의사항

- **별도 초기화 불필요**: 로봇이 켜지면 guidance 모드로 대기. 웹에서 데이터 전송 즉시 동작 시작.
- **waypoints 전송 = 전체 교체**: 경유지 수정 시 변경된 전체 목록을 재전송. 이미 방문한 경유지는 제외할 것 (`waypoint_arrived` 이벤트로 추적).
- **`set_mode: escort`**: 웨이포인트가 없으면 무시됨. `waypoints` 먼저 전송.
- **`waypoint_arrived` 후 자동 진행 없음**: `resume` 또는 새 `waypoints` 수신 전까지 대기.
- **경로 유효 범위**: `/verso/path`는 경로 재계산 시에만 갱신. 사용자 이탈 후 재경로 시 새 경로 수신됨.
- **연결 끊김 시**: 로봇은 마지막 상태 유지. 재연결 후 `/verso/status`로 현재 상태 확인 가능.
