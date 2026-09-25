# Phase 1 구현 계획: 캐리 집행 인프라

기준일: 2026-08-25 KST

기준 태그: `phase0-baseline`

진행 현황 갱신(2026-09-15): 이 문서는 구현 기준선이며 완료 보고서가 아니다.
실제 Demo 주문 4건과 close-only 복구를 확인했으나 잔량으로 추가 진입이 중단됐다.
현재 잔여 작업·버전·증거는 [구현 상태](PHASE1_IMPLEMENTATION_STATUS.md),
연속 관측의 미충족 조건은 [1주 실행 계획](PHASE1_WEEK_RUN.md)을 따른다.

목표: 실거래 자본 없이 2-leg 집행, 대사, 장애 복구 인프라를 검증한다.

이 문서는 2026-08-19 초안을 Phase 0 실측 결과와 최신 공식 문서에 맞춰
수정한 구현 기준선이다. Phase 1의 성공 산출물은 수익률이 아니라 감사 가능하고
판정 가능한 집행 파이프라인이다.

## 1. 확정된 선행 상태

- Phase 0은 커밋 `9179f08`, 태그 `phase0-baseline`로 고정됐다.
- Oracle Tokyo의 V2 DB를 로컬 비공개 스냅샷으로 복제하고 SHA-256을 대조했다.
- 스냅샷은 194개 종료 거래와 388개 체결 주문을 포함한다.
- fee-only 반사실과 block bootstrap은 사전등록 후 실행했다.
- Phase 1은 실거래 주문을 만들거나 실자본을 사용하지 않는다.
- 작업트리가 dirty이거나 실행 이미지 digest/lock hash가 없으면 실행 진입점을
  fail-closed로 종료한다.

원시 SQLite와 자격증명은 Git에 포함하지 않는다. 파생 집계, 해시, 통계 결과만
버전 관리한다.

## 2. Phase 0 결과가 게이트하는 범위

V2 fee-only 반사실의 일별 평균 수익률은 `-0.0778146%`였다. 사전등록한
5일 primary moving-block bootstrap의 95% 구간은
`[-0.1517467%, -0.0115672%]`였고, 1/3/7/10일 sensitivity 구간도 모두
0 아래였다.

이 결과가 게이트하는 대상은 다음 두 가지뿐이다.

1. V2 비용 진단의 최종 문구
2. Phase 4에서 V2형 단기 방향성 전략을 다시 검토할 자격

다음 작업은 게이트하지 않는다.

- Binance Demo의 모의 주문 배관
- 운영 원장과 리스크 서비스
- 상태 머신 fixture replay와 장애 주입
- 캐리 스캐너의 주문 없는 관측

통계 결과와 모의 집행 인프라는 인과적으로 다른 검증 대상이다.

### 2.1 캐리 경제성 계산 계약

Abort 비용 30 bps를 모든 진입에 부과하는 계산은 과도하게 보수적이지만, 정상
진입비용만 빼고 “캐리는 양의 기대값”이라고 확정하는 계산도 불완전하다. 성공한
에피소드는 진입뿐 아니라 최종 청산 비용을 부담하고, abort 에피소드는 펀딩을
받지 못한다. Phase 1 스캐너는 다음 식을 사용한다.

```text
E[net bps]
  = (1 - p_abort) × (funding gross - successful round-trip costs)
    - p_abort × abort loss
```

`successful round-trip costs`에는 spot/perp 진입과 청산, 예상 impact, funding
반전, legging, rebalance, requote가 포함된다. Demo 수수료는 무시하고 credentialed
mainnet account query를 사용한다. 2026-09-03 조회로 Spot 10/10 bps와 USD-M
2/5 bps를 확인했고, BNB 할인은 보수적으로 적용하지 않았다. snapshot은 24시간 뒤
만료되며 재조회에 실패하면 스캐너는 다시 관측 전용으로 돌아간다. 따라서
“p_abort 50%에서도 항상 양수”나 “월 2.70 USDT 확정”은 Phase 1의 결론이 아니다.

Phase 1의 `p_abort=0.20`은 정책 prior다. Demo에서 측정한 값은 실제 queue 경쟁과
역선택을 포함하지 않으므로 하한 참고치로만 저장하고, Phase 3 소액 실거래 전에는
prior를 교체하지 않는다.

## 3. Venue와 실행 환경 결정

### 3.1 Phase 1 기본 경로

