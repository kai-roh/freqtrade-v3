# PROGRESS

기준일: 2026-09-25 20:10 KST. 새 세션은 이 파일부터 읽는다. 상세 근거는 각 링크 문서에 있고,
이 파일은 **현재 상태·열린 문제·다음 할 일**만 최신으로 유지한다. 과거 이력은 여기 쓰지 않는다.

## 한 줄 요약

Phase 1(Binance Demo 2-leg 캐리 집행 인프라)은 재시작 복구 3회·잔량 정산·30 에피소드까지
실증됐다. 주간 관측 실행기는 2026-09-17 정지 후 실행 창(09-22)이 만료됐고, 남아 있던 비헤지 현물은
**2026-09-25 11:01 UTC에 close-only 재개로 매도·정산해 열린 intent 0건**이다. Phase 2(perp-only 시장중립 바스켓)는 사전등록대로 실행해 **STOP_NO_EDGE**로
기각됐다. Phase 3(소액 실자본) 후보 전략은 없다. 실자본·Mainnet 주문은 어디에도 승인되지 않았다.

## 현재 상태

| 영역 | 상태 | 근거 |
|---|---|---|
| Phase 0 연구·비용·재현성 | 완료. Milestone 1 `STOP_BEFORE_CLASSIFIER`, 자본기준 지표로 재검증해도 동일 | [MILESTONE_1](docs/MILESTONE_1.md), `research_results/validation-b6d3bbd/` |
| Phase 1A~1D 집행 인프라 | 완료. 실체결 128건, 거부 전이 0, 미해결 복구 0, 강제 재시작 복구 3회 | [PHASE1_IMPLEMENTATION_STATUS](docs/PHASE1_IMPLEMENTATION_STATUS.md), [DEMO_AUTO_RUNBOOK](docs/PHASE1_DEMO_AUTO_RUNBOOK.md) |
| Phase 1E 주간 관측 | **종료(창 만료).** 에피소드 30 CLOSED / 게이트 50, 열린 intent 0, 마지막 에피소드는 09-25 close-only 재개로 종료 | [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md), `evidence/phase1/demo-week-run-20260915/` |
| quote-age SLA | 채택 96 ms(USD-M p99 47.68 ms × 2). 현물 bookTicker는 미측정 유지. 표본 120,702개 누적 | `configs/phase1-policy.json`, `evidence/phase1/sla-evidence-20260915.json` |
| Telegram | 알림 2줄 포맷, 명령 봇 `/status /profit /balance /daily /help` 실행 중 | [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md#telegram-commands) |
| Phase 2 바스켓 연구 | 완료·기각 `STOP_NO_EDGE`. 펀딩 +3.4 USDT vs 비용 13.8 USDT, PBO 0.77 | [Decision 0009](docs/decisions/0009-phase2-basket-result-stop-no-edge.md), `research_results/phase2/REPORT.md` |
| Phase 3 | 착수 불가(후보 없음) | Decision 0006 §Constraints |

서버(`ft-tokyo`, `/home/kai/freqtrade-v3`) 컨테이너: `phase1-postgres` 실행, `phase1-telegram-bot` 실행,
주간 실행 컨테이너는 모두 종료(`…-resume5` exit 0이 마지막), `freqtrade_kai`(zero-entry shadow) 실행.
서버 작업 복사본은 `1a124d1` + `05faa73` 동기화, 현행 이미지 `freqtrade-v3-demo-auto:1a124d1`(`sha256:5d2dd045…`).
저장소 브랜치 `codex/v2-to-v3-infrastructure`, 테스트 438개 통과(PostgreSQL 포함).

## 열린 문제

1. **Phase 1E 게이트 미달.** 에피소드 30 < 50. 재시작 3회는 충족. 새 run(새 `--started-at`, 새 manifest)으로
   연장할지, 현 상태에서 게이트를 판정하고 종료할지 결정이 필요하다. 연장 시 이미지는 `1a124d1` 이상.
2. 서버 격리 스키마 테스트(`freqtrade-v3-tests`)를 `1a124d1` 이후 실행하지 않았다(권한 분류기 차단).
   로컬 PostgreSQL 16.14에서 438개 통과로 대체. 테스트 이미지 컨텍스트는 `05faa73`에서 `user_data/*` 제외.
3. 테스트 이미지에서 manifest CLI 테스트 1건이 `.git` 부재로 실패한다(환경 문제, 코드 결함 아님).

해결됨(09-25): Demo 비헤지 현물 `0.00286713 BTC`는 `1a124d1` 이미지의 close-only 재개
(`--resume-intent`/`--previous-manifest`)로 `0.00286 BTC @ 84,734` 매도, 잔량 `0.00000713 BTC` 정산,
intent `1fe50ea6…` CLOSED. 원인 두 가지(신선도 거부 즉시 정지, 청산 단계 노출 예산 불변식)는 `1a124d1`에서
수정. 상세는 [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md).

## 다음 할 일 (순서대로)

1. Phase 1E 결정: 연장 run 시작 여부. 연장하면 `configs/phase1-week-run.json`, 이미지 `1a124d1`, 새 `--started-at`으로
   새 run(Demo 주문, 승인 필요). 종료하면 게이트 미달(30/50)을 그대로 기록한다.
2. 관측 종료 후 `scripts/summarize_phase1_sla.py`로 SLA·헤지 지연 재집계, Phase 1E 종료 ADR 작성
   (09-25 재개의 `unhedged_budget_exceeded` 증거와 두 수정 사항 포함).
3. (선택) 서버에서 `freqtrade-v3-tests:1a124d1` 빌드·격리 스키마 테스트 재확인.
4. Phase 2 후속은 **새 사전등록**으로만: 유력 후보는 H1을 maker/post-only 집행·일 단위 결정·낮은 회전율로
   재정의. 결과를 본 뒤 격자·비용·게이트를 바꾸는 것은 금지(Decision 0008).
5. 저장소: 로컬 커밋(`1a124d1`~) push, `codex/v2-to-v3-infrastructure` → `main` PR·머지.
   서버 작업 복사본 재동기화(`git archive HEAD | ssh ... tar -xm`).

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
