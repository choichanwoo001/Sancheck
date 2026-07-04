# 레거시 taste-analysis 파이프라인 (제거됨)

제품 축의 “취향” 기능은 **하이브리드 추천**(`ai/hybrid_recommender/`)으로 통일되었다.  
구현은 **업그레이드** 관계이며, 아래 **클러스터링 기반** 파이프라인은 코드베이스에서 삭제되었다.

## 삭제 전 구조 (요약)

- **엔트리**: `ai/main.py` — CLI로 ISBN 목록 또는 `--random` 정보나루 샘플 도서 수집.
- **모듈** (`ai/taste_analysis/`, 제거됨):
  - `library_api.py` → **`ai/library_api/`** 로 이동 (정보나루 API만 유지).
  - `embedding.py` — 키워드 OpenAI 임베딩.
  - `clustering.py` — K-means / DBSCAN 클러스터링.
  - `taste_analyzer.py` — 클러스터·키워드 기반 LLM 서술형 취향 분석.
  - `visualize.py` — 클러스터 시각화.

## 제거 이유 (제품 판단)

클러스터링 단계가 **후속 LLM 단계 품질을 저하**시킬 수 있다는 판단으로, 해당 파이프라인만 제거하고 정보나루 연동(`library_api`)은 book_chat·하이브리드·스크립트에서 계속 사용한다.
