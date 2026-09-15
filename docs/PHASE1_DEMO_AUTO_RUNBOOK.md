# Demo 자동 캐리 실행

## 범위

`scripts/run_phase1_demo_auto.py`는 연결 진단이나 접수 후 취소 probe가 아니다.
Nautilus의 실제 Binance Demo 주문과 체결을 사용해 다음 순서를 자동 수행한다.

1. 전용 Demo 계정과 두 레그 실시간 호가를 연결한다.
2. 명시적 engineering 트리거를 독립 위험 프로세스가 승인하면 현물을 IOC 매수한다.
3. REST·스트림 체결을 원장에 대사하고 BTC 수수료를 뺀 수량으로 선물을 헤지한다.
4. 진입 시 기록한 300초 보유 기한이 지나면 reduce-only 선물 매수로 숏을 종료한다.
5. 선물 무포지션 확인 후 해당 에피소드가 소유한 현물만 매도한다.
6. 양쪽이 정확히 0이면 CLOSED. 최소주문 미만 현물 잔량만 남고 선물이 flat이면
   감사 기록(`episode_residuals`, 비용, incident, 대사, 전이)과 함께 소유 잔량으로 정산해
   CLOSED로 보낸다. 잔량은 매도하지 않고 다음 에피소드 baseline이 상속한다.
   `exact_flat=false`로 보고하며 정확한 flat과 구분한다.

경제적 캐리 진입 승인은 아니다. 약 220 USDT 명목의 합성 Demo 트리거이며
비용·수익률·시장 알파나 실계정 승격 근거로 사용하지 않는다. 정상 캐리 정책의
미확인 Spot exchange-age 또는 미완성 비용 원장을 참으로 바꾸지 않았다.

## 안전 경계

- Mainnet 주문·자금 이체·광범위 취소는 없다. 전용 `BINANCE_DEMO_*`만 읽는다.
- 커밋·태그된 소스를 immutable 이미지로 빌드한다. 이미지에는 키를 넣지 않는다.
- `configs/phase1-engineering.json` 해시와 Git/이미지/lock 해시를 manifest에 기록한다.
- 시작 전 현물 BTC 잔고는 `episode_baselines`에 고정한다. 기존 보유분을 매도하지 않는다.
- 종료 요청은 DB에 먼저 저장하며 재시작으로 헤지 모드로 되돌아가지 않는다.
- 한 manifest당 신규 에피소드 한 번이다. 같은 `--started-at`은 재시작 시 재사용한다.
  다른 ID를 만들어 불확실한 주문이나 dust를 우회해서는 안 된다.
- 미확인 전송은 재전송하지 않는다. REST 재확인 실패 3회 시 신규 주문을 중단한다.
- 로컬 receive-gap 2초/IOC 10 bps는 보수적인 시험 상한이지 측정된 시장 SLA가 아니다.
- 실제 BTC 수수료는 보유량 계산에 사용한다. Demo 수수료를 mainnet 비용의 대용으로
  간주하지 않는다.
- stream callback과 제어·REST 처리는 별도 DB 연결을 사용한다.
- DB 실행기 잠금 및 계정 주문 잠금을 사용한다. raw 외부 주문까지 차단하는 잠금은 아니므로
  이 Demo 계정의 BTCUSDT에 다른 프로그램이나 수동 주문을 동시에 사용하지 않는다.

## 관측 및 재시작

서버의 `evidence/phase1/demo-auto-20260915/run.json`에 시작, 제출, 스트림 체결,
종료·오류와 manifest가 기록된다. 주문의 최종 사실은 PostgreSQL `orders`, `fills`,
`order_dispatches`, `order_recovery_checks`, `fill_event_inbox`와 계정 GET 대사로 확인한다.
`submitted=true`는 로컬 enqueue이고 `fill_confirmed=true`와 다르다.

Telegram 전송 실패는 주문 상태를 바꾸거나 주문 재전송을 일으키지 않는다.
현재 파일에는 Telegram 수신 성공 여부가 포함되지 않으므로 전송 시도와 전달 확인을
구분한다.

컨테이너는 자동 재시작하지 않는다. 같은 소스·이미지·`--started-at`으로 재시작하면
기존 intent를 찾아 대사 후 이어간다. 버전 변경 후 포지션 인수는 별도 검증이 필요하다.
실행 중 강제 종료, stream 오류, unresolved 주문 발생 시 다른 실행기를 띄우지 말고
기존 intent·실제 잔고·미체결 주문을 먼저 확인한다.

