import typer
from rich.console import Console
from rich.table import Table

from quant_krx import __version__
from quant_krx.config.settings import get_settings

app = typer.Typer(name="quant-krx", help="KRX Korean Stock Quant Trading Assistant")
console = Console()


@app.command("run-daily")
def run_daily(
    dry_run: bool = typer.Option(
        True, "--dry-run/--no-dry-run", help="알림 발송 없이 리포트만 생성"
    ),
):
    """일일 퀀트 파이프라인 실행."""
    from quant_krx.data.fdr_adapter import FDRAdapter
    from quant_krx.jobs.daily import DailyJob
    from quant_krx.storage.db import Database

    settings = get_settings()
    db = Database(settings.duckdb_path)
    db.connect()

    provider = FDRAdapter()
    notifier = None

    if not dry_run:
        from quant_krx.notify.telegram import TelegramNotifier
        if not settings.notify.telegram_bot_token:
            console.print("[red]TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.[/red]")
            raise typer.Exit(1)
        notifier = TelegramNotifier(
            bot_token=settings.notify.telegram_bot_token,
            chat_id=settings.notify.telegram_chat_id,
            db=db,
        )

    job = DailyJob(settings=settings, db=db, provider=provider, notifier=notifier)
    result = job.run(dry_run=dry_run)

    table = Table(title=f"Daily Job: {result.run_id}")
    table.add_column("항목")
    table.add_column("값")
    table.add_row("상태", result.status)
    table.add_row("종목 수", str(result.symbol_count))
    table.add_row("신호 수", str(result.signal_count))
    table.add_row("Report A", str(result.report_a_count))
    table.add_row("Report B", str(result.report_b_count))
    table.add_row("알림 IDs", str(result.notification_ids))
    if result.errors:
        table.add_row("오류", "\n".join(result.errors[:3]))
    console.print(table)

    if result.status == "error":
        raise typer.Exit(1)


@app.command("validate-config")
def validate_config():
    """설정 파일 유효성 검사 (네트워크 없이)."""
    settings = get_settings()
    ok, msg = settings.validate_watchlist()

    table = Table(title="Config Validation")
    table.add_column("Item", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Value")

    table.add_row("DuckDB Path", "✓", settings.duckdb_path)
    table.add_row("Report Dir", "✓", settings.report_dir)
    table.add_row("Provider", "✓", settings.provider.primary)
    table.add_row("Watchlist", "✓" if ok else "✗", msg)
    table.add_row("LLM Mock", "✓" if settings.llm.mock else "—", str(settings.llm.mock))

    console.print(table)

    if not ok:
        raise typer.Exit(1)


@app.command("version")
def show_version():
    """버전 정보 출력."""
    console.print(f"quant-krx {__version__}")


if __name__ == "__main__":
    app()
