# Phase 1 구현 상태

기준일: 2026-09-15 KST (아래 과거 기록은 당시 상태)

## 현재 진행 요약

이 요약은 2026-09-15 실행 증거와 마지막 계정 GET에 근거한다. 문서 업데이트를
위한 재주문·서비스 재시작은 하지 않았다.

| 영역 | 확인된 진행 | 아직 남은 것 |
|---|---|---|
| Phase 0 | 기준선·비용/재현성 기반과 V2 분석 결과 확보 | Phase 1 경제성 승인과는 별개 |
| 1A 실행 환경 | 고정 버전 ARM64 이미지, Demo 인증·실시간 연결, 커밋/이미지 추적 | 장기 운전 검증 |
| 1B 원장·리스크 | PostgreSQL, 독립 위험 프로세스, 실제 체결 4건 대사, migration 0007 | 잔량 소유권을 보존하는 다음 에피소드 정책 |
| 1C 스캐너 | 주문 없는 스캐너와 비용 미확인 시 거부 경로 구현 | 정상 경제적 진입 게이트 충족; 합성 진입으로 대체 불가 |
| 1D 집행·복구 | 실제 진입·헤지·선물 종료, 수정 배포 후 현물 종료 확인 | 무중단 완료, 작업 중 주문 취소·부분체결·재접속 복구 실환경 검증 |
| 1E 관측 | 실제 스트림·REST·오류 및 복구 증거 확보 | 반복 에피소드, 재시작·장애 주입, SLA 집계, 1주 관측 |
| Phase 2 | 이번 작업에서 착수·승격하지 않음 | Phase 1 종료 게이트 검토 후 결정 |

**마지막 확인 상태:** 자동 실행기 중단, 선물 `0 BTC`, 미체결 주문 `0`, 활성 명령 `0`,
현물 잔량 `0.00000715 BTC`, intent `ABORTING`, 중단 사유 `DUST_REMAINS`.
미해결 recovery `0`, 적용된 fill inbox `4`다. 잔량은 미설명 대사 오류가 아니라
수수료·최소 주문 단위로 설명되는 소유 자산이며, 그렇다고 정확한 flat은 아니다.

### 다음 작업 순서

1. 잔량 처리 정책·원장·진입 가드를 함께 설계한다. 기존 BTC와 전략 소유분을
   구분하고, 기준 잔고 초기화나 허위 CLOSED 없이 다음 에피소드 허용 조건을 정한다.
2. IOC 미체결/부분체결, 취소 응답 유실, 재접속·재시작을 실제 Demo에서 검증한다.
   확인되지 않은 명령 재전송 금지와 close-only 인수 이력을 유지한다.
3. Telegram 전달 결과를 실행 증거에 기록하고, 단일 에피소드 제한과 종료 조건을
   검토한 뒤 반복 실행기로 확장한다. 현재 파일은 전송 시도만으로 전달을 증명하지 않는다.
4. [1주 관측 계획](PHASE1_WEEK_RUN.md)의 기준으로 반복·재시작·장애·비용·SLA를
   집계한다. 주문 4건을 에피소드 4회 또는 Phase 1E 완료로 세지 않는다.

### 검증 및 버전

- 마지막 코드 검증: 실제 로컬 PostgreSQL을 포함한 `382 passed`, Ruff lint/format 통과.
  이번 문서 수정에서 이 테스트를 재실행한 것은 아니다.
- 최초 실행: `3f0da66`, 태그 `phase1-demo-auto-20260915`.
- 시간 정밀도 수정·close-only 복구: `96dde03`, 태그 `phase1-demo-auto-recovery-20260915`.
- 실행 증거 기록: `6c2dfea`. 문서 커밋과 서버에서 실행한 이미지 버전은 구분한다.
- [실행·복구 상세](PHASE1_DEMO_AUTO_RUNBOOK.md),
  [최종 계정 확인](../evidence/phase1/demo-auto-final-account-20260915.json).

## 2026-09-15 자동 실행 연결

**실제 실행 결과:** Oracle에서 Demo 현물 매수 → 선물 숏 → 300초 후 선물 종료를
자동 실행했다. 종료 체결의 스트림 timestamp가 REST보다 1 microsecond 빨라 대사가
멈췄고, 원본 inbox로 검증한 정밀도 정규화 수정 후 close-only 버전 인수로 현물 매도까지
실행했다. 총 주문 4건이 모두 FILLED/OBSERVED이며 선물은 0, 활성 명령은 0이다.
현물 `0.00000715 BTC`가 남아 `ABORTING/DUST_REMAINS`를 유지하고 프로세스는 종료했다.
무중단 한 사이클, 정확한 flat, 1주 연속 가동, Phase 1E 완료는 **아니다**.
초기 실패와 복구 보고서를 각각 보존했다:
`evidence/phase1/demo-auto-initial-20260915.json`,
`evidence/phase1/demo-auto-recovery-20260915.json`.

