# Phase 1 구현 상태

기준일: 2026-09-03 KST

## 판정

Phase 1의 로컬·결정론적 범위와 Binance의 읽기 전용 공개 Demo 연결은 완료됐다.
V2의 보호된 자격증명을 Oracle Tokyo에서 대조한 결과 해당 키는 Mainnet 전용이며
Demo 계정 인증에는 사용할 수 없었다. 주문 제출은 계속 비활성화되어 있다. 따라서
이 상태는 실거래 또는 Phase 3 승격 허가가 아니다.

## 구현 완료

- 기계 판독 정책과 Demo/live 경계
- Python `3.12.12`, NautilusTrader `1.231.0`, PostgreSQL `16.14` exact pin
- `uv.lock`과 lock hash 검증
- Binance Spot/USD-M의 분리된 Demo client 구성
- GET 전용 allowlist와 비밀·잔고를 기록하지 않는 credential probe
- Demo 변수에 잘못 저장된 Mainnet 키를 자동 탐지하는 환경 경계 검사
- Demo Spot/USD-M 공개 ping, BTCUSDT 필터, 펀딩 응답
- Oracle Tokyo에서 credentialed Mainnet Spot/USD-M 수수료와 선물 계정 설정 조회
- 14개 테이블 PostgreSQL 순방향·역방향 migration
- fee snapshot이 없거나 24시간을 넘기면 항상 0 target을 내는 주문 없는 캐리 스캐너
- intent 필드, 비용 원장, leverage, quote SLA, 노출과 예산을 검사하는 독립 리스크 계층
- idempotent command/fill/transfer 원장 계약
- internal transfer를 포함한 21개 상태 전이와 6개 불변식
- 주문을 내지 않는 restart recovery
- 13개 결정론적 장애 시나리오와 quote/hedge SLA 계산
- V2 일별 수익률의 ACF/Ljung-Box 의존성 진단과 fee-only bootstrap 문서 보완

## 의도적으로 보류

다음 항목은 자격증명 또는 실거래 시장 미시구조가 없으면 증명할 수 없다.

- Binance Demo Spot/USD-M의 인증된 account snapshot
- Demo의 post-only reject, partial fill, cancel, reconnect, recovery 배관
- Binance Demo에서 universal internal transfer가 실제 지원되는지 여부
- 실제 queue position, fill rate, adverse selection과 live hedge latency
- Phase 1E의 50회 이상 합성 주문 시도 및 관측 percentile

Demo에서 얻는 hedge latency와 abort 빈도는 실제 경쟁을 포함하지 않는 하한이다.
정책 prior와 운영 SLA를 교체하는 근거는 Phase 3 소액 실거래 이후에만 생긴다.

## 문서 보완 과정의 수정

1. 기대 순수익 식에 성공 에피소드의 청산 비용을 포함했다.
2. 확인되지 않은 Binance Spot 2 bps 가정을 제거했다. fee 값은 credentialed
   mainnet account query 전까지 `null`로 유지했고, 조회 후 확인값으로 교체했다.
3. Demo의 abort 빈도로 `p_abort` prior를 교체하지 않도록 Phase 3 이후로 미뤘다.
4. direct submit 경로와 transfer 경로를 모두 유지하면 상태 전이는 20개가 아니라
   21개다.
5. 일별 자기상관은 “무의미”가 아니라 “현재 표본에서 유의한 의존성이 검출되지
   않음”으로 표현을 낮췄다.
6. 읽기 전용 계정 조회로 확인한 Spot 표준 수수료 10/10 bps와 USD-M 2/5 bps를
   반영했다. BNB 할인은 계정과 심볼에서 사용 가능하지만 잔고 의존성을 제거하기 위해
   비용 모델에는 적용하지 않았다. maker 진입 비용은 12 bps, 왕복은 24 bps다.
7. 수수료 snapshot은 24시간 뒤 만료되며 scanner와 risk 계층이 모두 거부한다.

## 2026-09-03 Binance 연결 검증

V2의 `/home/kai/freqtrade-v2/.env`를 Oracle Tokyo 안에서만 읽어 GET 요청만 실행했다.
키·secret·UID·잔고는 출력하거나 evidence에 기록하지 않았다.

