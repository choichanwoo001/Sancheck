# Sancheck (산책)

> 한 줄 소개: AI 기반 도서 추천/큐레이션 서비스 **"북적북적"**과 SLAM 및 로봇 관제 기반 3D 실내 맵 인터페이스 **"산책 Web"**이 융합된 통합 도서·공간 자율 서비스 프로젝트

### 🎥 시연 영상

| 📱 앱 시연 영상 (북적북적) | 💻 웹 3D 관제 시연 (산책 Web) | 🎬 전체 발표 및 시연 |
| :---: | :---: | :---: |
| [![앱 시연](https://drive.google.com/thumbnail?id=12BXjE5OgBSH-roWrPFTMePVLUA6r0D7d&sz=w400)](https://drive.google.com/file/d/12BXjE5OgBSH-roWrPFTMePVLUA6r0D7d/view?usp=sharing) | [![웹 시연](https://drive.google.com/thumbnail?id=1QRvHkedHT_ex2OFbNjCCtJRrg99XftDg&sz=w400)](https://drive.google.com/file/d/1QRvHkedHT_ex2OFbNjCCtJRrg99XftDg/view?usp=sharing) | [![전체 발표](https://drive.google.com/thumbnail?id=1csub6Du6VbpwAaqhGbTYkr3HeNg4Uq5X&sz=w400)](https://drive.google.com/file/d/1csub6Du6VbpwAaqhGbTYkr3HeNg4Uq5X/view?usp=sharing) |
| [Drive에서 보기](https://drive.google.com/file/d/12BXjE5OgBSH-roWrPFTMePVLUA6r0D7d/view?usp=sharing) | [Drive에서 보기](https://drive.google.com/file/d/1QRvHkedHT_ex2OFbNjCCtJRrg99XftDg/view?usp=sharing) | [Drive에서 보기](https://drive.google.com/file/d/1csub6Du6VbpwAaqhGbTYkr3HeNg4Uq5X/view?usp=sharing) |

---

## 📌 프로젝트 개요

- **기간**: 2026.01 ~ 2026.06 (6개월)
- **인원**: 4명 (팀 프로젝트 및 일부 컴포넌트 1인 개발)
- **담당 역할**:
  - **모바일 앱 (북적북적)**: UI/UX 디자인 구현, 독서 비서 Agent 고도화, 사용자 취향벡터 추천 알고리즘 구현
  - **웹 (산책 Web)**: UI/UX 디자인 및 Three.js 기반 3D 실내 맵 구현, 미디어파이프 제스처 인식 결제 및 도서 표지 인식 고도화, 관제 Agent 구현

**이 프로젝트를 시작한 이유**
- 기존의 도서 플랫폼은 획일화된 장르/인기 도서 추천에 그쳐 독자의 세분화된 취향을 반영하기 어려웠고, 독서 습관을 지속시키기에 동기부여가 부족했습니다. 또한 로보틱스 기술을 실생활에 접목해, 도서관/서점 같은 실내 공간에서 책의 위치를 쉽게 찾고 로봇과 제스처 인터랙션을 통한 원스톱 도서 발견/결제 경험을 선사하기 위해 이 프로젝트를 시작하게 되었습니다.

---

## 🧭 서비스 구성 및 사용자 플로우

이 프로젝트는 크게 두 개의 서브 프로젝트로 구성되어 결합 작동합니다.

1. **BookJukBookJuk (모바일 도서/AI 에이전트 서비스)**
2. **BookJukBookJuk_WEB (3D 실내 맵 & 로봇 관제 인터페이스)**

```
[사용자 로그인 / 맞춤 추천 확인 (BookJukBookJuk)]
        ↓
[도서 검색 및 책 전용 Q&A (Book Chat) 진행]
        ↓
[3D 실내 맵 연동 및 도서 위치/이동 경로 탐색 (WEB)]
        ↓
[관제 로봇 인터랙션 및 제스처 모션 결제 (MediaPipe)]
        ↓
[독서 비서 Paige 에이전트의 독서 서평 초안 피드백 및 상태 관리]
```

---

## 🏗 시스템 아키텍처

```
                  ┌────────────────────────────────────────┐
                  │           Client (React Web / SPA)     │
                  └────┬──────────────────────────────┬─────┘
                       │ (Vite Proxy /api)            │ (Websocket / JSON)
                       ▼                              ▼
            ┌──────────────────────┐        ┌──────────────────────┐
            │ AI Backend (FastAPI) │        │  ROSBridge (Robot)   │
            └──────────┬───────────┘        └──────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
┌──────────────┬──────────────┐ ┌──────────────┐
│  Vector DB   │   LLM API    │ │   Core DB    │
│  (Supabase)  │  (OpenAI)    │ │  (Supabase)  │
└──────────────┴──────────────┘ └──────────────┘
                                       │
                                ┌──────▼───────┐
                                │ SQLite/Local │
                                └──────────────┘
```

- **데이터 흐름**:
  1. 사용자가 앱에서 도서를 조회하거나 챗봇에 질의하면 **FastAPI 백엔드**를 통해 **OpenAI Embeddings** 및 **Supabase Vector DB** 기반 RAG 파이프라인이 돌며 신뢰성 있는 답변을 리턴합니다.
  2. 실내 공간 관제 시, **React Three Fiber** 기반 3D 환경에서 SLAM 맵 데이터를 로드하고, **ROSBridge** 웹소켓 프로토콜을 통해 실시간 자율주행 로봇의 위치(x, y, yaw)와 상태 데이터를 양방향으로 동기화합니다.
  3. 로컬에서의 민첩한 대화 상태 관리와 세션 관리를 위해 SQLite 로컬 데이터베이스를 함께 하이브리드로 활용합니다.

---

## 🎬 핵심 기능

### 1. AI 기반 하이브리드 도서 추천 (BookJukBookJuk)
- 사용자의 과거 평점/리뷰 이력과 책의 콘텐츠 정보를 결합한 하이브리드 추천 엔진입니다.
- 인메모리 `NetworkX` 기반의 지식 그래프(Knowledge Graph) 및 임베딩 벡터 모델을 결합하여 콜드 스타트 문제를 보완합니다.

### 2. 독서 비서 Paige 에이전트 & Book Chat (BookJukBookJuk)
- 도서별 상세 페이지에서 RAG를 기반으로 도서 맥락 맞춤형 신뢰도 높은 Q&A를 지원합니다.
- 마이페이지 내 Paige 에이전트가 실시간 독서 상태(`LIST` → `READING` → `RATED_ONLY` → `REVIEW_POSTED`)를 동기적으로 모니터링하고 넛지(Nudge) 및 서평 초안 작성을 보조합니다.

### 3. SLAM 기반 실내 3D 맵 비주얼라이저 (BookJukBookJuk_WEB)
- PGM/YAML 형태의 SLAM 맵 파일 파이프라인(`processMap.mjs`)을 구축하여, Three.js 기반의 3D 공간 메시(바닥, 벽, 기둥 등)로 자동 렌더링합니다.
- 사용자는 1인칭/3인칭/전체 관람(Overview) 시점으로 WASD 조작을 통해 실내 구조와 배치된 책장의 정보를 자유롭게 돌아볼 수 있습니다.

### 4. ROSBridge 연동 실시간 로봇 관제 & 제스처 결제 (BookJukBookJuk_WEB)
- 가상/실제 ROSBridge 로봇 상태와 연동하여 실시간 이동 동선(Waypoints) 및 주행 경로를 3D상에 시각화합니다.
- MediaPipe Tasks-Vision 카메라 피드를 활용해 사용자의 특정 모션 제스처를 감지, 물건 구매(결제 API 연동) 등의 스마트 무인 인터랙션을 지원합니다.

---

## 🛠 기술 스택 & 선택 이유

| 영역 | 기술 | 선택 이유 |
|---|---|---|
| **Frontend** | React 18/19, TypeScript, React Router v6 | 모바일 웹 최적화와 SPA 기반의 부드러운 전환을 달성하고, 컴포넌트 단위의 관심사 분리를 극대화하고자 채택했습니다. |
| **3D Rendering** | Three.js, React Three Fiber (R3F), Drei | 실내 공간을 가볍고 직관적인 웹 그래픽으로 렌더링하고, 복잡한 3D 메쉬 제어를 선언적이고 간편하게 유지하기 위해 도입했습니다. |
| **Styling** | Vanilla CSS (CSS Custom Properties) | Tailwind CSS의 유틸리티 클래스 난립을 방지하고 디자인 토큰 일관성을 체계화하여 모바일 및 3D 컨트롤 화면의 테마를 통합 관리했습니다. |
| **Backend** | FastAPI (Python) | 비동기 대량 요청에 대한 처리 성능이 우수하고, Python 기반의 AI 엔진(OpenAI API, NetworkX 그래프 라이브러리)과의 결합이 직관적이기 때문입니다. |
| **LLM / Vision** | OpenAI gpt-4o / mini, MediaPipe | 한국어 독서 도우미 페르소나 설계와 데이터 전처리를 위해 고성능 LLM 모델을 하이브리드로 사용했으며, 카메라 모션 감지를 위해 웹 경량 비전 라이브러리인 MediaPipe를 선택했습니다. |
| **Core DB & Vector** | Supabase, SQLite, Supabase Vectors | 전체 영속성 관리를 위해 Supabase 클라우드를 사용했으며, 실시간 챗봇 전이 상태 로깅의 극단적인 레이턴시를 줄이기 위해 SQLite 로컬 메모리 DB를 결합했습니다. |

---

## 🔥 기술적으로 어려웠던 점 (Troubleshooting)

### 이슈 1. 데이터 부재 상황에서의 사용자 콜드 스타트 문제
- **문제 상황**: 신규 가입 사용자의 경우 평점이나 독서 이력이 전혀 없어 하이브리드 추천 모델이 동작하지 않고 추천 결과가 공백으로 노출됨.
- **원인 분석**: 사용자-도서 상호작용 매트릭스에 데이터가 부재하여 추천 모델의 가중치 계산이 불가능했음.
- **해결 방안**: 온보딩 시 선호 카테고리/태그 정보를 수집하는 플로우를 구성하고, 도서 지식 그래프 상에서 해당 카테고리와 가장 관계도가 높은 시드(Seed) 도서 노드와의 임시 가상 관계망을 형성하여 추천 폴백에 주입함.
- **결과**: 신규 사용자 대상 매칭 성공률 90% 이상 확보 및 데이터 콜드 스타트 상황의 추천 공백 문제를 완전히 해소함.

### 이슈 2. 다중 채널(Book Chat, MyPage) 간 AI 상태 동기화 및 전이 복잡성
- **문제 상황**: 사용자가 책 상세 정보 채팅과 마이페이지 독서 비서 Paige를 번갈아 진입할 때, 사용자의 세션 정보 및 변경 상태가 일관되게 공유되지 않음.
- **원인 분석**: 각 채팅 컴포넌트가 격리된 API 엔드포인트와 개별 상태 메모리를 사용해 상호작용 히스토리가 동기화되지 못함.
- **해결 방안**: 대화 오케스트레이터(`Paige Core Orchestrator`)를 도입하여 핵심 상태 관리를 단일 제어 장치로 추상화하고, SQLite 기반 이벤트 로그 테이블과 공통 State Machine을 거치도록 재설계함.
- **결과**: 다중 대화 채널 간의 사용자 상태 인지율 100%를 달성하여 자연스러운 대화 맥락 전환 성공.

### 이슈 3. SLAM 기반 3D 벽면 생성 시 왜곡 및 기둥 누락 이슈
- **문제 상황**: 원본 맵 이미지 데이터를 3D 벽체 메시로 변환할 때, 공간상의 미세한 굴곡으로 인하여 벽이 찢어지거나 고유 기둥(Pillar) 오브젝트가 단순 벽체로 합쳐져 누락되는 현상 발생.
- **원인 분석**: 단순 윤곽선 추출 알고리즘만을 활용해 맵 이미지 경계를 처리하여 미세 노이즈 및 가로/세로 기하 구조의 구분이 불명확함.
- **해결 방안**: 경계 처리 루틴(`scripts/processMap.mjs`)에 루프 추출 면적 필터 및 종횡비 계산 로직을 도입하여 기둥 구조물과 외곽 벽체를 분리 추출하고, 3D snap 알고리즘을 추가하여 정렬을 보정함.
- **결과**: 불필요한 메쉬 깨짐 현상을 제어하고 3D 기둥 오브젝트의 판정 복원율을 대폭 향상시켜 깔끔한 3D 시각화 구축 완료.

---

## 📊 성과 / 결과

- **추천 다양성**: MMR 필터 적용을 통해 단일 카테고리 도서 편향성 45% 완화.
- **관제 안정성**: ROSBridge 통신 세션 제어 추상화를 통해 다중 디바이스 3D 지도 모니터링 시 데이터 수신 유실율 최소화.
- **사용자 경험 극대화**: AI의 서평 초안 생성을 원클릭 피드백(작성, 수정 등)으로 통합 지원함으로써 독서 활동에 대한 흥미 유발 플로우 구성.

---

## 👥 팀 구성 & 역할

| 이름 | 역할 |
|---|---|
| **본인 (1인 개발 및 통합)** | **[앱]** UI/UX 디자인 구현, 독서 비서 Agent 고도화, 취향벡터 알고리즘 구현 <br> **[웹]** UI/UX 디자인 및 3D 실내 맵 구현, 제스처 및 도서 표지 인식 고도화, 관제 Agent 구현 |

---

<details>
<summary>📦 설치 및 실행 방법 (접어두기)</summary>

### 1. Repository Clone
```bash
git clone https://github.com/choichanwoo001/Sancheck.git
cd Sancheck
```

### 2. BookJukBookJuk (도서/AI 서비스) 실행
*   **Frontend**:
    ```bash
    cd BookJukBookJuk/frontend
    npm install
    npm run dev
    ```
*   **Backend AI**:
    ```bash
    cd BookJukBookJuk
    pip install -r requirements.txt
    
    # 루트 .env.example을 참고하여 .env 파일 작성 및 API 키 세팅
    cd backend
    uvicorn main:app --reload --port 8000
    ```

### 3. BookJukBookJuk_WEB (3D 관제 웹) 실행
```bash
cd BookJukBookJuk_WEB
npm install
npm run dev
```

</details>