Phase 1은 Binance 단일 venue를 사용한다.

| Leg | Binance 상품 | Nautilus instrument 예시 |
|---|---|---|
| Spot long | BTCUSDT Spot | `BTCUSDT.BINANCE` |
| Perp short | BTCUSDT USD-M perpetual | `BTCUSDT-PERP.BINANCE` |

실행 환경은 legacy Testnet이 아니라 `BinanceEnvironment.DEMO`를 기본값으로
한다. Nautilus 공식 문서는 신규 모의거래 설정에 Demo를 권고하며, 하나의 Demo
API key로 Spot과 Futures Demo endpoint를 사용할 수 있다고 명시한다. Spot과
USD-M은 별도 data/execution client로 구성하되 하나의 intent와 상태 머신으로
조정한다.

Binance를 선택한 이유는 다음과 같다.

- 두 leg가 같은 BTCUSDT 경제적 기초자산을 사용한다.
- Hyperliquid UI의 BTC spot은 HyperCore에서 `UBTC/USDC`로 remap되는 Unit
  Bitcoin이다.
- UBTC spot 대 BTC perp는 bridge/custody와 UBTC/BTC basis라는 별도 위험을
  추가한다.
- Phase 1의 목적은 수익 최적화가 아니라 집행 일관성 검증이다.
- Binance Spot은 `LIMIT_MAKER`, USD-M Futures는 `GTX` post-only 주문을
  지원한다. 따라서 “post-only 보장 없음”은 더 이상 전제가 아니다.

### 3.2 Hyperliquid 경계

Hyperliquid 주문 경로는 Phase 1에서 구현하지 않는다. 기존 read-only metadata
수집은 유지하고, Phase 2 perp-only 바스켓 후보로 남긴다.

Hyperliquid 공식 문서는 portfolio margin이 spot과 perp를 합칠 수 있다고
설명하지만 현재 pre-alpha에서는 collateral/borrow cap이 제한되고, 공식 페이지
사이에도 현재 eligible BTC 범위에 해석 여지가 있다. 이것은 `UBTC` spot이 BTC
perp를 확실히 담보한다는 증거가 아니다.

향후 아래 항목이 모두 계정/API 실측으로 확인될 때만 별도 ADR에서 재검토한다.

- raw symbol과 token index가 `UBTC`로 명시적으로 매핑됨
- 선택한 account abstraction mode에서 UBTC spot이 BTC perp margin을 실제 상쇄함
- UBTC/BTC basis와 bridge/custody 위험 예산이 승인됨
- 해당 동작이 restart/reconciliation fixture로 재현됨

## 4. 코드와 배포 경계

저장소 이름 `freqtrade-v3`는 연속성을 위한 역사적 이름이다. Freqtrade는 V2
비교 연구와 zero-entry shadow runtime에만 남고, Phase 1 주문 엔진은
NautilusTrader다.

기존 Phase 0 모듈은 태그와 import 안정성을 위해 지금 이동하지 않는다. 새로운
코드는 `v3/phase1/` 아래에 추가한다. 기존 `v3/risk.py`를 디렉터리로 바꾸면
import가 깨지므로 별도 namespace를 쓴다. 추후 namespace 정리가 필요하면 호환
shim과 별도 migration commit으로 처리한다.

```text
v3/
├── costs.py                      기존 비용 계산 primitive
├── reproducibility.py            기존 7종 manifest 및 clean-tree gate
├── instruments.py                기존 instrument conformance
├── preflight.py                  기존 최종 order admission
└── phase1/
    ├── policy.py                 기계 판독 정책
    ├── runtime.py                실행 진입 fail-closed 검사
    ├── ledger.py                 원장 repository 계약
    ├── migrations/               PostgreSQL migration
    ├── risk.py                   독립 Phase 1 리스크 결정
    ├── scanner.py                주문 없는 캐리 target
    ├── state_machine.py          2-leg aggregate
    └── adapters.py               Nautilus/Binance 경계
```

Freqtrade와 Nautilus는 compose project, network, volume, port, database,
environment file을 공유하지 않는다.

## 5. Phase 1A: 실행 환경 분리

예상 기간: 3~4일

### 산출물