| 항목 | 결과 | 판정 |
|---|---:|---|
| Demo Spot 공개 API | HTTP 200 | 연결 가능 |
| Demo USD-M 공개 API | HTTP 200 | 연결 가능 |
| V2 키 → Demo Spot account | HTTP 401, `-2015` | Demo 키 아님 |
| V2 키 → Demo USD-M account | HTTP 401, `-2015` | Demo 키 아님 |
| V2 키 → Mainnet Spot account/commission | HTTP 200 | Mainnet 키 유효 |
| V2 키 → Mainnet USD-M account/commission | HTTP 200 | Mainnet 키 유효 |

따라서 같은 Binance 로그인에서 발급된 키라도 Mainnet과 Demo 자격증명은 별도라는
경계를 유지한다. V2 키를 V3 Demo 실행 환경으로 복사하거나 자동 fallback하지 않는다.

Demo BTCUSDT의 공개 필터는 Spot 최소명목 5 USDT, USD-M 최소명목 50 USDT다.
정책의 3배 headroom을 적용하면 두 레그의 실제 하한은 150 USDT다. 300 USDT 캐리
레그는 필터를 충족하지만 30% 금액 ramp인 90 USDT는 USD-M headroom을 충족하지
못하므로 사용할 수 없다.

Mainnet V2 USD-M BTCUSDT 설정은 조회 시점에 `ISOLATED`, 4x였다. 이는 Phase 1의
2x 상한을 위반한다. 이번 검증은 읽기 전용이므로 레버리지나 마진 모드를 변경하지
않았으며, 향후 별도 Demo 키로 관측한 값이 2x 이하가 아니면 preflight에서 거부한다.

## 완료 기준

현재 코드 완료는 아래 검증으로 판정한다.

- 전체 단위/회귀 테스트
- Ruff lint와 format check
- NautilusTrader adapter config import/construction
- PostgreSQL migration up/down round trip
- Linux ARM64 execution image build와 order-free smoke

자격증명 기반 항목은 별도 evidence 파일이 만들어질 때까지 미완료로 남긴다.

## 2026-09-03 검증 결과

- 전체 테스트: `181 passed`
- Ruff lint/format: 통과
- order-free import smoke: NautilusTrader `1.231.0`, psycopg `3.3.5`, Demo client 2개
- Linux ARM64 image build/smoke: 통과, 로컬 manifest digest
  `sha256:b512908098e756d7e4b5b4c172320099bfd2e7bb85c48eebc5aaa9538f4417bd`
- PostgreSQL migration: `0 → 14 → 0 → 14` 테이블 왕복 통과
- 결정론적 fault replay: 13/13 통과
- Binance 공개 Demo Spot/USD-M 연결과 BTCUSDT 필터: 통과
- V2 자격증명 분류: Mainnet 유효, Demo 인증 실패(`-2015`)
- Mainnet fee snapshot: Spot 10/10 bps, USD-M 2/5 bps, 24시간 TTL

로컬 manifest digest는 이 머신의 재현 증거다. Oracle Tokyo 배포 manifest에는
registry에 push된 digest를 별도로 기록해야 한다.

연결 증거는 `evidence/phase1/binance-connectivity-oracle-tokyo.json`, 정규화된 비용
snapshot은 `evidence/phase1/binance-mainnet-fees-2026-09-03.json`에 있다.

## 2026-09-03 신규 키 재검증

신규 발급 키를 `BINANCE_DEMO_*` 변수로 Oracle Tokyo에서 검사했으나 Demo Spot과
USD-M account endpoint는 모두 HTTP 401, `-2015`를 반환했다. 같은 키를 Mainnet의
읽기 전용 account endpoint에 대조하자 양쪽 모두 HTTP 200이었다. 따라서 이 키는
Demo 키가 아니라 Mainnet에서 발급된 별도 실계정 키다. Spot account는 거래 가능
상태도 반환했으므로 Demo 실행 자격증명으로 사용하지 않으며 주문 경로는 계속
비활성화한다. Binance Demo Trading 내부의 API Management에서 발급한 키로 교체하기
전까지 credentialed Demo 시험은 보류한다.
