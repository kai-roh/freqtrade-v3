# PROGRESS

기준일: 2026-10-02 KST. 새 세션은 이 파일부터 읽는다. 상세 근거는 각 링크 문서에 있고,
이 파일은 **현재 상태·열린 문제·다음 할 일**만 최신으로 유지한다. 과거 이력은 여기 쓰지 않는다.

## 한 줄 요약

Phase 1E 관측을 **2026-10-02에 종료**했다([Decision 0010](docs/decisions/0010-phase1e-observation-close.md)).
주간 run 에피소드 67개(원장 전체 70개 CLOSED), 종료 게이트 12개 중 11개 충족. **"실패 후 열린 무헤지 노출 0"
1개 항목이 미충족**이라 Phase 1은 완료로 표시하지 않았다(정지 2회가 각각 약 186시간·12시간 노출을 남김).
Phase 2는 **STOP_NO_EDGE**로 기각됐고 Phase 3 후보 전략은 없다. 실자본·Mainnet 주문은 어디에도 승인되지 않았다.

## 현재 상태

| 영역 | 상태 | 근거 |
|---|---|---|
| Phase 0 연구·비용·재현성 | 완료. Milestone 1 `STOP_BEFORE_CLASSIFIER`, 자본기준 지표로 재검증해도 동일 | [MILESTONE_1](docs/MILESTONE_1.md), `research_results/validation-b6d3bbd/` |
| Phase 1A~1D 집행 인프라 | 완료. 명령 289건(전부 Demo), 체결 296건, 거부 전이 0, 중복·고아 0, 강제 재시작 복구 3회 | [Decision 0010](docs/decisions/0010-phase1e-observation-close.md) |
| Phase 1E 관측 | **종료.** 주간 run 67 에피소드, 실행기 정지(10-02 03:38 UTC, 대기 구간), 열린 intent 0 | [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md) |
| Phase 1 종료 게이트 | **11/12.** 5번 "실패 후 열린 무헤지 노출 0" 미충족 | [Decision 0010](docs/decisions/0010-phase1e-observation-close.md) |
| quote-age SLA | 96 ms 유지. USD-M 307,696표본 p99 48 ms로 재확인. 현물 bookTicker는 미측정 | `evidence/phase1/phase1e-close-20261002/sla-evidence-20261002.json` |
| 헤지 지연 | 69표본, 중위 4.4 s, p99 7.3 s. 실행기 2초 tick이 지배하는 Demo 엔지니어링 수치, 운영 SLA 아님 | 같은 파일 |
| Mainnet 수수료 | 10-02 GET 갱신: 현물 10/10 bps, 선물 2/5 bps(변동 없음) | `evidence/phase1/phase1e-close-20261002/binance-mainnet-fees-20261002.json` |
| Telegram | 알림 2줄 포맷, 명령 봇 `/status /profit /balance /daily /help` 실행 중 | [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md#telegram-commands) |
| Phase 2 바스켓 연구 | 완료·기각 `STOP_NO_EDGE`. 펀딩 +3.4 USDT vs 비용 13.8 USDT, PBO 0.77 | [Decision 0009](docs/decisions/0009-phase2-basket-result-stop-no-edge.md), `research_results/phase2/REPORT.md` |
| Phase 3 | 착수 불가(후보 없음, Phase 1 미완료) | Decision 0006 §Constraints |

서버(`ft-tokyo`, `/home/kai/freqtrade-v3`) 컨테이너: `phase1-postgres` 실행, `phase1-telegram-bot` 실행,
`freqtrade_kai`(zero-entry shadow) 실행. **주간 실행기는 없다**(마지막 `phase1-demo-week-run-20260928-restart1` exit 137,
대기 중 사용자 지시로 정지). Demo 계정: 선물 0, 미체결 없음, 현물 BTC `0.00050308` = 정산 잔량 69건 합계.
서버 작업 복사본은 `5e8afe1`, 현행 이미지 `freqtrade-v3-demo-auto:5e8afe1`(`sha256:ef02aba8…`).
저장소 브랜치 `codex/v2-to-v3-infrastructure`, 테스트 441개 통과(PostgreSQL 포함).

## 열린 문제

1. **Phase 1 게이트 5번 미충족.** 실행기는 치명 오류 시 신규 주문만 멈추고 청산하지 않으며 사람이 재시작한다.
   해소 방법은 둘 중 하나이고 어느 쪽이든 새 결정이다. (a) 치명 오류 시 열린 에피소드를 자동 close-only로 넘기는
   경로 구현과 장애 주입 Demo 검증, (b) 5번을 "fail-closed + 알림 + 문서화된 사람 복구"로 개정하고 최대 대응 시간 명시.
2. `1a124d1`의 일시 거부 재시도와 청산 단계 예산 규칙은 테스트만 있고 실제 Demo 거부로는 아직 작동한 적 없다.
3. 진입 위험 결정 행에 관측 레버리지가 저장되지 않는다(디스패치 payload에는 있음). 감사 편의상 보완 권장, 게이트 실패 아님.
4. 서버 격리 스키마 테스트(`freqtrade-v3-tests`)는 `1a124d1` 이후 실행하지 않았다(권한 분류기 차단). 로컬 PostgreSQL 16.14로 대체.
5. 테스트 이미지에서 manifest CLI 테스트 1건이 `.git` 부재로 실패한다(환경 문제, 코드 결함 아님).

## 다음 할 일 (순서대로)

1. 게이트 5번 해소 방식 결정: 자동 close-only 복구 구현 또는 게이트 개정(열린 문제 1).
2. 저장소: 로컬 커밋(`1a124d1`~) push, `codex/v2-to-v3-infrastructure` → `main` PR·머지.
3. Phase 2 후속은 **새 사전등록**으로만(Decision 0008). 유력 후보는 H1을 maker/post-only·일 단위 결정·낮은 회전율로 재정의.
4. (선택) 진입 위험 결정에 레버리지 기록, 서버 격리 스키마 테스트 재확인.

## 운영 규칙 (요약)

- Demo만. Mainnet 주문·실자본·live authorization은 어떤 코드 경로에도 없다.
- 서버에서 주문·DB 상태를 바꾸는 실행은 사용자 명시 승인 후. 읽기 전용 점검·이미지 빌드는 자유.
- 실행기는 자동 재시작하지 않는다. 재시작은 같은 `--started-at`과 새 컨테이너 이름으로.
- 실행 중 Demo BTCUSDT 계정에서 다른 프로그램·수동 주문 금지.
- 연구는 사전등록 → 데이터 동결(해시) → 실행 → ADR. 결과를 본 뒤의 변경은 새 등록.
- 로컬 머신은 Binance API에 접속되지 않는다. 공개 API 조회·데이터 다운로드는 서버에서 한다.

## 빠른 확인 명령

```bash
# 로컬 검증
uv run --frozen python -m pytest -q            # PostgreSQL 통합은 PHASE1_TEST_DATABASE_DSN 필요
uv run --frozen ruff check . && uv run --frozen ruff format --check .

# 서버 상태 (읽기 전용)
ssh ft-tokyo 'docker ps -a --format "{{.Names}} {{.Status}}" | grep -E "week-run|telegram|postgres"'
ssh ft-tokyo 'docker exec phase1-postgres psql -U phase1 -d phase1 -Atc "select state,count(*) from intents group by state"'

# Telegram: /status /profit /balance /daily
```

## 문서 지도

- 결정 기록: `docs/decisions/0001`~`0009` (0007 잔량 정산·펀딩 투영, 0008 Phase 2 등록, 0009 Phase 2 결과)
- Phase 1: [계획](docs/PHASE1_IMPLEMENTATION_PLAN.md) · [상태](docs/PHASE1_IMPLEMENTATION_STATUS.md) ·
  [실행 runbook](docs/PHASE1_DEMO_AUTO_RUNBOOK.md) · [주간 관측](docs/PHASE1_WEEK_RUN.md) ·
  [연결 runbook](docs/PHASE1_INTEGRATION_RUNBOOK.md) · [매칭 probe](docs/PHASE1_MATCHING_PROBE.md)
- Phase 2: [사전등록](docs/PHASE2_PREREGISTRATION.md) · 결과 `research_results/phase2/`
- Phase 0·연구: [전략 계약](docs/STRATEGY_PHASE0_FINAL.md) · [Milestone 1](docs/MILESTONE_1.md) ·
  [보고·정기 연구](docs/REPORTING_AND_RESEARCH.md) · [블록 부트스트랩](docs/BLOCK_BOOTSTRAP.md) · V2 문서 3종
- 운영: [서버 상태](docs/SERVER_STATE.md) · [의존성 정책](docs/DEPENDENCY_POLICY.md) · [V2→V3 이전](docs/MIGRATION_V2_TO_V3.md)
