# Phase 1 연결 검증과 남은 집행 작업

기준일: 2026-09-13 KST. 실자본 및 Mainnet 주문은 금지한다.

## 이번 연결 범위

- `postgres.py`: 실제 PostgreSQL 원장, checksum migration 이력, 관측/비용/위험/상태 저장.
- `risk_service.py`: spawn 방식의 별도 위험 검사 프로세스. 정책·수수료 hash와 요청 hash를
  대조하며, 타임아웃·프로세스 종료·오래된 요청·불일치 응답은 거부한다.
- `connected_flow.py`: 관측 저장 → 시나리오 비용 기록 → 위험 거부 → CLOSED의 주문 없는
  연결. `cost_ledger_complete=False`와 미확인 대사를 승인으로 바꾸지 않는다.
- `capture_phase1_market.py`: 키 없이 Demo 현물·선물 호가/필터와 Mainnet 공개 펀딩 수집.
- `run_phase1_node_smoke.py`: 실제 Nautilus start/stop 진단. 전략 없음, HALTED,
  주문·취소·수정 차단, 읽기 및 사용자 스트림 생명주기만 허용한다.

이는 2-leg 주문 서비스 완료나 Phase 1 전체 완료를 뜻하지 않는다. 연결 함수는
실제 PostgreSQL + 별도 위험 프로세스 + fixture 관측으로 검증한다. 공개 시장
수집과 거래소 노드 진단은 별도 증거이며 이를 live end-to-end 집행으로 합산하지 않는다.

## 고정 버전에서 발견한 차이

Nautilus 1.231.0의 `ExecutionEngine.register_client`는 동일 venue 두 번째 등록을
거부한다. 서로 다른 client ID만으로는 현물/선물 동시 등록이 되지 않는다.
의존성을 임의 업그레이드하거나 엔진 내부 routing map을 덮어쓰지 않고, 지원되는
client/provider `venue` 설정을 분리한다.

| 정책·원장 ID | Nautilus 내부 ID |
|---|---|
| `BTCUSDT.BINANCE` | `BTCUSDT.BINANCE_SPOT_DEMO` |
| `BTCUSDT-PERP.BINANCE` | `BTCUSDT-PERP.BINANCE_USDM_DEMO` |

변환 정의는 `adapters.NAUTILUS_INSTRUMENT_IDS` 하나다. 모르는 내부 ID는 오류다.
향후 주문/체결 어댑터도 이 경계에서 변환해야 한다. 실제 거래소는 둘 다 Binance이며
venue alias를 거래소 분산이나 자본 집중 한도 회피로 계산하지 않는다.
계정과 실행 클라이언트가 분리돼도 중앙 2-leg coordinator와 대사는 별도로 필요하다.
alias는 client 이름 및 account issuer와도 일치시킨다. 계정 2개가 캐시에 존재한다는
사실뿐 아니라 `account_for_venue` 조회 성공을 별도 게이트로 확인한다.