- `Dockerfile.execution`: Oracle ARM64용 전용 이미지
- Python `3.12.12` ARM64 이미지와 NautilusTrader `1.231.0` exact pin
- `uv.lock`과 lock SHA-256
- PostgreSQL 16 exact image reference와 digest
- Binance Demo Spot/USDT-M 별도 client configuration
- 실행 진입점의 manifest, image digest, clean-tree gate
- ARM64 build와 주문 없는 smoke test

버전은 2026-09-03 compatibility 확인에서 고정했다. `uv.lock` 없이 실행하거나
floating tag/range와 자동 업그레이드를 사용하는 경로는 금지한다.

### 진입 조건

아래 중 하나라도 만족하지 않으면 프로세스를 시작하지 않는다.

- Git SHA가 존재하고 working tree가 clean이다.
- image digest와 dependency lock hash가 존재한다.
- environment가 Demo이며 live order authorization은 false다.
- Spot과 USD-M client가 서로 다른 account/client ID를 가진다.
- 허용 instrument가 BTCUSDT Spot과 BTCUSDT USD-M perpetual로 제한된다.
- 계정의 실제 leverage를 조회할 수 있고 2x 이하임을 확인한다.

### 검증

- ARM64 container에서 `import nautilus_trader` 성공
- 주문 없는 node start/stop 성공
- Spot/USDT-M instrument 및 account snapshot 조회 성공
- Freqtrade shadow와 동시 실행 시 자원 충돌 0
- dirty tree, missing digest, live environment 각각 즉시 종료

## 6. Phase 1B: 운영 원장과 독립 리스크 계층

예상 기간: 1~1.5주

PostgreSQL `NUMERIC`과 UTC timestamp를 사용한다. 금액과 수량은 binary float로
저장하지 않는다. schema migration은 순방향/역방향 테스트를 갖는다.

### 6.1 테이블 14개

| 테이블 | 역할 |
|---|---|
| `intents` | 전략 근거, 목표, 정상/위험 exit, 시간 제한, 비용·리스크 예산, manifest ID |
| `cost_ledger_entries` | leg fee, impact, funding, legging, rebalance, transfer, requote의 예상/실현 비용과 출처 |
| `risk_decisions` | 승인/거부, 관측 leverage, quote age, 노출 전후, 지연시간 |
| `instrument_snapshots` | raw symbol, precision, min notional, tick/lot, 상태, content hash |
| `quote_observations` | bid/ask, venue/local timestamp, age와 수집 상태 |
| `order_commands` | immutable 명령과 unique idempotency key |
| `orders` | venue/client order ID, 상태, 체결량, 평균가, reject code |
| `fills` | unique venue fill ID, 수량, 가격, fee token, maker/taker, liquidation metadata |
| `positions` | venue/local position snapshot, leverage, margin, liquidation price |
| `funding_events` | 심볼별 interval, rate, expected/realized amount |
| `reconciliation_runs` | 설명된/미설명 잔차와 실행 결과 |
| `incidents` | 장애 종류, 심각도, 관련 intent, 종결 근거 |
| `state_transitions` | 성공/거부된 전이 시도, trigger와 guard 결과 |
| `internal_transfers` | Spot/Futures 지갑 이동 요청·확정·실패와 unique idempotency key |

`run_manifest_id`는 버전 관리된 manifest artifact의 content hash다. 별도 DB
테이블을 만들지 않고, intent에서 immutable hash를 참조한다.

### 6.2 Source of truth

| 대상 | 권위 소스 | 불일치 처리 |
|---|---|---|
| 실제 주문·체결·포지션·잔고 | 거래소 | 신규 intent 차단, incident 생성, 대사 |
| intent·승인·명령·상태 전이 | PostgreSQL | 거래소 값으로 덮어쓰지 않음 |
| instrument와 fee 규칙 | credentialed venue query의 timestamped snapshot | 만료/조회 실패 시 주문 거부 |

### 6.3 리스크 거부 조건

다음 조건 중 하나라도 참이면 승인하지 않는다.

- leverage 조회 실패 또는 2x 초과
- quote-age가 측정된 SLA 초과
- leg 명목이 instrument 최소명목의 3배 미만
- intent 필드 또는 cost ledger 누락
- 거래소와 로컬 포지션 불일치
- 일 손실이 총자본의 2%에 도달
- 월 abort 비용이 캐리 슬리브의 0.5%에 도달
- 월 abort 시도 3회 도달 또는 연속 abort 2회 도달
- idempotency key 중복
- Demo가 아닌 환경 또는 live authorization 감지

