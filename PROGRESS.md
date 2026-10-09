# PROGRESS

기준일: 2026-10-09 KST. 새 세션은 이 파일부터 읽는다. 상세 근거는 각 링크 문서에 있고,
이 파일은 **현재 상태·열린 문제·다음 할 일**만 최신으로 유지한다. 과거 이력은 여기 쓰지 않는다.

## 한 줄 요약

Phase 1E 관측을 2026-10-02에 종료했고([Decision 0010](docs/decisions/0010-phase1e-observation-close.md)),
게이트 5번을 Demo 한정으로 개정해([Decision 0011](docs/decisions/0011-amend-phase1-gate-item5.md))
**Phase 1은 Demo 기준 완료**다(09-17 정지의 186시간 대응은 기록된 예외). Phase 2(taker)와 Phase 2b(저회전 maker 펀딩 캐리)는 게이트를 통과하지 못했고, 위험 중립화 진단 뒤
**펀딩 횡단면 전략군을 보류**했다([Decision 0014](docs/decisions/0014-shelve-funding-cross-section-family.md)). 균형 복원·베타 사이징은
가격 손실과 낙폭을 일관되게 줄였지만, 위험을 중립화하면 펀딩이 비용과 거의 같아 캐리가 남지 않았다. 이어 사용자가 방향성 위험을
감수하기로 하고 **Phase 2c(BTC·ETH 저빈도 추세)**를 사전등록·실행했으나 `STOP_NO_EDGE`였다([Decision 0016](docs/decisions/0016-phase2c-result-stop-no-edge.md)):
연 8.4% 수익은 났지만 위험을 맞춘 보유보다 Sharpe가 낮았고(0.54 vs 0.78) PBO 0.34였다. 후속으로 고정 MA200을 현물 보유·실제 주문 제약과
비교한 사전 고정 진단은 **`PAUSE_RESEARCH`**였다([Decision 0017](docs/decisions/0017-ma200-comparison-pause-research.md)): 수익 75% 유지·낙폭 63%로
위험 축소는 됐지만, 슬리브 500 USDT에서는 BTC 선물 최소 수량(0.001 BTC ≈ 64 USDT)이 거칠어 주문의 73%를 낼 수 없었다. 사용자가 슬리브를
**1,000 USDT(계좌 전체)**로 바꾸기로 결정해(계획 이탈, [Decision 0018](docs/decisions/0018-ma200-sleeve-1000-plan-departure.md)) 다시 돌린 결과
5개 기준을 모두 통과했다(`OBSERVE_ELIGIBLE`). 이어 **주문 없는 MA200 전진 관측을 등록**했다([Decision 0019](docs/decisions/0019-ma200-observation-and-dry-run.md)):
2026-10-03 시작, 서버가 매일 11:10 KST에 가상 계좌를 계산해 Telegram으로 보내고, 첫 7일은 운영 점검이다. 이어 **Demo 실행기와 자동 보호 장치**를
개발·Demo 검증하고 cron으로 가동했다([Decision 0020](docs/decisions/0020-ma200-live-risk-contract.md)). −10% 중단선이 1,000 USDT에서
양립하지 않는 것으로 나와, 사용자가 **−20%(800 USDT)로 완화**했고 Demo에도 적용했다([Decision 0021](docs/decisions/0021-ma200-stop-20-percent.md), 위험 수준 25% 유지).
10-07에 관측 보고의 기간 손익 버그(24시간·주 손익이 최근 1시간만 계산)를 고치고, 보고에 Demo 실제 계좌를 넣었으며,
거래하지 않는 섀도 봇의 23시·일요일 리포트를 끄고, 보호 장치 실패 알림을 추가했다([Decision 0022](docs/decisions/0022-ma200-reports-and-guard-health.md)).
**7일 운영 점검(10-03~10-09)은 2026-10-09에 통과했다**(운영 항목 4/4, 수익성 검증 아님).
실거래는 아직 승인되지 않았다(Mainnet 잠금). 실자본·Mainnet 주문은 어디에도 승인되지 않았다.

## 현재 상태