- 실제 PostgreSQL·독립 위험 프로세스 기반으로 진입, 수수료 차감 헤지,
  reduce-only 선물 종료, 이번 에피소드 소유 현물만 매도하는 경로를 연결했다.
- migration 0007은 진입 전 BTC 기준 잔고와 영속적 종료 요청을 저장한다.
  재시작 시 종료 중인 포지션을 다시 헤지하지 않는다. dust는 CLOSED가 아니다.
- `scripts/run_phase1_demo_auto.py`는 명시적 Demo engineering 진입 한 회,
  약 220 USDT, 300초 보유 후 종료를 수행한다. 단일 실행 프로세스 잠금과
  manifest당 재진입 금지, IOC 명령 횟수 제한을 적용한다.
- 이 합성 트리거는 수익성 승인과 별개다. 정상 캐리 비용/호가 나이 게이트는
  바꾸지 않았다. receive-gap 2초와 IOC 10 bps는 시험 안전 상한이지 실측 SLA가 아니다.
- 스트림과 제어 DB 연결을 분리한다. 체결과 REST의 합계가 일치하기 전에는
  후속 주문을 내지 않는다. 미확인 주문을 재전송하지 않는다.
- 로컬 회귀 검증과 실제 서버 주문 결과는 구분한다. 실제 체결이 발생했지만
  실패·재배포를 포함했으므로 정상적인 연속 운전이나 Phase 1E 완료로 승격하지 않는다.
- 한 주 무인 반복, 작업 중 주문의 자동 취소·복구, 장애 주입 실환경 관측은
  이번 단일 자동 사이클의 성공과 별도다. dust/오류 시 자동 추가 진입은 중지한다.

## 과거 판정 — 2026-09-09 당시

Phase 1의 로컬·결정론적 범위와 Binance Demo Spot·USD-M 계정 인증은 완료됐다.
2026-09-08 신규 Demo 키의 인증과 Mainnet 거부를 확인했다. Spot 주문 검증 API는
통과했으나 USD-M의 HTTP 200 응답은 비어 있는 주문 필드여서 판정을 보류했다.
사용자의 모의자금 준비 후 Demo Futures 사용 가능 USDT 300 이상을 확인했고,
BTCUSDT 무포지션·미체결 주문 0 상태에서 격리마진·2x로 설정 후 재조회했다.
매칭 엔진에 제출하는 주문 경로는 계속 비활성화되어 있다. 따라서
이 상태는 실거래 또는 Phase 3 승격 허가가 아니다.

## 초기 구현 완료 항목 — 이후 추가분은 상단 참조

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

## 초기 보류 항목 — 현재 잔여 범위는 상단 참조

아래 항목은 아직 구현/통합 검증이 남아 있다. Demo 자격증명과 자금 부족은
더 이상 보류 사유가 아니다. 실제 시장 집행 품질만 Phase 3의 별도 검증 대상이다.

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

## 2026-09-08 신규 Demo 키 인증 및 주문 검증

사용자가 기존 실계정 키를 `BINANCE_API_*`로 유지하고 별도 신규 키를
`BINANCE_DEMO_API_*`로 등록했다. 최신 로컬 두 키 쌍을 SSH 표준입력으로만
Oracle의 보호된 `.env`에 병합했고 양쪽 파일 권한은 `0600`이다.
이전 키 폐기는 요청하지 않으며 Mainnet 주문 권한을 새로 부여하지 않는다.

| 검사 | 결과 |
|---|---|
| 신규 Demo 키 → Demo Spot·USD-M account | 양쪽 HTTP 200, 계정 응답 구조 확인 |
| 신규 Demo 키 → Mainnet Spot·USD-M account | 양쪽 HTTP 401, -2015 |
| 일반 Binance 키 → Mainnet account | 유효, 수수료 조회 성공 |
| Demo Spot LIMIT_MAKER `/api/v3/order/test` | HTTP 200, 빈 JSON 객체로 검증 통과 |
| Demo Futures GTX `/fapi/v1/order/test` | HTTP 200, symbol/type/side/수량 등이 빈 템플릿: 의미적 검증 보류 |
| Demo Spot USDT | 300 USDT 이상 사용 가능 |
| Demo Futures USDT | 사용 가능 잔고 0 |
| Demo BTCUSDT 선물 | CROSSED, 20x, One-way; 열린 주문·포지션 0 |