리스크 서비스 timeout은 deny다. 같은 명령을 새 idempotency key로 자동 재시도하지
않는다.

### 6.4 Idempotency

```text
sha256(intent_id:leg:attempt:qty:price)[:32]
```

명시적 cancel-confirmed requote에서만 `attempt`를 증가시킨다. 전송 결과가
unknown이면 동일 key로 먼저 거래소 상태를 조회한다. PostgreSQL unique
constraint와 venue client-order ID를 함께 사용한다.

## 7. Phase 1C: 캐리 스캐너

예상 기간: 4~5일

스캐너는 주문을 제출하지 않고 목표 포지션과 0 결정의 이유를 출력한다.

```python
@dataclass(frozen=True)
class CarryTarget:
    venue: str
    spot_instrument_id: str
    perp_instrument_id: str
    target_notional: Decimal
    funding_rate: Decimal
    funding_interval_minutes: int
    expected_gross_bps: Decimal
    net_expected_bps: Decimal
    holding_period_hours: int
    decision_reason: str
    instrument_snapshot_id: str
    cost_ledger_id: str
```

`net_expected_bps < 20`이면 `target_notional`은 0이다. funding interval은 상수가
아니며 `/fapi/v1/fundingInfo`의 심볼별 `fundingIntervalHours`에서 가져온다.
credentialed commission query가 실패하면 추정 fee로 승격하지 않고 스캐너를
관측 전용 상태로 둔다.

비용 원장은 leg fee, impact/adverse selection, funding 반전, legging loss,
rebalance, requote를 포함한다. 각 값에는 출처와 관측시각을 저장한다.

캐리 슬리브는 450 USDT다. Spot 현금 `1N`과 2x 격리 perp 증거금 `0.5N`을
동시에 수용해야 하므로 leg 명목 상한은 `450 / 1.5 = 300 USDT`다. scanner와
risk가 이 상한을 각각 독립적으로 거부한다.

## 8. Phase 1D: 2-leg 집행 상태 머신

예상 기간: 2~3주

초안은 18개 전이였다. 지갑 잔고가 충분한 direct path와 부족한 transfer path를
둘 다 보존하면 `internal_transfers` 반영 후 21개가 된다. 20개로 세는 안은
`RISK_APPROVED → SUBMITTING` direct path를 잃으므로 채택하지 않는다. 테스트는
각 전이마다 하나 이상의 사례를 가져야 한다.

| From | To | Trigger/guard 요약 |
|---|---|---|
| — | `PLANNED` | 양의 CarryTarget, intent와 비용 원장 존재 |
| `PLANNED` | `RISK_APPROVED` | 독립 리스크 승인 |
| `PLANNED` | `ABORTING` | deny 또는 timeout |
| `RISK_APPROVED` | `SUBMITTING` | 양 지갑 잔고 충분, 두 leg command와 key를 DB에 먼저 기록 |
| `RISK_APPROVED` | `TRANSFERRING` | 잔고 부족, 지원·승인된 내부이체 요청을 DB에 먼저 기록 |
| `TRANSFERRING` | `SUBMITTING` | 이체 확인 후 양 지갑 잔고 재검증 |
| `TRANSFERRING` | `ABORTING` | 이체 실패·timeout·지원 불명; 체결이 없으므로 거래비용 0 |
| `SUBMITTING` | `PARTIALLY_HEDGED` | 한 leg의 일부 이상 체결 |
| `SUBMITTING` | `HEDGED` | 두 leg 체결, 명목 괴리 허용치 이내 |
| `SUBMITTING` | `ABORTING` | 양 leg 미체결 상태로 TTL 만료 |
| `PARTIALLY_HEDGED` | `HEDGED` | 반대 leg 완료와 delta 확인 |
| `PARTIALLY_HEDGED` | `HEDGE_REQUIRED` | hedge SLA 초과 |
| `HEDGE_REQUIRED` | `HEDGED` | 비상 hedge 성공 |
| `HEDGE_REQUIRED` | `ABORTING` | hedge 실패 후 체결 leg unwind 결정 |
| `HEDGED` | `RECONCILING` | 주기 대사 또는 종료 조건 |
| `RECONCILING` | `HEDGED` | 설명된 잔차만 존재 |
| `RECONCILING` | `RECONCILIATION_BLOCKED` | 미설명 잔차 존재 |
| `RECONCILING` | `CLOSED` | 두 leg와 open order가 모두 0 |
| `ABORTING` | `CLOSED` | 체결분 unwind 완료 |
| `ABORTING` | `HEDGE_REQUIRED` | unwind 중 반대 fill 도착 |
| `RECONCILIATION_BLOCKED` | `RECONCILING` | incident 종결 근거 후 명시적 재시도 |