[최신 공식 통합 문서](https://nautilustrader.io/docs/latest/integrations/binance/)와
설치된 고정 버전의 API/구현이 다를 수 있다. 최신 문서만 보고 지원을 확정하지 않는다.

### Spot HMAC 인증 호환 경로

고정 버전의 기본 Spot `session.logon`은 현재 Demo HMAC 키로 -2028을 반환했다.
[Binance 공식 사용자 스트림 문서](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/user-data-stream)의
`userDataStream.subscribe.signature` 경로를 사용하는 선택적
`--hmac-spot-compat` 진단을 추가했다. 서명 구독 ACK와 초기 대사가 성공하기 전에는
인증 완료나 이벤트 dispatch를 허용하지 않는다. Demo·1.231.0만 허용하고 endpoint
override는 거부한다. 의도적인 unsubscribe에서 발생하는 종료 이벤트는 재구독하지 않는다.

이는 upstream private API에 의존하는 좁은 호환 계층이다. 버전 업그레이드 시 자동
승계하지 말고 회귀 검증한다. 연결 성공만으로 네트워크 단절 후 복구나 주문 이벤트
정확성이 검증된 것은 아니다. 현재 옵션은 주문 없는 진단에만 사용한다.

## 호가와 비용의 증거 경계

- Spot REST `bookTicker`에는 거래소 이벤트 시각이 없다. `market_age_ms=null`로 기록한다.
- `transport_rtt_ms`는 왕복 통신 시간이지 호가 나이가 아니다. 0ms로 치환하지 않는다.
- Futures REST 시각이 있으면 수신 시각과의 차이를 기록하되, 미래 시각은 거부한다.
- 펀딩 주기는 심볼별 `fundingInfo` 또는 세 정산 시점의 두 동일 간격에서 얻는다.
  불충분/오래된 데이터는 8시간으로 추측하지 않는다.
- 마지막 정산률을 보유기간에 확장한 값은 시나리오다. 미래 수익 예측이나 보장이 아니다.
- Demo 체결 수수료는 실제 경제성 근거가 아니다. 별도 Mainnet fee snapshot을 쓰며,
  미측정 impact/legging/requote 등의 비용은 원장에서 null로 남긴다.

## 검증 방법

개발 환경에서는 `python -m pytest`를 사용한다. PostgreSQL 테스트는 명시적으로
지정한 `PHASE1_TEST_DATABASE_DSN`에 일회성 격리 schema를 만들고 자기 schema만 제거한다.
DSN이 없으면 DB 통합 검증은 skip되므로 전체 통합 통과로 보고하지 않는다.

`run_phase1_node_smoke.py --credentials-env-file <보호된 파일> --output <결과>`는
`BINANCE_DEMO_API_KEY/SECRET`만 선택한다. 별도 진단 프로세스에서만 실행한다.
로그에 계정 응답이 노출되지 않도록 native stdout/stderr를 버리고 결과에는 상태,
허용 요청 경로, 오류 종류만 남긴다. HTTP 요청 성공은 WebSocket 구독 성공이 아니다.
코드가 고정되지 않은 진단은 `diagnostic_only=true`, `deployment_authorized=false`다.
이 진단을 주문 실행의 clean-tree/태그/이미지 게이트 우회 경로로 사용하지 않는다.

## 다음 집행 착수 조건

### 2026-09-13: 전송·체결 영속화 기본 모듈

`dispatch.py`와 migration 0003은 command당 전송 시도를 한 번만 예약한다.
전용 DB connection이 이미 transaction 안에 있으면 거부한다. 따라서 예약이 실제로
commit되기 전에 외부 전송을 시작하는 문제가 없다. 최신 승인 ID·결정 나이·승인 후
증가한 호가 나이·SUBMITTING 상태·활성 command를 확인한다.

상태 의미:

- `CLAIMED`: 전송 시도 예약이 저장됨. 프로세스 중단 후에도 재전송 금지.
- `ENQUEUED`: 로컬 제출 함수가 반환됨. 거래소 접수/체결 성공이 아님.
- `UNKNOWN`: 전송 예외. 오류 종류만 보관하고 원문에는 자격증명이 있을 수 있어 저장하지 않음.
- `OBSERVED`: 동일 client ID·제품 venue·venue order ID의 영속 주문 증거가 확인됨.

주문 조회 결과가 없다는 사실은 재전송 권한이 아니다. `OBSERVED` 역시 주문 재사용이나
2-leg 완료를 뜻하지 않는다. 재시작 시 미해결 예약을 먼저 조회하고 신규 주문을 막아야 한다.
증거가 있는 journal은 down migration으로 삭제할 수 없다.

`fill_ingestion.py`는 실제 Nautilus `OrderFilled` 자료형을 받아 command 잠금 아래
주문·체결·누적 수량을 하나의 transaction으로 반영한다. 제품 venue와 symbol별 trade ID를
함께 사용한다. 중복 이벤트는 재합산하지 않고, 늦은 부분체결은 취소 상태를 다시 열지 않는다.
Demo commission은 관측 증거로만 보존한다. Mainnet 비용 원장과 혼합하지 않는다.

`fill_inbox.py`와 migration 0004는 정규화된 `OrderFilled` 필드를 먼저 commit한다.
처리 전 재시작해도 receipt로 재처리할 수 있다. 실패 시 해당 체결 반영만 rollback하고
inbox는 BLOCKED, incident는 open으로 남긴다. PENDING/BLOCKED receipt가 있으면
dispatch 예약을 거부한다. 이는 정규화 이벤트 보관이며 원본 WebSocket packet이나
임의 `info` 메타데이터 보관이 아니다. liquidation 메타데이터의 별도 연결은 미완료다.
DB 장애 시 예외를 숨기지 않고 PENDING 기록을 유지한다. runner는 이런 예외에서도
신규 주문을 중단해야 한다.
inbox receipt 수는 수신 횟수이며 체결 수가 아니다. 재전달도 별도 receipt로 보존하여
동일 trade ID의 상충 payload를 잃지 않는다. 체결 수·수량·수수료 보고는 중복 제거된
`fills`에서 계산하고, receipt 수를 Phase 1E 에피소드 수로 합산하지 않는다.

이 모듈들은 **완성된 주문 gateway가 아니다**. 실행 runner에 연결하지 않았으며,
runtime의 주문 금지 검사를 완화하지 않았다. 실제 활성화 전 반드시 다음이 필요하다:

1. 정책·이미지·fee·wallet·instrument 검증과 독립 위험 요청을 정확한 주문 payload에 결합.
2. 예약 commit 직후 전송 전 재검증, 순차 두 레그 coordinator, bounded cancel/hedge.
3. live callback → 영속 inbox → 단일 consumer 연결. 수량 초과나 불일치는 BLOCKED로
   보존하고 재시작 시 먼저 복구한다. 직접 ingestion 함수를 호출해 오류를 삼키면 안 된다.
4. accepted/rejected/canceled 이벤트 및 거래소 조회 결과 수집. 현재는 fill 정규화 경로만 있다.
5. 새 불변 이미지·배포 검증 후 Demo 매칭 엔진 시험. 이번 단위/DB 시험은 Demo 에피소드가 아니다.

### 호가 시각 추가 제약

설치된 Nautilus 1.231.0의 `BinanceQuoteData.parse_to_quote_tick`은 원문 `T`가 없으면
`ts_event=ts_init`로 대체한다. Spot `bookTicker`의 이 값을 0ms 지연 표본으로 쓰면 안 된다.
`quote_timing.py`는 원문 시각에서만 나이를 계산하고 부재는 None, 미래 시각은 오류로 남긴다.
raw stream hook에는 아직 연결하지 않았다. 따라서 이 함수 추가만으로 호가 SLA를 측정했다고
보고하거나 현재 정책의 `maximum_quote_age_ms=null`을 바꾸지 않는다.

### 남은 종료 조건

1. 고정 버전으로 두 계정의 private stream 구독과 정상 종료를 실제 확인한다.
2. 주문 전 원장 commit, 최신 위험 승인, canonical/runtime ID 변환을 하나의
   집행 gateway로 묶는다. 현재 원장 메서드 자체는 주문 실행 권한이 아니다.
3. 이벤트 순서 역전·부분 체결·취소 실패·재시작 대사를 실제 어댑터 경로로 검증한다.
4. 거래소 이벤트 시각이 있는 호가 스트림과 수신 지연을 분리해 SLA를 측정한다.
5. Demo 50회 에피소드·3회 재시작과 관측기간을 충족한 뒤 Phase 1E 종료를 판정한다.
   fixture 테스트를 실제 Demo 에피소드로 세지 않는다.