## 아직 완료가 아닌 것

한 사이클 성공은 일주일 무인 반복 또는 Phase 1E 완료와 다르다. 자동 취소·부분체결
장애 복구의 실환경 관측, dust 소유권을 유지하는 차기 에피소드 정책, 장기 실행 및
경제적 진입 게이트는 별도다. 아래 실행 결과에도 이 범위를 유지한다.

## 실제 실행 — 2026-09-15 KST

| 시각 | 주문 | BTC 수량 | 체결가 USDT |
|---|---|---:|---:|
| 18:06 | 현물 BUY | 0.00285 | 76935.43 |
| 18:06 | 선물 SELL | 0.0028 | 76942.40 |
| 18:11 | 선물 BUY reduce-only | 0.0028 | 76943.90 |
| 18:16 | 복구 후 현물 SELL | 0.00284 | 76969.68 |

첫 이미지 source `3f0da66699724883037bdf09516f86dc57b15590`,
image `sha256:4995ef790243f75511375037239fc18a79fc52bf47064263b4768b08c397bf08`.
복구 source `96dde03b97367335f09f31da1120c08dfba1eaa1`,
image `sha256:8653914615dbdf7ca91051821752bccf09198b2dcc436af322f449a1dff08431`.

현물 매수 수수료는 `0.00000285 BTC`였다. 순 현물 보유 `0.00284715 BTC`에서
매도 `0.00284 BTC`를 차감한 `0.00000715 BTC`는 소유 잔량으로 남았다. 기준 잔고를
재설정하거나 CLOSE로 숨기지 않았다. 계정 GET의 무포지션/미체결 확인과 구분해
원장 체결 합계에서도 선물 net `0`, 활성 명령 `0`, 적용된 inbox `4`를 확인했다.

중간 장애 원인: pinned 어댑터의 밀리초→나노초 float 변환에서
`1789463468936999936`을 microsecond 단위로 버림 처리하면서 REST의
`09:11:08.937000`과 저장된 `09:11:08.936999`가 달라졌다. 나머지 체결 필드는 일치했다.
새 체결은 256ns 이내의 millisecond 변환 오차만 정규화한다. 기존 기록의 1us 수정은
원본 inbox가 입증하는 경우만 허용하고, 숫자·ID·수수료가 다르면 전체 트랜잭션을
rollback한다. 원본 inbox, BLOCKED 3건 및 수정 audit는 보존되어 있다.

복구는 명시한 intent와 이전 manifest를 확인한 close-only 인수다. 새 entry를 만들지
않았으며 새 source/image/manifest를 baseline evidence에 기록했다. 이 인수는 통상적인
동일 이미지 재시작과 다르다. 초기 컨테이너 exit 2, 복구 컨테이너 exit 0이지만 후자는
잔량 감지 후 정상 중단이라는 뜻이지 flat 또는 완료 승인이 아니다.


## 잔량 정산

2026-09-15 19:29 KST에 사용자 승인 후 아래 명령을 실행해 에피소드
`09a7f1cf-51d1-43ab-b8a6-fa65041ba6ed`를 `ABORTING → CLOSED`로 정산했다
(종료 코드 0, 주문 0건, Telegram 전달 확인, 증거
`evidence/phase1/residual-settlement-20260915.json`). 명령은 주문 없이 GET과 원장 기록만 수행한다. 종료 요청·선물 flat·
미체결 0·체결 전부 반영·매도 불가 잔량 조건 중 하나라도 어긋나면 아무것도 바꾸지 않고
종료 코드 2를 반환한다. `--notify`는 `[DEMO][PHASE1]` Telegram 알림을 보낸다.

```bash
cd /home/kai/freqtrade-v3
set -a; . ./.phase1-database.env; set +a
IMG=freqtrade-v3-demo-auto:b6d3bbd
docker run --name phase1-residual-settle-20260915 \
  --network phase1-demo-evidence --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m --user 1002:1002 \
  -e PHASE1_DATABASE_DSN \
  -e PHASE1_BUILD_SOURCE_SHA=b6d3bbdad0e47b1a7d64514a472843e3273506fe \
  -e PHASE1_IMAGE_DIGEST="$(docker image inspect --format '{{.Id}}' "$IMG")" \
  -v /home/kai/freqtrade-v3/.env:/run/phase1.env:ro \
  -v /home/kai/freqtrade-v3/evidence/phase1/demo-auto-20260915:/evidence \
  --entrypoint /app/.venv/bin/python "$IMG" scripts/settle_phase1_residual.py \
  --credentials-env-file /run/phase1.env \
  --output /evidence/residual-settlement-20260915.json \
  --intent-id 09a7f1cf-51d1-43ab-b8a6-fa65041ba6ed --settle-residual --notify
```