`/order/test`는 매칭 엔진에 주문을 보내지 않는다. HTTP 200이나 주문 형태의
응답을 체결 증거로 취급하지 않는다. 가격·수량은 실행 시 공개 호가 및 tick/step으로
계산하며, 테스트 도구는 Demo host 두 개와 테스트 endpoint만 호출할 수 있다.
리다이렉트는 거부하고 키·잔고·주문 ID는 결과에 기록하지 않는다.

선물 Demo 자금은 Binance Demo UI의 Assets → Futures → Reset 경로로 준비해야
한다. 공식 문서에서 확인한 경로는 UI이며 이번 구현에는 잔고 초기화 API가 없다.
실제 주문 시험 전에 2x 이하 레버리지, 자금, 실행 이미지·원장·리스크 조건도
충족해야 한다. 이번 REST 진단은 Nautilus node start/stop 또는 1D/1E 통과 증거가 아니다.

증거:

- `evidence/phase1/binance-connectivity-2026-09-08.json`
- `evidence/phase1/binance-mainnet-fees-2026-09-08.json`
- `evidence/phase1/demo-order-validation-2026-09-08.json`

공식 근거:

- [Binance Demo 사용 및 자금 초기화](https://www.binance.com/en-NZ/support/faq/detail/9be58f73e5e14338809e3b705b9687dd)
- [Spot Test new order](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade)
- [USD-M Test Order](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)

검증: 전체 `193 passed`, Ruff lint/format 통과, Oracle ARM64 Python 3.12에서
실제 GET 및 Demo `/order/test` 진단 수행. Nautilus 주문·체결·재시작 대사는 미검증이다.

## 2026-09-11 연결 계층 검증 완료 — Phase 1 전체는 진행 중

- 실제 PostgreSQL 원장과 별도 위험 검사 프로세스를 연결했다. migration checksum,
  중복 체결 차단, 역순 주문 상태 방어, 최신 위험 거부, 오래된 요청 거부를 검증했다.
- fixture 관측 → 비용 원장 → 위험 거부 → CLOSED 통합 테스트를 실제 DB와
  subprocess에서 통과했다. 주문 명령은 생성하지 않았다.
- Oracle ARM64의 고정 Nautilus 1.231.0에서 Binance Demo Spot·Futures 동시 연결,
  private stream 구독, 계정 2개·상품 2개 및 venue별 계정 매핑을 확인했다.
- 기본 Spot HMAC 인증 실패를 signed subscription 호환 경로로 해결했다.
  의도적 종료 시 재구독하는 경로도 차단하고 원격에서 재검증했다.
- 검증 결과: **243 tests passed**, PostgreSQL 통합 포함·skip 없음,
  Ruff lint/format 및 diff whitespace 검사 통과.
- 이번 진단의 매칭 엔진 주문은 **0건**이다. Mainnet 주문이나 실자본 투입은 없다.

증거: `evidence/phase1/node-smoke-hmac-2026-09-11.json`.
공개 관측과 이전 계정 준비 증거는 각각 `public-market-2026-09-09.json`,
`demo-account-preparation-2026-09-08.json`이며 현재 시점의 잔고/호가로 재사용하지 않는다.
원격 검증은 기존 고정 이미지에 소스를 읽기 전용으로 연결한 진단이다.
검증된 새 불변 이미지의 운영 배포나 실시간 전체 주문 흐름 완료를 뜻하지 않는다.

남은 핵심 작업은 원장·최신 위험 승인·Nautilus 주문 제출의 단일 gateway,
실시간 호가 시각 기반 SLA, 두 레그 부분체결/취소/재시작 대사, 실제 Demo
50회 에피소드·3회 재시작 및 Phase 1E 관측기간이다. 신규 호환 계층의
네트워크 장애 후 복구도 이 시험에서 확인해야 한다.
상세 절차와 증거 경계는 `docs/PHASE1_INTEGRATION_RUNBOOK.md`를 따른다.

## 2026-09-13 Phase 1D 전송·체결 복구 기반 추가

이번 변경은 로컬 구현 및 PostgreSQL 통합 시험이다. Oracle 배포, Demo 주문 제출,
실시간 실행 callback 연결은 하지 않았다. Phase 1 전체는 여전히 미완료다.

- `dispatch.py`: 전송 시도 예약을 먼저 commit하고 command당 재전송을 차단한다.
  최신 승인·호가 나이·상태를 재확인하며, 단순 enqueue를 거래소 성공으로 취급하지 않는다.
  두 DB connection이 동시에 요청해도 한 번만 예약되는 것을 검증했다.
- 고정 Nautilus 주문 객체 생성: canonical/runtime ID, client ID, post-only를 보존한다.
  아직 전송 gateway가 아니며, runtime의 주문 금지 검사를 변경하지 않았다.
- `fill_ingestion.py`: 실제 Nautilus 자료형의 fixture를 DB에 반영해 부분체결,
  중복·역순 이벤트, 취소 후 늦은 체결, 수수료 중복 방지를 검증했다.
- `fill_inbox.py`: 정규화 체결 데이터를 처리 전에 보존한다. 초과 체결 등 불일치는
  BLOCKED/incident로 남기고 신규 예약을 차단한다. 재시작 후 저장된 receipt를 재처리한다.
- `record_order`: 첫 upsert도 command 잠금으로 직렬화하고 command/client ID 및 수량을 검증한다.
- `quote_timing.py`: 현물 호가의 합성 `ts_event=ts_init`을 0ms 측정으로 오인하지 않도록
  원문 시각 기반 계산을 추가했다. 실제 스트림 hook과 장시간 표본 수집은 미완료다.

검증: **272 tests passed**, 실제 PostgreSQL 통합 포함·skip 없음.
Ruff lint/format 및 diff 검사 통과. 이번 시험을 실제 Demo 체결 에피소드로 계상하지 않는다.

다음 순서는 (1) 실시간 이벤트/호가 수신과 inbox consumer 연결,
(2) 실행 이미지·정책·수수료·위험 요청을 정확한 주문 payload에 결합한 gateway,
(3) 두 레그 cancel/hedge 및 거래소 조회 기반 복구,
(4) Demo 반복 시험과 Phase 1E 관측이다. 정책의 미측정 호가 SLA와 오래된 fee snapshot을
임의 값으로 대체해 주문을 활성화하지 않는다.

## 2026-09-14 실시간 원장 연결 원격 검증

- 전용 PostgreSQL을 Oracle에 구성했다. 외부 포트는 공개하지 않았고 기존
  `freqtrade_kai` 컨테이너는 변경하지 않았다. DB 자격증명은 별도 0600 파일에 둔다.
- `demo_node.py`와 `demo_collector.py`가 현물·선물 스트림을 실제 원장에 연결한다.
  수집기는 주문 HTTP 경로를 별도로 차단한다. 체결 callback은 durable inbox에
  연결했으나 **실제 체결 이벤트 수신은 아직 0건**이며 해당 부분은 fixture 검증만 있다.
- 60초 수집: 현물 55건, 선물 38건 저장. 이번 진단 세션 누계는 현물 75건,
  선물 51건이다. 현물 exchange age는 전부 NULL, 주문 명령·체결은 각각 0건이다.
- 배포 경로에서 발견한 macOS resource-fork migration 오인식과 실행 중인
  event loop를 dispose하는 종료 오류를 수정하고 회귀 테스트를 추가했다.
- Demo 계정 재조회: 양쪽 시험자금, 격리마진, 2배 이하, 선물 flat,
  BTC 미체결 주문 없음 조건 모두 통과. Mainnet fee는 GET으로 갱신했다.
- Telegram의 `[DEMO][PHASE1]` 연결 시험 알림 전달을 확인했다.
- 검증: **289 tests passed**, 실제 PostgreSQL 통합 포함·skip 없음,
  Ruff 및 diff whitespace 검사 통과.

증거: `evidence/phase1/demo-stream-2026-09-14.json`,
`demo-readiness-2026-09-14.json`, `binance-mainnet-fees-2026-09-14.json`.
이는 고정 의존성 이미지와 임시 소스를 이용한 제한 시간 진단이며 거래 배포가 아니다.
전용 DB는 증거 보존을 위해 남아 있고 수집기는 종료됐다.

**Phase 1 전체 및 일주일 자동매매는 아직 시작/완료되지 않았다.**
다음 필수 연결은 payload-bound 독립 위험 승인 → durable claim → Demo 제출,
두 레그의 제한된 취소·헤지·종료와 거래소 조회 기반 재시작 대사다.
주문 gateway가 없는 상태에서 `orders_enabled`를 켜거나 미측정 경제성 게이트를
우회하지 않는다. 합성 시험은 별도 engineering-only 정책으로 명시하고
수익성·실전 체결 품질의 증거와 분리해야 한다.

## 2026-09-14 실제 Demo 주문 접수·취소 확인

사용자 명시 요청에 따라 별도의 단발성 REST probe를 실행했다.
현물·선물 각 1건, **매칭 엔진 실제 주문 2건**을 접수하고 취소·재조회했다.
현물 주문 `64634141675`, 선물 주문 `28585069232` 모두 CANCELED/체결 0.
미체결 BTC 주문 없음, 선물 flat, BTC 재고 변동 없음 및 Telegram 전달을 확인했다.

현물은 취소 직후 조회 지연으로 첫 결과가 NEW여서 후속 제출을 차단했다.
추가 POST 없이 GET 기반 대사로 해결했고 최초 실패 증거를 보존했다.
고정 이미지에서 실행했으며 진단 컨테이너는 종료됐다. 기존 봇은 변경하지 않았다.
검증: **301 tests passed**, PostgreSQL 포함, Ruff 통과.

이는 **Nautilus 자동매매 runner가 아닌 별도 제한 REST 주문 시험**이다.
실제 체결 에피소드·부분체결 헤지·재시작 복구·일주일 운영은 미완료이며,
전략의 주문 금지 정책도 유지된다. 상세 결과와 이미지 SHA는
`docs/PHASE1_MATCHING_PROBE.md`에 기록했다.

## 2026-09-15 주문 연결·복구 코드 충돌 정리

- 독립 위험 프로세스와 manifest/config 정책 해시를 결합한 진입 gateway를 추가했다.
  양 레그는 같은 BTC 수량으로 평가하고 위험 명목은 큰 쪽을 사용한다.
  현물 한 레그만 제출하며 선물은 pending으로 반환한다. 접수 결과가 불명확하면
  UNKNOWN을 기록하고 주문 활성화를 해제한다. 이는 완성된 2-leg runner가 아니다.
- 잘못된 검토시각을 자동 수정하거나 지갑 부족을 통과시키지 않는다.
  현재 경제성 정책의 미측정 Spot exchange age와 불완전 비용은 계속 진입 거부다.
- `rest_recovery.py`는 GET 전에 PENDING 증거를 커밋하고 주문→체결→주문 재조회를
  검증한다. Futures buyer/maker 필드, canonical fill key, 동일 체결 중복 제거,
  전체 체결 수량 대사, terminal 주문에 한한 command 비활성화를 처리한다.
  오류가 해결돼도 최초 BLOCKED snapshot/error와 해결 receipt 연결은 보존한다.
- 복구 증거 등록과 dispatch 입장은 동일 PostgreSQL advisory transaction lock을 쓴다.
  PENDING/BLOCKED 복구 증거가 있으면 신규 제출이 거부된다.
- 순수 두 레그 계획기는 양쪽 거래소 잔고 증거를 필수로 요구한다. 수수료 차감 후
  소유한 Spot만 계산하며 최소 주문 미만 잔량이나 sub-lot 불일치를 flat으로 숨기지 않는다.

검증: **340 tests passed**, 실제 로컬 PostgreSQL 포함·skip 없음.
변경 파일 Ruff 및 diff whitespace 검사 통과. 서버 연결/기존 컨테이너 상태만
조회했으며, 이 변경은 아직 Oracle 실행 이미지로 배포하거나 신규 Demo 주문으로 검증하지 않았다.

### 자동 운영을 막는 남은 실행 연결

1. 첫 레그의 최종 체결·수수료에 맞춰 pending 선물 수량을 재평가하고 새로운 위험
   승인을 받는 coordinator. 기존 pending 수량을 그대로 재전송하면 안 된다.
2. 위험 축소용 IOC/reduce-only 종료 gateway 및 부분체결/취소 timeout 처리.
   일반 entry dispatch는 Spot BUY / Perp SELL만 허용하므로 종료에 재사용할 수 없다.
3. 기동 시 원장·계좌 대사, 단일 실행자 잠금, 종료/장애 알림과 반복 실행 lifecycle.
4. 합성 데모 시험의 별도 engineering-only 정책: receive-gap을 exchange age로
   둔갑시키지 않고, 경제성 승인을 받았다는 기록도 남기지 않는다.
5. 고정 이미지에서 실제 두 레그 진입→종료→재시작 검증을 거친 후 일주일 관측 시작.

**자동매매 및 Phase 1E 일주일 운영은 아직 시작하지 않았다.**
