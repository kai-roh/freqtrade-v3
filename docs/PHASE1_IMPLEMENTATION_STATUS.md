# Phase 1 구현 상태

기준일: 2026-09-03 KST

## 판정

Phase 1의 자격증명 없이 구현 가능한 로컬·결정론적 범위는 완료됐다. 주문 제출은
계속 비활성화되어 있으며, Binance Demo 자격증명과 실제 계정 응답이 필요한 항목은
완료로 간주하지 않는다. 따라서 이 상태는 실거래 또는 Phase 3 승격 허가가 아니다.

## 구현 완료

- 기계 판독 정책과 Demo/live 경계
- Python `3.12.12`, NautilusTrader `1.231.0`, PostgreSQL `16.14` exact pin
- `uv.lock`과 lock hash 검증
- Binance Spot/USD-M의 분리된 Demo client 구성
- 14개 테이블 PostgreSQL 순방향·역방향 migration
- fee snapshot이 없으면 항상 0 target을 내는 주문 없는 캐리 스캐너
- intent 필드, 비용 원장, leverage, quote SLA, 노출과 예산을 검사하는 독립 리스크 계층
- idempotent command/fill/transfer 원장 계약
- internal transfer를 포함한 21개 상태 전이와 6개 불변식
- 주문을 내지 않는 restart recovery
- 13개 결정론적 장애 시나리오와 quote/hedge SLA 계산
- V2 일별 수익률의 ACF/Ljung-Box 의존성 진단과 fee-only bootstrap 문서 보완

## 의도적으로 보류

다음 항목은 자격증명 또는 실거래 시장 미시구조가 없으면 증명할 수 없다.

- Binance Demo Spot/USD-M account와 instrument snapshot
- 현재 계정의 commission tier, BNB 할인, leverage와 margin mode
- Demo의 post-only reject, partial fill, cancel, reconnect, recovery 배관
- Binance Demo에서 universal internal transfer가 실제 지원되는지 여부
- 실제 queue position, fill rate, adverse selection과 live hedge latency
- Phase 1E의 50회 이상 합성 주문 시도 및 관측 percentile

Demo에서 얻는 hedge latency와 abort 빈도는 실제 경쟁을 포함하지 않는 하한이다.
정책 prior와 운영 SLA를 교체하는 근거는 Phase 3 소액 실거래 이후에만 생긴다.

## 문서 보완 과정의 수정

1. 기대 순수익 식에 성공 에피소드의 청산 비용을 포함했다.
2. 확인되지 않은 Binance Spot 2 bps 가정을 제거했다. fee 값은 credentialed
   mainnet account query 전까지 `null`이며 scanner는 관측 전용이다.
3. Demo의 abort 빈도로 `p_abort` prior를 교체하지 않도록 Phase 3 이후로 미뤘다.
4. direct submit 경로와 transfer 경로를 모두 유지하면 상태 전이는 20개가 아니라
   21개다.
5. 일별 자기상관은 “무의미”가 아니라 “현재 표본에서 유의한 의존성이 검출되지
   않음”으로 표현을 낮췄다.

## 완료 기준

현재 코드 완료는 아래 검증으로 판정한다.

- 전체 단위/회귀 테스트
- Ruff lint와 format check
- NautilusTrader adapter config import/construction
- PostgreSQL migration up/down round trip
- Linux ARM64 execution image build와 order-free smoke

자격증명 기반 항목은 별도 evidence 파일이 만들어질 때까지 미완료로 남긴다.

## 2026-09-03 검증 결과

- 전체 테스트: `172 passed`
- Ruff lint/format: 통과
- order-free import smoke: NautilusTrader `1.231.0`, psycopg `3.3.5`, Demo client 2개
- Linux ARM64 image build/smoke: 통과, 로컬 manifest digest
  `sha256:656af9b6f8e7797d8743cf4330af09a19763f4e732c6584e75956630a1252468`
- PostgreSQL migration: `0 → 14 → 0 → 14` 테이블 왕복 통과
- 결정론적 fault replay: 13/13 통과

로컬 manifest digest는 이 머신의 재현 증거다. Oracle Tokyo 배포 manifest에는
registry에 push된 digest를 별도로 기록해야 한다.