성공 시 출력 JSON의 `settlement.state`가 `CLOSED`, `residual_base`가 `0.00000715`,
`open_intents`가 `0`이어야 한다. 실행 후 증거 파일을 저장소 `evidence/phase1/`로 복사한다.


## 반복·재시작 검증 — 2026-09-15 KST

소스 `66bf69d`, 이미지 `freqtrade-v3-demo-auto:66bf69d`(`sha256:41fb5c67…`), 설정
`configs/phase1-verify-repeat.json`(에피소드 2회, 간격 900초, 총 창 3600초, 보유 300초,
레그 약 220 USDT). 실제 Demo 주문 8건이 모두 FILLED이며 Mainnet 주문·실자본은 없다.

| 시각(UTC) | 이벤트 | 수량 BTC | 체결가 USDT |
|---|---|---:|---:|
| 11:35:13 | 에피소드 1 현물 BUY | 0.00285 | 76939.29 |
| 11:35:17 | 선물 SELL (헤지) | 0.0028 | 76899.40 |
| 11:36 | **`docker kill`로 실행기 강제 종료** (exit 137, 보유 중) | | |
| 11:37:24 | 같은 `--started-at`로 재시작 → `RESUMING` 열린 intent 재개 | | |
| 11:40:13 | 선물 BUY reduce-only (보유 기한 도달) | 0.0028 | 76907.10 |
| 11:40:18 | 현물 SELL (소유분만) | 0.00284 | 76914.00 |
| 11:40:23 | 잔량 `0.00000715` 자동 정산 → CLOSED (`exact_flat=false`) | | |
| 11:55:23 | 15분 간격 후 에피소드 2 현물 BUY | 0.00286 | 76901.69 |
| 11:55:28 | 선물 SELL (헤지) | 0.0028 | 76845.90 |
| 12:00:24 | 선물 BUY reduce-only | 0.0028 | 76908.00 |
| 12:00:29 | 현물 SELL | 0.00285 | 76926.88 |
| 12:00:34 | 잔량 `0.00000714` 자동 정산 → CLOSED | | |
| 12:00:35 | 실행기 정상 종료 `run_window_exhausted` (exit 0) | | |

확인 사항:

- 재시작 복구 1회: 강제 종료 시점의 상태 `HEDGE_REQUIRED`(현물 순보유 0.00284715 대
  숏 0.0028, 미만 lot 잔여)를 재시작 실행기가 재개해 재헤지 없이 종료를 완료했다.
- 에피소드 2 baseline은 `spot_base=0.00001430`, `inherited_residual_base=0.00001430`으로
  앞선 두 에피소드의 정산 잔량을 기존 보유분으로 상속했고 매도하지 않았다.
- 원장: 거부된 전이 0, 미해결 recovery 0, 미처리 inbox 0, 활성 명령 0, 열린 incident 0,
  체결 12건(이전 에피소드 4건 포함) 전부 FILLED. 모든 알림은 `telegram_delivered=true`.
- 종료 사유가 `episode_budget_complete`가 아닌 `run_window_exhausted`인 이유는 검증 run
  식별자 `--started-at`을 실제 시작보다 35분 앞선 11:00Z로 지정했고 창이 3600초였기
  때문이다. 두 에피소드는 모두 완료됐고 정지 규칙은 설계대로 동작했다.
- IOC 미체결·부분체결은 이번 실행에서 발생하지 않았다(모두 즉시 전량 체결). 해당 경로는
  terminal 주문의 command 비활성화와 6회 IOC 상한으로 코드·테스트에서 다룬다.

증거: `evidence/phase1/demo-verify-repeat-20260915/run.json`(강제 종료 전),
`run-restart1.json`(재시작 후). 이는 반복 실행기와 재시작 복구의 실환경 검증이며
1주 관측 시작이나 Phase 1E 완료(에피소드 50회, 재시작 3회)는 아니다.
