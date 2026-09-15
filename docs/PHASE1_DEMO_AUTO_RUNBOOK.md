# Demo 자동 캐리 실행

## 범위

`scripts/run_phase1_demo_auto.py`는 연결 진단이나 접수 후 취소 probe가 아니다.
Nautilus의 실제 Binance Demo 주문과 체결을 사용해 다음 순서를 자동 수행한다.

1. 전용 Demo 계정과 두 레그 실시간 호가를 연결한다.
2. 명시적 engineering 트리거를 독립 위험 프로세스가 승인하면 현물을 IOC 매수한다.
3. REST·스트림 체결을 원장에 대사하고 BTC 수수료를 뺀 수량으로 선물을 헤지한다.
4. 진입 시 기록한 300초 보유 기한이 지나면 reduce-only 선물 매수로 숏을 종료한다.
5. 선물 무포지션 확인 후 해당 에피소드가 소유한 현물만 매도한다.
6. 양쪽이 정확히 0이면 CLOSED, 최소주문 미만 잔고가 남으면 dust와 미완료 상태를 유지한다.

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
