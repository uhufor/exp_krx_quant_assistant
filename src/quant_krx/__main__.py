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


@app.command("list-factors")
def list_factors_cmd(
    category: str = typer.Option(
        None, "--category", "-c", help="카테고리 필터 (예: value, quality, growth)"
    ),
):
    """등록된 팩터 목록을 출력한다."""
    from quant_krx.factors import list_factors
    from quant_krx.factors.metadata import FactorCategory

    if category is not None:
        valid = {c.value for c in FactorCategory}
        if category not in valid:
            console.print(
                f"[red]알 수 없는 카테고리 '{category}'입니다. "
                f"사용 가능: {', '.join(sorted(valid))}[/red]"
            )
            raise typer.Exit(1)

    factors = list_factors(category)

    table = Table(title="팩터 목록", show_lines=True)
    table.add_column("id", style="bold")
    table.add_column("표시명")
    table.add_column("카테고리")
    table.add_column("설명")

    for meta in factors:
        table.add_row(meta.id, meta.display_name, meta.category.value, meta.description)

    console.print(table)


@app.command("show-factor")
def show_factor_cmd(factor_id: str = typer.Argument(..., help="조회할 팩터 id")):
    """팩터 상세 정보(파라미터 명세·산출 컬럼·필요 데이터)를 출력한다."""
    from quant_krx.factors.errors import UnknownFactorError
    from quant_krx.factors.registry import get_factor

    try:
        factor = get_factor(factor_id)
    except UnknownFactorError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e

    meta = factor.metadata

    table = Table(title=f"팩터 상세: {meta.id}", show_lines=True)
    table.add_column("항목")
    table.add_column("값")
    table.add_row("표시명", meta.display_name)
    table.add_row("카테고리", meta.category.value)
    table.add_row("설명", meta.description)
    table.add_row("산출 컬럼", ", ".join(meta.output))
    table.add_row("필요 데이터", ", ".join(meta.required_data))

    if meta.params:
        param_lines = []
        for p in meta.params:
            constraint = []
            if p.min is not None:
                constraint.append(f"min={p.min}")
            if p.max is not None:
                constraint.append(f"max={p.max}")
            if p.choices is not None:
                constraint.append(f"choices={p.choices}")
            suffix = f" ({', '.join(constraint)})" if constraint else ""
            param_lines.append(
                f"{p.name}: {p.type.__name__} = {p.default}{suffix} — {p.description}"
            )
        table.add_row("파라미터", "\n".join(param_lines))
    else:
        table.add_row("파라미터", "(없음)")

    console.print(table)

    if "financials" in meta.required_data:
        console.print(
            "[yellow]참고: DART 재무제표 연동은 아직 구현되지 않았습니다(Deferred). "
            "현재는 값이 NaN으로 반환됩니다.[/yellow]"
        )


@app.command("fetch-fundamental")
def fetch_fundamental_cmd(
    symbols: str = typer.Option(
        None, "--symbols", "-s", help="콤마 구분 종목 목록 (생략 시 watchlist 전체)"
    ),
    start: str = typer.Option(None, "--start", help="시작일 YYYY-MM-DD (기본: 5년 전)"),
    end: str = typer.Option(None, "--end", help="종료일 YYYY-MM-DD (기본: 오늘)"),
    kind: str = typer.Option(
        "all", "--kind", "-k", help="수집 종류: valuation | financials | all"
    ),
    provider: str = typer.Option(
        "fixture", "--provider", "-p", help="데이터 제공자: fixture | pykrx"
    ),
):
    """밸류에이션/재무제표 데이터를 수집해 DuckDB에 저장한다 (멱등)."""
    from datetime import date, datetime, timedelta

    from quant_krx.data.fixture_fundamental import FixtureFundamentalAdapter
    from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter
    from quant_krx.data.upsert import upsert_fundamental
    from quant_krx.storage.db import Database

    if kind not in ("valuation", "financials", "all"):
        console.print(
            f"[red]알 수 없는 --kind '{kind}'. 사용 가능: valuation, financials, all[/red]"
        )
        raise typer.Exit(1)
    if provider not in ("fixture", "pykrx"):
        console.print(f"[red]알 수 없는 --provider '{provider}'. 사용 가능: fixture, pykrx[/red]")
        raise typer.Exit(1)

    settings = get_settings()
    sym_list = [s.strip() for s in symbols.split(",")] if symbols else settings.load_watchlist()
    if not sym_list:
        console.print(
            "[red]수집할 종목이 없습니다. watchlist를 설정하거나 --symbols를 지정하세요.[/red]"
        )
        raise typer.Exit(1)

    end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
    start_date = (
        datetime.strptime(start, "%Y-%m-%d").date() if start else end_date - timedelta(days=365 * 5)
    )
    as_of = date.today()

    adapter = FixtureFundamentalAdapter() if provider == "fixture" else PyKrxFundamentalAdapter()

    db = Database(settings.duckdb_path)
    db.connect()

    table = Table(title="fetch-fundamental 결과", show_lines=True)
    table.add_column("종류")
    table.add_column("수용")
    table.add_column("제외")
    table.add_column("제외 사유(일부)")

    with db.cursor() as conn:
        if kind in ("valuation", "all"):
            try:
                frame = adapter.fetch_valuation(sym_list, start_date, end_date)
            except NotImplementedError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(1) from e
            frame = frame.assign(source=adapter.source_name, fetched_at=datetime.utcnow())
            result = upsert_fundamental(conn, "fundamental_daily", frame, as_of=as_of)
            reasons = ", ".join(f"{e.symbol}:{e.reason.value}" for e in result.excluded[:3])
            table.add_row("valuation", str(result.accepted), str(len(result.excluded)), reasons)

        if kind in ("financials", "all"):
            try:
                frame = adapter.fetch_financials(sym_list, start_date, end_date)
            except NotImplementedError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(1) from e
            frame = frame.assign(source=adapter.source_name, fetched_at=datetime.utcnow())
            result = upsert_fundamental(conn, "financial_statements", frame, as_of=as_of)
            reasons = ", ".join(f"{e.symbol}:{e.reason.value}" for e in result.excluded[:3])
            table.add_row("financials", str(result.accepted), str(len(result.excluded)), reasons)

    console.print(table)
    db.close()


if __name__ == "__main__":
    app()