| 영역 | 상태 | 근거 |
|---|---|---|
| Phase 0 연구·비용·재현성 | 완료. Milestone 1 `STOP_BEFORE_CLASSIFIER`, 자본기준 지표로 재검증해도 동일 | [MILESTONE_1](docs/MILESTONE_1.md), `research_results/validation-b6d3bbd/` |
| Phase 1A~1D 집행 인프라 | 완료. 명령 289건(전부 Demo), 체결 296건, 거부 전이 0, 중복·고아 0, 강제 재시작 복구 3회 | [Decision 0010](docs/decisions/0010-phase1e-observation-close.md) |
| Phase 1E 관측 | **종료.** 주간 run 67 에피소드, 실행기 정지(10-02 03:38 UTC, 대기 구간), 열린 intent 0 | [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md) |
| Phase 1 종료 게이트 | **12/12 (Demo 기준 완료).** 5번은 fail-closed·알림·문서화된 복구·24시간 대응으로 개정, 09-17 건은 예외 기록. Phase 3 전 재결정 | [Decision 0011](docs/decisions/0011-amend-phase1-gate-item5.md) |
| quote-age SLA | 96 ms 유지. USD-M 307,696표본 p99 48 ms로 재확인. 현물 bookTicker는 미측정 | `evidence/phase1/phase1e-close-20261002/sla-evidence-20261002.json` |
| 헤지 지연 | 69표본, 중위 4.4 s, p99 7.3 s. 실행기 2초 tick이 지배하는 Demo 엔지니어링 수치, 운영 SLA 아님 | 같은 파일 |
| Mainnet 수수료 | 10-02 GET 갱신: 현물 10/10 bps, 선물 2/5 bps(변동 없음) | `evidence/phase1/phase1e-close-20261002/binance-mainnet-fees-20261002.json` |
| Telegram | 알림 2줄 포맷, 명령 봇 `/status /profit /balance /daily /help` 실행 중 | [PHASE1_WEEK_RUN](docs/PHASE1_WEEK_RUN.md#telegram-commands) |
| Phase 2 바스켓 연구 | 완료·기각 `STOP_NO_EDGE`. 펀딩 +3.4 USDT vs 비용 13.8 USDT, PBO 0.77 | [Decision 0009](docs/decisions/0009-phase2-basket-result-stop-no-edge.md), `research_results/phase2/REPORT.md` |
| Phase 2b 위험 중립화 진단 | **보류 `SHELVE_FAMILY`.** 균형 복원·베타 사이징이 8/8 셀에서 개선, 그러나 연간 펀딩−비용 ±0.8 USDT, 에피소드 2~8개/년 | [Decision 0014](docs/decisions/0014-shelve-funding-cross-section-family.md), `research_results/phase2b/risk-diagnosis/REPORT.md` |
| Phase 2b maker 캐리 연구 | **게이트 불통과 `STOP_NO_EDGE`.** 단계 A는 fold 0에서만 거래(에피소드 2개), 단계 B는 거래 0건(스프레드 최대 0.69 bp). 손실 −6.68 USDT 중 가격 −6.62, 비용 0.48. 원인은 베타 불일치(롱이 베타 순노출 +31~35 USDT)와 진입 차단 중 레그 수 불균형 | [Decision 0013](docs/decisions/0013-phase2b-result-stop-no-edge.md), `research_results/phase2b/EPISODE_TRACE.md` |
| Phase 2c BTC·ETH 추세 연구 | **게이트 불통과 `STOP_NO_EDGE`.** walk-forward 연속 계좌(2022-08~2026-10) 순수익 200.6 USDT(연 8.4%, 슬리브 500), Sharpe 0.54 < BH-VT 0.78, PBO 0.34, 부트스트랩 구간 0 포함. 수익은 주로 롱(+340), 숏은 −80 | [Decision 0016](docs/decisions/0016-phase2c-result-stop-no-edge.md), `research_results/phase2c/REPORT.md` |
| MA200 후속 비교 | **`PAUSE_RESEARCH`.** C1~C4(수익 유지·낙폭·효율·최악 연도) 통과, C5 구현 실패(BTC 주문 234/322 건너뜀). 현물 보유가 Sharpe 0.93으로 가장 높음 | [Decision 0017](docs/decisions/0017-ma200-comparison-pause-research.md), `research_results/phase2c/ma200-comparison/REPORT.md` |
| MA200 슬리브 1,000 | **`OBSERVE_ELIGIBLE`(계획 이탈).** 순손익 675 vs 현물 보유 847, MDD 13.3% vs 22.6%, 최악 연도 −21 vs −92, 주문 건너뜀 3/99 | [Decision 0018](docs/decisions/0018-ma200-sleeve-1000-plan-departure.md), `research_results/phase2c/ma200-comparison-sleeve1000/REPORT.md` |
| MA200 전진 관측 | **진행 중, 2026-10-03 시작. 7일 운영 점검 통과(10-09).** 보고·전달 7/7, 점검 7/7, 건너뜀 0, 서버 재계산 동일, 예외 0. 10-09 가상 자산 974.71(−2.5%, 시장 하락; 선물 보유와 같음, 현물 보유 972.98) | [MA200_FORWARD_OBSERVATION](docs/MA200_FORWARD_OBSERVATION.md), 서버 `evidence/ma200-observation/` |
| MA200 Demo 실행 | **가동 중.** 매일 10:05 KST 실행, 10분마다 보호 장치(손실 중단·실행기 정지·불일치 → 자동 감축 청산·정지). Demo 검증 10단계 통과. 포지션 BTC 0.0034·ETH 0.080 롱. 7일 실행 7/7 정상(주문 없음), 보호 장치 878/879 정상(10-06 Demo 시간 초과 1회), 정지 0. 10-09 실행 자산 956.98, 최저 947.71(10-09 03:10 KST), 중단선 800 | [Decision 0020](docs/decisions/0020-ma200-live-risk-contract.md), 서버 `evidence/ma200-live-demo/` |
| Phase 3 | 실자본 미승인(Mainnet 잠금). 남은 것: −10% 중단선과 위험 수준 재결정, 실자본 ADR, 계좌·API 키 | Decision 0020 |

서버 cron(10-07부터): 11:10 KST 관측, 10:05 Demo 실행, 10분마다 보호 장치. 이미지 `freqtrade-v3-{live,observe}:current` = `e22190a`(`sha256:e8a2e8e0…`).
23시 운영 리포트·일요일 연구/주간 리포트는 Decision 0022로 중단(스크립트는 수동용으로 남김).
서버(`ft-tokyo`, `/home/kai/freqtrade-v3`) 컨테이너: `phase1-postgres` 실행, `phase1-telegram-bot` 실행,
`freqtrade_kai`(zero-entry shadow, 보고 중단) 실행. **주간 실행기는 없다**(마지막 `phase1-demo-week-run-20260928-restart1` exit 137,
대기 중 사용자 지시로 정지). Demo 계정: 선물 0, 미체결 없음, 현물 BTC `0.00050308` = 정산 잔량 69건 합계.
서버 작업 복사본은 `5e8afe1`, 현행 이미지 `freqtrade-v3-demo-auto:5e8afe1`(`sha256:ef02aba8…`).
저장소 브랜치 `codex/v2-to-v3-infrastructure`, 테스트 441개 통과(PostgreSQL 포함).

## 열린 문제

1. **중단선 −20%의 남은 위험**(Decision 0021): 25% 위험 수준에서 2021년 고점 부근에 시작했다면 최악 하락 24.8%로 중단선이 발동했을 것이다.
   알고 선택한 위험으로 기록했다.
2. **MA200 관측 7일 운영 점검 중**(2026-10-03~10-09). 7일은 수익성을 검증하지 못한다. 사용자는 그 뒤 실거래를 원하며,
   실거래 전 필요 사항은 관측 문서 §5. 규칙은 관측 중 바꾸지 않고, 개선은 월 1회 검토·새 등록·변경 후 데이터로만 평가한다.
2. **다중 레그·방향성 공통 교훈:** 위험 축소와 신규 진입 승인 분리, 베타·달러 명목 기준 노출 한도(Decision 0014),
   그리고 주문 단위·계획 슬리브 기준의 구현 가능성 점검을 규칙 조정보다 먼저 한다(Decision 0017).
3. **확인 검증용 미사용 데이터는 새 등록 이후 데이터뿐이다.**
4. `1a124d1`의 일시 거부 재시도와 청산 단계 예산 규칙은 테스트만 있고 실제 Demo 거부로는 아직 작동한 적 없다.
5. 진입 위험 결정 행에 관측 레버리지가 저장되지 않는다(디스패치 payload에는 있음).
6. **Demo 펀딩률은 실제 시장과 다르다.** 10-07 BTC Demo +0.028%/8h vs Mainnet −0.005%. Demo 실제 손익은 관측보다 펀딩만큼 불리하게
   나온다(10-07까지 Demo 펀딩 −2.52 vs 가상 약 −0.2). 실행 품질 판정은 가격·체결 기준으로, 펀딩은 관측 쪽 실제 시장 값으로 본다.
7. PostgreSQL 통합 테스트 72개는 이번 연구 작업 동안 건너뛰었다. 집행 경로를 바꾸거나 배포할 때는 반드시 실제로 통과시킨다.

## 다음 할 일 (순서대로)

1. 매일 Telegram(관측 11:10, Demo 실행 10:05, 보호 장치 발동 시) 확인. 관측은 계속되며 첫 방향 전환 때 실행 경로를 실제로 확인한다.
2. 실거래 준비: 실자본 사용 결정(ADR), 계좌와 선물 거래 권한 API 키(사용자 준비). 그 뒤 Mainnet 잠금 해제.
   ML은 Decision 0002에 따라 결정론적 전략이 두 비용 regime을 통과한 뒤에만.
2. 저장소: 로컬 커밋 push, `codex/v2-to-v3-infrastructure` → `main` PR·머지.
3. (선택) 진입 위험 결정에 레버리지 기록, 서버 격리 스키마 테스트 재확인.

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
