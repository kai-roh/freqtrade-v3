from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_operations_report_wrapper_is_fail_closed_and_kst() -> None:
    script = (ROOT / "scripts/run_operations_report.sh").read_text()

    assert "set -euo pipefail" in script
    assert 'REPORT_TZ="${REPORT_TZ:-Asia/Seoul}"' in script
    assert 'PERIOD="${1:-}"' in script
    assert 'daily" && "$PERIOD" != "weekly' in script
    assert "--telegram-always" in script


def test_scheduled_research_refreshes_data_archives_results_and_reports() -> None:
    script = (ROOT / "scripts/run_scheduled_research.sh").read_text()

    assert "set -Eeuo pipefail" in script
    assert "flock -n" in script
    assert 'DATA_DAYS="${V3_DATA_DAYS:-365}"' in script
    assert 'TRAIN_DAYS="${V3_TRAIN_DAYS:-180}"' in script
    assert '--train-days "$TRAIN_DAYS"' in script
    assert "./scripts/download_research_data.sh" in script
    assert "./scripts/run_walk_forward.sh" in script
    assert "V3_RESEARCH_RUN_ID must use YYYYMMDDTHHMMSSZ" in script
    assert 'mv -Tf "$LATEST_TMP" "$OUTPUT_ROOT/latest"' in script
    assert "./scripts/run_operations_report.sh weekly" in script


def test_cron_contract_schedules_daily_and_weekly_kst_jobs() -> None:
    cron = (ROOT / "deploy/freqtrade-v3.cron").read_text()

    assert "TZ=Asia/Seoul" in cron
    assert "CRON_TZ=" not in cron
    assert "0 23 * * *" in cron
    assert "run_operations_report.sh daily" in cron
    assert "10 23 * * 0" in cron
    assert "run_scheduled_research.sh" in cron
    assert "/freqtrade-v3/reports/logs/" in cron
    assert "/user_data/reports/" not in cron
    assert "freqtrade-v2" not in cron


def test_cron_installer_checks_host_timezone_and_bootstraps_logs() -> None:
    installer = (ROOT / "deploy/install_server_cron.sh").read_text()

    assert "set -euo pipefail" in installer
    assert 'HOST_TIMEZONE="$(timedatectl show -p Timezone --value' in installer
    assert '"$HOST_TIMEZONE" != "Asia/Seoul"' in installer
    assert "install -d -m 0700 reports reports/daily reports/weekly reports/logs" in installer
    assert "crontab deploy/freqtrade-v3.cron" in installer


def test_walk_forward_runner_forwards_research_overrides() -> None:
    script = (ROOT / "scripts/run_walk_forward.sh").read_text()

    assert '"$@"' in script