가드 실패도 `state_transitions`에 기록한다.

### 8.1 불변식 6개

1. 각 열린 intent는 leg당 활성 command가 최대 하나다.
2. `HEDGED`에서 두 leg 명목 괴리는 5% 이하다.
3. 거래소 포지션과 최신 로컬 snapshot은 허용 반올림 범위 내에서 일치한다.
4. 모든 fill은 order에 연결되고 venue fill ID 중복이 없다.
5. `SUBMITTING` 이후 intent는 승인된 risk decision을 가진다.
6. 무헤지 명목×지속시간 누적이 사전 상한을 넘지 않는다.

### 8.2 재시작 복구

복구 중에는 주문을 제출하지 않는다.

1. 미종결 intent를 로드한다.
2. 거래소의 open order, 최근 fill, position, balance를 조회한다.
3. 누락 fill을 idempotent하게 반영한다.
4. 상태를 재구성하고 불변식 6개를 검사한다.
5. 위반 시 모든 신규 intent를 차단하고 `RECONCILIATION_BLOCKED`로 둔다.
6. 위반이 없을 때만 실행 loop를 연다.

### 8.3 Abort와 비상 hedge

- 단건 abort 예산: intent 명목의 30 bps
- 월간 abort 예산: 캐리 슬리브의 0.5%
- 월 3회 또는 연속 2회 abort 시 신규 intent 중단과 incident 생성

30 bps는 초기 정책값이며 성과 통계가 아니다. Demo 실측 전 사후 조정하지 않는다.
부분체결 이후에는 delta 제거가 비용 예산보다 우선한다. 예산 초과 예상은 hedge를
포기하는 조건이 아니라 신규 진입 kill-switch와 incident 조건이다.

비상 hedge는 fresh quote 확인 후 bounded IOC-limit으로 시작한다. 최대 재시도
횟수와 가격 공격 폭을 고정하며, 각 실패를 원장과 transition에 기록한다. adapter가
market order에 cached quote를 요구하는 경로는 별도 fixture로 검증하고, stale 또는
missing quote에서 무제한 market fallback을 사용하지 않는다.

## 9. Phase 1E: 장애 주입과 SLA

예상 기간: 1~1.5주

### 9.1 세 가지 검증 경로

실제 캐리 기회가 없더라도 상태 머신을 검증할 수 있어야 한다.

| 경로 | 목적 |
|---|---|
| 결정론적 fixture replay | 순서 역전, 지연 fill, liquidation/ADL, restart 상태 재구성 |
| 합성 target 주입 | Demo의 실제 submit/cancel/fill/partial-fill/hedge 배관 |
| 정상 스캐너 관측 | 실제 비용 차감 기회가 언제 0/양수를 내는지 기록 |

합성 target은 Demo/Testnet에서만 허용한다. 환경이 Live이거나 live authorization이
켜져 있으면 CLI 파싱 단계에서 거부한다. Demo 명목은 운영 SLA 측정용이며
1,000 USDT mainnet sizing 근거로 사용하지 않는다.

### 9.2 장애 시나리오 13개

1. 첫 leg만 체결
2. 부분체결 직후 WebSocket 종료
3. quote 없음
4. stale quote
5. post-only 거부
6. 연속 modify 실패와 delayed fill report
7. 이벤트 순서가 뒤집힌 지연 fill
8. WebSocket 재연결
9. 프로세스 강제 종료와 restart recovery
10. 필수 account/client identity 누락
11. funding, fee, rounding 잔차
12. liquidation/ADL fixture replay
13. 동일 idempotency key 중복 명령

각 시나리오는 최종 상태, 제출 주문 수, 고아 fill 수, 미설명 잔차, incident 및
transition 기록을 assertion한다.

### 9.3 SLA 측정

