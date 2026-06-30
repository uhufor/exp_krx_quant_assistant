import json
import math

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
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
    strategies: str = typer.Option(
        None, "--strategies", "-s",
        help="실행할 전략 (콤마 구분). 예: ma_crossover,macd  생략하면 설정 기준 전체 실행.",
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

    enabled = [s.strip() for s in strategies.split(",")] if strategies else None

    job = DailyJob(settings=settings, db=db, provider=provider, notifier=notifier)
    result = job.run(dry_run=dry_run, enabled_strategies=enabled)

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


@app.command("show-reports")
def show_reports(
    run_id: str = typer.Option(None, "--run-id", "-r", help="조회할 run_id (기본: 최근 실행)"),
    report_type: str = typer.Option("A", "--type", "-t", help="리포트 종류: A | B | all"),
):
    """최근 실행 결과를 종목별로 출력."""
    import duckdb

    settings = get_settings()
    con = duckdb.connect(settings.duckdb_path)

    if run_id is None:
        row = con.execute("SELECT run_id FROM signals ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            console.print("[yellow]저장된 신호가 없습니다. run-daily를 먼저 실행하세요.[/yellow]")
            raise typer.Exit(0)
        run_id = row[0]

    console.print(f"\n[bold]Run ID:[/bold] {run_id}\n")

    signals = con.execute(
        "SELECT id, symbol, strategy, signal_type, score, metrics, risk_flags "
        "FROM signals WHERE run_id=? ORDER BY symbol, strategy",
        [run_id],
    ).fetchall()

    if not signals:
        console.print(f"[yellow]run_id={run_id} 에 해당하는 신호가 없습니다.[/yellow]")
        raise typer.Exit(0)

    _SIGNAL_COLOR = {"buy": "green", "sell": "red", "watch": "yellow", "hold": "cyan"}

    summary = Table(title="신호 요약", show_lines=True)
    summary.add_column("종목", style="bold")
    summary.add_column("전략")
    summary.add_column("신호")
    summary.add_column("점수", justify="right")
    summary.add_column("총수익률", justify="right")
    summary.add_column("MDD", justify="right")
    summary.add_column("Sharpe", justify="right")
    summary.add_column("승률", justify="right")
    summary.add_column("리스크")

    sig_ids = []
    for sig in signals:
        sig_id, sym, strategy, sig_type, score, metrics_json, risk_json = sig
        sig_ids.append((sig_id, sym, strategy, sig_type))
        m = json.loads(metrics_json)
        rf = json.loads(risk_json)
        sharpe = m.get("sharpe", float("nan"))
        sharpe_str = f"{sharpe:.2f}" if not math.isnan(sharpe) else "N/A"
        color = _SIGNAL_COLOR.get(sig_type, "white")
        summary.add_row(
            sym,
            strategy,
            f"[{color}]{sig_type.upper()}[/{color}]",
            f"{score:.2f}",
            f"{m.get('total_return', 0):.1%}",
            f"{m.get('mdd', 0):.1%}",
            sharpe_str,
            f"{m.get('win_rate', 0):.1%}",
            ", ".join(rf) if rf else "-",
        )
    console.print(summary)

    if report_type == "all":
        types_to_show = ["A", "B"]
    else:
        types_to_show = [report_type.upper()]

    for sig_id, sym, strategy, sig_type in sig_ids:
        for rtype in types_to_show:
            row = con.execute(
                "SELECT content FROM reports WHERE signal_id=? AND report_type=?",
                [sig_id, rtype],
            ).fetchone()
            if row:
                console.print(Panel(
                    Markdown(row[0]),
                    title=f"[bold]{sym}[/bold] · {strategy} · Report {rtype}",
                    border_style="dim",
                ))


@app.command("list-strategies")
def list_strategies():
    """사용 가능한 전략 목록과 현재 활성화 상태 출력."""
    from quant_krx.config.settings import ALL_STRATEGIES

    settings = get_settings()
    enabled = set(settings.strategy.enabled)

    _DESCRIPTIONS = {
        "ma_crossover":  "MA 교차 — 단기(20일)/장기(60일) 이동평균 골든·데드크로스",
        "rsi_breakout":  "RSI 돌파 — RSI 30 이하 매수 / 70 이상 매도 (역추세)",
        "bollinger_band": "볼린저 밴드 — 가격이 밴드 이탈 시 평균 회귀 기대",
        "macd":          "MACD — 12/26 EMA 차이의 시그널선 교차 (모멘텀)",
        "momentum":      "12-1 모멘텀 — 12개월 수익률 기반 추세 지속성 (Jegadeesh & Titman)",
    }

    table = Table(title="전략 목록", show_lines=True)
    table.add_column("이름", style="bold")
    table.add_column("상태")
    table.add_column("설명")

    for name in ALL_STRATEGIES:
        status = "[green]ON[/green]" if name in enabled else "[dim]OFF[/dim]"
        table.add_row(name, status, _DESCRIPTIONS.get(name, ""))

    console.print(table)
    console.print(
        "\n[dim]전략 선택: uv run python -m quant_krx run-daily "
        "--strategies ma_crossover,macd[/dim]"
    )


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
