# PROGRESS

기준일: 2026-10-19 KST. 새 세션은 이 파일부터 읽는다. 상세 근거는 각 링크 문서에 있고,
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
10-19 사용자가 수익률 확인을 최우선으로 요구해, Binance USDT 전 종목(상장폐지 포함)·2017년~ 데이터로 6개 전략군 120개 설정을
사전등록 탐색했다(Phase 2d). 개발 게이트 통과 없음 `STOP_NO_EDGE`([Decision 0024](docs/decisions/0024-phase2d-stop-and-register-phase2e.md)).
가장 일관된 묶음(상위 10종목 모멘텀+BTC 필터) 앙상블을 단일 가설로 holdout(2025-01~2026-09)에서 한 번 검증했으나
−3.7%(BTC −19.6%)로 `FAIL`([Decision 0025](docs/decisions/0025-phase2e-result-fail.md)).
10-20 사용자 요청(추세 롱숏·하락장 숏 위주, 새 정보)으로 66개 설정을 사전등록 탐색했다(Phase 2f). 숏 쪽은 2022년 하락장을 포함해도 수익이 없었고 개발 게이트 통과 없음 `STOP_NO_EDGE`.
테이커 매수 흐름 앙상블(T1)을 단일 가설로 2024-01~2026-09에서 한 번 검증했다. +381%, Sharpe 1.86, MDD 21%로 V1~V4는 통과했지만 DSR 0.84 < 0.95로 `FAIL`([Decision 0028](docs/decisions/0028-phase2g-result-fail-dsr.md)). 수익의 약 절반은 숏 스퀴즈 종목의 펀딩 수취이고 상위 10주에 집중됐다.
사용자 결정으로 MA200 Demo 실행기를 종료하고(최종 949.86 USDT) 같은 Demo 계좌에서 T1을 주 1회 실제 주문으로 관측한다([Decision 0029](docs/decisions/0029-t1-demo-execution-retire-ma200-executor.md)). 첫 리밸런싱 10-26 09:05 KST. MA200 가상 관측은 계속한다.
실거래는 아직 승인되지 않았다(Mainnet 잠금). 실자본·Mainnet 주문은 어디에도 승인되지 않았다.

## 2026-10-18 추가 연구 — 다이버전스 단타

사용자 요청으로 기존 MA200과 분리된 RSI 다이버전스 연구 후보를 개발하고,
BTC·ETH 공식 1분봉으로 2025-10~2026-09를 백테스트했다(1분/5분, 기본/스트레스 비용).
기본 비용 기준 1분봉 30회·−30.72 USDT, 5분봉 9회·−12.27 USDT(자본 1,000).
두 후보 모두 최소 100회 미달 **`INSUFFICIENT_TRADES`**, 관측 손익도 음수여서 승격하지 않는다.
운영 서버·MA200·Demo 주문 경로는 변경하지 않았다. 아래 운영 표는 기존 10-09 기록이다.
근거: [등록](docs/DIVERGENCE_PREREGISTRATION.md), [결과](research_results/divergence/REPORT.md),
[Decision 0023](docs/decisions/0023-divergence-scalp-research-insufficient.md).

## 2026-10-18 추가 연구 — 캔들 스캘핑·제한 분할 매수

눌림목·박스권·돌파를 분리해 30분봉 신호로 구현하고, 단일 진입/최대 2회 추가 매수와
기본/스트레스 체결을 비교했다(BTC·ETH, 2025-10~2026-09, 자본 1,000 USDT).
12개 조합 모두 손실, 6개 전략·사이징 후보 모두 **`STOP_NO_EDGE`**다.
기본 비용 단일/분할 순손익: 눌림목 −41.20/−48.36, 박스권 −84.39/−92.09,
돌파 −64.70/−65.22 USDT. 승률 약 57~60%에도 손실이며, 비용 전 가격 손익도 모두 음수다.
추가 매수는 관측 순손익을 개선하지 못했다. 무제한 물타기·배율 증가는 적용하지 않았다.
기존 운영 경로는 변경하지 않았으며 아래 운영 표는 10-09 스냅샷이다.
근거: [등록](docs/CANDLE_SCALP_PREREGISTRATION.md), [결과](research_results/candle-scalp/REPORT.md),
[Decision 0024](docs/decisions/0024-candle-scalp-stop-no-edge.md).

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
| MA200 Demo 실행 | **종료(10-20, Decision 0029).** 최종 949.86 USDT. 이하 종료 전 기록: 매일 10:05 KST 실행, 10분마다 보호 장치(손실 중단·실행기 정지·불일치 → 자동 감축 청산·정지). Demo 검증 10단계 통과. 포지션 BTC 0.0034·ETH 0.080 롱. 7일 실행 7/7 정상(주문 없음), 보호 장치 878/879 정상(10-06 Demo 시간 초과 1회), 정지 0. 10-09 실행 자산 956.98, 최저 947.71(10-09 03:10 KST), 중단선 800 | [Decision 0020](docs/decisions/0020-ma200-live-risk-contract.md), 서버 `evidence/ma200-live-demo/` |
| Phase 2d 다종목 탐색 | **`STOP_NO_EDGE`.** 120개 설정, 최고 F1(Sharpe 1.11, CAGR 72%, MDD 76%) DSR 0.55·PBO 0.47. 기준선 BTC Sharpe 0.75 | [Decision 0024](docs/decisions/0024-phase2d-stop-and-register-phase2e.md), `research_results/phase2d/` |
| Phase 2e 앙상블 확인 | **`FAIL`.** holdout −3.7%, Sharpe 0.19, MDD 40% (BTC −19.6%, −0.08, 53%). 보유보다 덜 잃었지만 수익 아님. holdout 소진 | [Decision 0025](docs/decisions/0025-phase2e-result-fail.md), `research_results/phase2e/` |
| Phase 2f 롱숏·포지션 탐색 | **`STOP_NO_EDGE`.** 66개 설정. 숏 쪽 손실(R1 −4%, R2 −53%), 숏 비중 큰 변형이 항상 최하. P3 테이커 흐름 6개 모두 Sharpe 1.47~1.83이나 PBO 0.73 | [Decision 0027](docs/decisions/0027-phase2f-stop-and-register-phase2g.md), `research_results/phase2f/` |
| Phase 2g 테이커 흐름 확인 | **`FAIL`(DSR만).** 검증 +381%, Sharpe 1.86, MDD 21%(BTC +93%, 0.75, 53%). 2024 +48%, 2025~26 +250%. DSR 0.84. 펀딩 제외 +189%. 검증 구간 소진 | [Decision 0028](docs/decisions/0028-phase2g-result-fail-dsr.md), `research_results/phase2g/` |
| T1 Demo 실행 | **가동(10-20 초기화).** 매일 09:05 KST, 월요일 리밸런싱, 10분 보호 장치, 중단선 650. 실행 검증 13/13 체결 | [Decision 0029](docs/decisions/0029-t1-demo-execution-retire-ma200-executor.md), 서버 `evidence/t1-live-demo/` |
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