- hedge latency: 첫 leg fill venue timestamp부터 반대 leg fill/cancel timestamp
- quote age: local receipt timestamp - venue timestamp
- 합성 2-leg 시도 최소 50건
- quote observation은 1E 동안 10초 표본 또는 위험 결정 시점에만 수집
- hedge latency: Demo 하한 분포의 median/p99를 기록하되 운영 SLA로 승격하지 않음
- quote-age SLA: 관측 p99 + 100% margin. 2026-09-15 USD-M exchange-age 259표본
  p99 47.68 ms → `maximum_quote_age_ms=96` 채택(`evidence/phase1/sla-evidence-20260915.json`).
  현물 bookTicker는 거래소 시각이 없어 미측정으로 유지한다.
- venue, adapter, instance, network topology 변경 시 재측정

이 표본은 운영 지연 분포 전용이며 수익률이나 alpha 판정에 쓰지 않는다.

## 10. 종료 게이트

모든 항목을 만족해야 Phase 1을 완료로 표시한다.

- mainnet order 0건, real capital 0
- unknown leverage 승인 0건, 2x 초과 승인 0건
- 미설명 reconciliation residual은 Phase 1E에서 정한 금액 임계 미만이고 제한시간 내 분류
- 중복 venue order 0, 고아 fill 0
- 실패 후 열린 무헤지 노출 0
- 모든 order command에 intent, cost ledger, manifest 참조 존재
- 강제 종료 recovery 3회 이상 성공
- 21개 transition과 6개 invariant 테스트 통과
- 13개 fault scenario 전부 통과
- Demo hedge-latency 하한과 quote-age SLA의 표본 수와 percentile 기록
- 수익률을 완료 기준으로 사용하지 않음
- mainnet fee snapshot은 24시간 이내이며 출처 evidence와 일치

Phase 1 완료는 Phase 3 실자본 사용 권한이 아니다.

## 11. 일정과 커밋 단위

총 예상 기간은 6~8주다.

| 단계 | 기간 | 완료 커밋 기준 |
|---|---:|---|
| Phase 0 증거 고정 | 완료 | baseline tag, DB hash, bootstrap result |
| 1A 실행 환경 | 3~4일 | ARM64 smoke, exact lock, clean/digest gate |
| 1B 원장·리스크 | 1~1.5주 | 14-table migration, repository, deny contract, restart-safe DB tests |
| 1C 스캐너 | 4~5일 | 주문 없는 target/zero-reason과 비용 원장 |
| 1D 상태 머신 | 2~3주 | 21개 전이, 6개 불변식, restart recovery |
| 1E 장애·SLA | 1~1.5주 | 13개 시나리오와 SLA evidence |

각 단계는 테스트가 통과하고 working tree가 clean인 Lore commit에서 종료한다.
1D에 들어간 뒤에는 상태 머신과 무관한 연구 작업을 같은 branch에 섞지 않는다.

## 12. 아직 자격증명이 필요한 확인

- Binance 전용 Demo API key와 Spot/USDT-M 권한
- Demo 주문 reject code
- Demo 계정의 leverage/margin mode
- post-only reject/requote와 hedge latency 실측

이 항목은 구현 차단이 아니라 해당 integration test의 실행 조건이다. 자격증명 없이도
1A의 image/manifest, 1B의 원장/리스크, 1D의 fixture state machine을 먼저 구현한다.

2026-09-03 읽기 전용 확인으로 다음 항목은 해소됐다.

- Demo 공개 Spot/USD-M ping과 BTCUSDT instrument filter
- Demo Spot 최소명목 5 USDT, USD-M 최소명목 50 USDT
- Mainnet 계정 수수료: Spot 10/10 bps, USD-M 2/5 bps
- V2 키의 환경 범위: Mainnet 유효, Demo 양쪽 `-2015`
- V2 Mainnet USD-M BTCUSDT 설정: 격리마진 4x

마지막 설정은 Phase 1 정책의 2x 상한을 위반하지만 Mainnet 계정의 관측값이며,
이번 작업에서 변경하지 않았다. 별도 Demo 키가 준비되기 전에는 Nautilus credentialed
client 시작, 주문 테스트, internal transfer 테스트를 실행하지 않는다.

## 13. 공식 근거

- NautilusTrader Binance integration:
  <https://nautilustrader.io/docs/latest/integrations/binance/>
- Binance USD-M funding info:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-Info>
- Binance Spot order API:
  <https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints>
- Binance USD-M order definitions:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/common-definition>
- Hyperliquid Info endpoint and UBTC remapping:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint>
- Hyperliquid account abstraction:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes>
- Hyperliquid portfolio margin:
  <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/portfolio-margin>
