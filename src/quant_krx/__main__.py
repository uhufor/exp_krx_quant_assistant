import dataclasses
import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from quant_krx import __version__
from quant_krx.config.settings import get_settings

# pydantic-settings의 env_file 로딩은 os.environ에 반영되지 않는다. pykrx 등 일부
# 서드파티 라이브러리가 os.getenv()로 자격증명(KRX_ID/KRX_PW)을 직접 읽으므로,
# 다른 임포트가 pykrx를 lazy-import하기 전에 .env를 os.environ에 명시적으로 반영한다.
load_dotenv()

# settings.log_level은 선언만 되어 있고 어디서도 logging에 연결되지 않아 quant_krx.*
# 로거의 logger.info()가 전부 무음 처리되던 기존 결함 — 여기서 한 번만 연결한다.
logging.basicConfig(level=get_settings().log_level)

app = typer.Typer(name="quant-krx", help="KRX Korean Stock Quant Trading Assistant")
console = Console()


def _read_json_input(source: str) -> dict:
    """정의 입력 규약 — JSON 파일 경로 또는 stdin('-')."""
    raw = sys.stdin.read() if source == "-" else Path(source).read_text()
    return json.loads(raw)


def _open_workspace():
    from quant_krx.storage.db import Database
    from quant_krx.workspace.service import WorkspaceService

    settings = get_settings()
    db = Database(settings.duckdb_path)
    db.connect()
    return db, WorkspaceService(db)


@app.command("run-daily")
def run_daily(
    dry_run: bool = typer.Option(
        True, "--dry-run/--no-dry-run", help="알림 발송 없이 리포트만 생성"
    ),
):
    """일일 퀀트 파이프라인 실행(활성 선언형 전략 집합 — strategy-activate로 제어)."""
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


@app.command("serve-gui")
def serve_gui_cmd(
    host: str = typer.Option(None, "--host", help="바인딩 호스트(기본: settings.gui.host)"),
    port: int = typer.Option(None, "--port", help="바인딩 포트(기본: settings.gui.port)"),
    reload: bool = typer.Option(False, "--reload", help="코드 변경 시 자동 재시작(개발용)"),
):
    """로컬 1인용 웹 GUI(API 서버)를 실행한다. localhost 전용, 인증 없음."""
    import uvicorn

    settings = get_settings()
    console.print(
        f"[green]quant-krx GUI 서버 시작: "
        f"http://{host or settings.gui.host}:{port or settings.gui.port}[/green]"
    )
    uvicorn.run(
        "quant_krx.api.app:create_app",
        factory=True,
        host=host or settings.gui.host,
        port=port or settings.gui.port,
        reload=reload,
    )


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
            except (NotImplementedError, RuntimeError) as e:
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


@app.command("strategy-backtest")
def strategy_backtest_cmd(
    strategy_id: str = typer.Argument(..., help="백테스트할 전략 id"),
    symbols: str = typer.Option(
        None, "--symbols", help="콤마 구분 종목 목록(생략 시 전략 universe.symbols 사용)"
    ),
    start: str = typer.Option(None, "--start", help="시작일 YYYY-MM-DD(기본: 5년 전)"),
    end: str = typer.Option(None, "--end", help="종료일 YYYY-MM-DD(기본: 오늘)"),
    fees: float = typer.Option(0.003, "--fees"),
    slippage: float = typer.Option(0.001, "--slippage"),
    data_source: str = typer.Option(
        "fixture", "--data-source", help="데이터 소스: fixture | fdr | pykrx"
    ),
    benchmark: str = typer.Option(
        None, "--benchmark", help="벤치마크 심볼/시장(예: KOSPI) — 상대 성과 함께 산출"
    ),
):
    """선언형 전략을 백테스트하고 최소 지표 집합을 표로 표시한다."""
    from datetime import date, datetime, timedelta

    from quant_krx.storage.db import Database
    from quant_krx.workspace.data_loading import prepare_backtest_data, resolve_backtest_symbols
    from quant_krx.workspace.errors import WorkspaceError
    from quant_krx.workspace.service import WorkspaceService

    if data_source not in ("fixture", "fdr", "pykrx"):
        console.print(f"[red]알 수 없는 --data-source '{data_source}'[/red]")
        raise typer.Exit(1)

    settings = get_settings()
    db = Database(settings.duckdb_path)
    db.connect()
    svc = WorkspaceService(db)

    defn = svc.get_strategy(strategy_id)
    if defn is None:
        from quant_krx.workspace.errors import not_found_hint

        hint = not_found_hint(d.id for d in svc.list_strategies())
        console.print(f"[red]전략 '{strategy_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        db.close()
        raise typer.Exit(1)

    validation = svc.validate_strategy(defn)
    if not svc.is_runnable(strategy_id) or not validation.ok:
        console.print(f"[red]전략 '{strategy_id}'은(는) 실행 불가(runnable/검증)[/red]")
        if validation.errors:
            console.print(f"[dim]{'; '.join(validation.errors)}[/dim]")
        db.close()
        raise typer.Exit(1)

    requested_symbols = [s.strip() for s in symbols.split(",")] if symbols else None
    sym_list = resolve_backtest_symbols(defn, requested_symbols)
    if not sym_list:
        console.print(
            "[red]대상 종목이 없습니다. --symbols 지정 또는 전략 universe.symbols 설정 필요[/red]"
        )
        db.close()
        raise typer.Exit(1)

    end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
    start_date = (
        datetime.strptime(start, "%Y-%m-%d").date()
        if start
        else end_date - timedelta(days=365 * 5)
    )

    def _warn_benchmark_failure(bm: str, exc: Exception) -> None:
        console.print(f"[yellow]벤치마크 '{bm}' 수집 실패(무시하고 계속): {exc}[/yellow]")

    data_errors: dict[str, str] = {}

    def _warn_symbol_failure(sym: str, exc: Exception) -> None:
        data_errors[sym] = str(exc)
        console.print(f"[yellow]종목 '{sym}' 데이터 조립 실패(건너뛰고 계속): {exc}[/yellow]")

    data, benchmark_df = prepare_backtest_data(
        db, defn, sym_list,
        data_source=data_source, start=start_date, end=end_date, benchmark=benchmark,
        resolve_rule=svc.get_rule, resolve_formula=svc.get_formula,
        on_benchmark_warning=_warn_benchmark_failure,
        on_symbol_error=_warn_symbol_failure,
    )
    if not data:
        console.print("[red]모든 종목의 데이터 조립이 실패했습니다[/red]")
        db.close()
        raise typer.Exit(1)

    try:
        report = svc.backtest(
            strategy_id, data=data, start=start_date, end=end_date,
            fees=fees, slippage=slippage, benchmark=benchmark_df,
        )
    except WorkspaceError as e:
        console.print(f"[red]백테스트 실패: {e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    db.close()

    if report.errors:
        console.print("[yellow]일부 종목 제외됨:[/yellow]")
        for sym, msg in report.errors.items():
            console.print(f"  [yellow]{sym}: {msg}[/yellow]")

    metrics = report.metrics
    title = f"백테스트: {strategy_id}"
    if len(sym_list) > 1:
        title += f" (대표 종목: {sym_list[0]}, 종목별 지표는 report.per_symbol 참조)"
    table = Table(title=title, show_lines=True)
    table.add_column("지표")
    table.add_column("값")
    table.add_row("총수익률", f"{metrics.total_return:.2%}")
    table.add_row("MDD", f"{metrics.mdd:.2%}")
    table.add_row("Sharpe", f"{metrics.sharpe:.3f}" if not math.isnan(metrics.sharpe) else "N/A")
    table.add_row("승률", f"{metrics.win_rate:.2%}" if not math.isnan(metrics.win_rate) else "N/A")
    table.add_row("거래 횟수", str(metrics.trade_count))
    table.add_row("총 비용", f"{metrics.fees_paid + metrics.slippage_cost:.2f}")
    if not math.isnan(metrics.benchmark_return):
        table.add_row("벤치마크 수익률", f"{metrics.benchmark_return:.2%}")
        table.add_row("초과수익률", f"{metrics.excess_return:.2%}")
    elif metrics.benchmark_note:
        table.add_row("벤치마크", metrics.benchmark_note)
    console.print(table)


@app.command("formula-create")
def formula_create_cmd(
    input_source: str = typer.Argument(..., help="JSON 파일 경로 또는 '-'(stdin)"),
):
    """Formula 정의를 생성/전체교체한다."""
    from quant_krx._jsonnorm import DefinitionError
    from quant_krx.formula.definition import Formula
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        formula = Formula.from_dict(_read_json_input(input_source))
        svc.upsert_formula(formula, now=datetime.utcnow())
    except (DefinitionError, WorkspaceError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]Formula '{formula.id}' 저장 완료[/green]")
    db.close()


@app.command("formula-show")
def formula_show_cmd(formula_id: str = typer.Argument(..., help="조회할 formula id")):
    """Formula 정의를 JSON으로 조회한다."""
    from quant_krx.workspace.errors import not_found_hint

    db, svc = _open_workspace()
    formula = svc.get_formula(formula_id)
    available = [f.id for f in svc.list_formulas()]
    db.close()
    if formula is None:
        hint = not_found_hint(available)
        console.print(f"[red]Formula '{formula_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        raise typer.Exit(1)
    console.print_json(json.dumps(formula.to_dict(), ensure_ascii=False))


@app.command("formula-delete")
def formula_delete_cmd(formula_id: str = typer.Argument(..., help="삭제할 formula id")):
    """Formula 정의를 삭제한다."""
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        svc.delete_formula(formula_id)
    except WorkspaceError as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]Formula '{formula_id}' 삭제 완료[/green]")
    db.close()


@app.command("list-formulas")
def list_formulas_cmd():
    """저장된 Formula 목록을 표시한다."""
    db, svc = _open_workspace()
    formulas = svc.list_formulas()
    db.close()
    table = Table(title="Formula 목록", show_lines=True)
    table.add_column("id", style="bold")
    table.add_column("name")
    table.add_column("output_column")
    for f in formulas:
        table.add_row(f.id, f.name, f.output_column)
    console.print(table)


@app.command("rule-create")
def rule_create_cmd(
    input_source: str = typer.Argument(..., help="JSON 파일 경로 또는 '-'(stdin)"),
):
    """Rule 정의를 생성/전체교체한다."""
    from quant_krx._jsonnorm import DefinitionError
    from quant_krx.rule.definition import Rule
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        rule = Rule.from_dict(_read_json_input(input_source))
        svc.upsert_rule(rule, now=datetime.utcnow())
    except (DefinitionError, WorkspaceError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]Rule '{rule.id}' 저장 완료[/green]")
    db.close()


@app.command("rule-show")
def rule_show_cmd(rule_id: str = typer.Argument(..., help="조회할 rule id")):
    """Rule 정의를 JSON으로 조회한다."""
    from quant_krx.workspace.errors import not_found_hint

    db, svc = _open_workspace()
    rule = svc.get_rule(rule_id)
    available = [r.id for r in svc.list_rules()]
    db.close()
    if rule is None:
        hint = not_found_hint(available)
        console.print(f"[red]Rule '{rule_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        raise typer.Exit(1)
    console.print_json(json.dumps(rule.to_dict(), ensure_ascii=False))


@app.command("rule-delete")
def rule_delete_cmd(rule_id: str = typer.Argument(..., help="삭제할 rule id")):
    """Rule 정의를 삭제한다."""
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        svc.delete_rule(rule_id)
    except WorkspaceError as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]Rule '{rule_id}' 삭제 완료[/green]")
    db.close()


@app.command("list-rules")
def list_rules_cmd():
    """저장된 Rule 목록을 표시한다."""
    db, svc = _open_workspace()
    rules = svc.list_rules()
    db.close()
    table = Table(title="Rule 목록", show_lines=True)
    table.add_column("id", style="bold")
    table.add_column("name")
    for r in rules:
        table.add_row(r.id, r.name)
    console.print(table)


@app.command("strategy-create")
def strategy_create_cmd(
    new_id: str = typer.Argument(..., help="생성할 전략 id"),
    input_source: str = typer.Argument(
        None, help="JSON 파일 경로 또는 '-'(stdin) — --template 미지정 시 필수"
    ),
    template: str = typer.Option(None, "--template", help="Template id로부터 복제 생성"),
):
    """전략을 생성한다(신규 JSON 정의 또는 Template 복제)."""
    from quant_krx._jsonnorm import DefinitionError
    from quant_krx.strategy.definition import StrategyDefinition
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        if template:
            defn = svc.create_from_template(template, new_id, now=datetime.utcnow())
        else:
            if not input_source:
                raise WorkspaceError("--template 미지정 시 JSON 입력이 필요합니다")
            defn = StrategyDefinition.from_dict(_read_json_input(input_source))
            if defn.id != new_id:
                defn = dataclasses.replace(defn, id=new_id)
            svc.upsert_strategy(defn, now=datetime.utcnow())
    except (DefinitionError, WorkspaceError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]전략 '{defn.id}' 생성 완료[/green]")
    db.close()


@app.command("strategy-show")
def strategy_show_cmd(strategy_id: str = typer.Argument(..., help="조회할 전략 id")):
    """전략 정의를 JSON으로 조회한다."""
    from quant_krx.workspace.errors import not_found_hint

    db, svc = _open_workspace()
    defn = svc.get_strategy(strategy_id)
    available = [d.id for d in svc.list_strategies()]
    db.close()
    if defn is None:
        hint = not_found_hint(available)
        console.print(f"[red]전략 '{strategy_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        raise typer.Exit(1)
    console.print_json(json.dumps(defn.to_dict(), ensure_ascii=False))


@app.command("strategy-edit")
def strategy_edit_cmd(
    strategy_id: str = typer.Argument(..., help="수정할 전략 id"),
    input_source: str = typer.Argument(..., help="JSON 파일 경로 또는 '-'(stdin) — 전체 교체"),
):
    """전략 정의를 전체 JSON 교체로 수정한다(부분 필드 패치 없음)."""
    from quant_krx._jsonnorm import DefinitionError
    from quant_krx.strategy.definition import StrategyDefinition
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        defn = StrategyDefinition.from_dict(_read_json_input(input_source))
        if defn.id != strategy_id:
            db.close()
            console.print(f"[red]JSON id '{defn.id}'가 인자 id '{strategy_id}'와 다릅니다[/red]")
            raise typer.Exit(1)
        svc.upsert_strategy(defn, now=datetime.utcnow())
    except (DefinitionError, WorkspaceError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]전략 '{strategy_id}' 수정 완료[/green]")
    db.close()


@app.command("strategy-delete")
def strategy_delete_cmd(strategy_id: str = typer.Argument(..., help="삭제할 전략 id")):
    """전략 정의를 삭제한다."""
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        svc.delete_strategy(strategy_id)
    except WorkspaceError as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]전략 '{strategy_id}' 삭제 완료[/green]")
    db.close()


@app.command("strategy-list")
def strategy_list_cmd():
    """저장된 전략 목록과 활성 상태를 표시한다."""
    db, svc = _open_workspace()
    strategies = svc.list_strategies()
    active = set(svc.list_active())
    db.close()
    table = Table(title="전략 목록", show_lines=True)
    table.add_column("id", style="bold")
    table.add_column("name")
    table.add_column("활성")
    table.add_column("runnable")
    for defn in strategies:
        status = "[green]ON[/green]" if defn.id in active else "[dim]OFF[/dim]"
        runnable = "Y" if defn.rule is not None else "N"
        table.add_row(defn.id, defn.name, status, runnable)
    console.print(table)


@app.command("strategy-validate")
def strategy_validate_cmd(strategy_id: str = typer.Argument(..., help="검증할 전략 id")):
    """전략의 전이 검증을 실행 없이 수행한다."""
    from quant_krx.workspace.errors import not_found_hint

    db, svc = _open_workspace()
    defn = svc.get_strategy(strategy_id)
    if defn is None:
        available = [d.id for d in svc.list_strategies()]
        db.close()
        hint = not_found_hint(available)
        console.print(f"[red]전략 '{strategy_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        raise typer.Exit(1)
    result = svc.validate_strategy(defn)
    db.close()
    if result.ok:
        console.print(f"[green]전략 '{strategy_id}' 검증 통과[/green]")
        return
    console.print(f"[red]전략 '{strategy_id}' 검증 실패:[/red]")
    for err in result.errors:
        console.print(f"  - {err}")
    raise typer.Exit(1)


@app.command("strategy-activate")
def strategy_activate_cmd(strategy_id: str = typer.Argument(..., help="활성화할 전략 id")):
    """전략을 활성화한다(runnable + 검증 통과 전제, FR-04)."""
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        svc.activate(strategy_id, now=datetime.utcnow())
    except WorkspaceError as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]전략 '{strategy_id}' 활성화 완료[/green]")
    db.close()


@app.command("strategy-deactivate")
def strategy_deactivate_cmd(strategy_id: str = typer.Argument(..., help="비활성화할 전략 id")):
    """전략을 비활성화한다."""
    db, svc = _open_workspace()
    svc.deactivate(strategy_id, now=datetime.utcnow())
    db.close()
    console.print(f"[green]전략 '{strategy_id}' 비활성화 완료[/green]")


@app.command("strategy-template-list")
def strategy_template_list_cmd():
    """Built-in/사용자 Template를 출처 구분과 함께 통합 열거한다."""
    db, svc = _open_workspace()
    infos = svc.list_templates()
    db.close()
    table = Table(title="Template 목록", show_lines=True)
    table.add_column("template_id", style="bold")
    table.add_column("출처")
    table.add_column("name")
    for info in infos:
        table.add_row(info.template_id, info.origin, info.name)
    console.print(table)


@app.command("strategy-export")
def strategy_export_cmd(
    strategy_id: str = typer.Argument(..., help="내보낼 전략 id"),
    output: str = typer.Option(None, "--output", "-o", help="출력 파일 경로(생략 시 stdout)"),
):
    """전략 + 전이 참조 Rule·Formula를 결정론적 JSON 번들로 내보낸다."""
    from quant_krx._jsonnorm import canonical_json
    from quant_krx.workspace.errors import WorkspaceError

    db, svc = _open_workspace()
    try:
        bundle = svc.export_strategy(strategy_id)
    except WorkspaceError as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    db.close()

    body = canonical_json(bundle.to_dict())
    if output:
        Path(output).write_text(body)
        console.print(f"[green]전략 '{strategy_id}' 번들을 '{output}'에 저장했습니다[/green]")
    else:
        console.print_json(body)


@app.command("strategy-import")
def strategy_import_cmd(
    input_source: str = typer.Argument(..., help="JSON 파일 경로 또는 '-'(stdin)"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="id 충돌 시 대체(활성 참조 보호가 우선)"
    ),
):
    """전략 JSON 번들을 위상 순서(Formula→Rule→Strategy)로 가져온다."""
    from quant_krx._jsonnorm import DefinitionError
    from quant_krx.workspace.errors import WorkspaceError
    from quant_krx.workspace.templates import StrategyBundle

    db, svc = _open_workspace()
    try:
        bundle = StrategyBundle.from_dict(_read_json_input(input_source))
        svc.import_strategy(
            bundle, now=datetime.utcnow(), on_conflict="overwrite" if overwrite else "reject"
        )
    except (DefinitionError, WorkspaceError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]전략 '{bundle.strategy.id}' 가져오기 완료[/green]")
    db.close()


def _open_screening(data_source: str = "fixture"):
    from quant_krx.screening.service import ScreeningService
    from quant_krx.storage.db import Database
    from quant_krx.workspace.data_loading import _ohlcv_provider_for

    settings = get_settings()
    db = Database(settings.duckdb_path)
    db.connect()
    provider = _ohlcv_provider_for(data_source)
    return db, ScreeningService(db, provider)


@app.command("screen-create")
def screen_create_cmd(
    input_source: str = typer.Argument(..., help="JSON 파일 경로 또는 '-'(stdin)"),
):
    """스크리닝 조건을 생성/전체교체한다."""
    from quant_krx.screening.definition import ScreeningCondition
    from quant_krx.screening.errors import ScreeningError

    db, svc = _open_screening()
    try:
        cond = ScreeningCondition.from_dict(_read_json_input(input_source))
        svc.upsert_condition(cond, now=datetime.utcnow())
    except (ScreeningError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]스크리닝 조건 '{cond.id}' 저장 완료[/green]")
    db.close()


@app.command("screen-show")
def screen_show_cmd(condition_id: str = typer.Argument(..., help="조회할 스크리닝 조건 id")):
    """스크리닝 조건을 rich 표/패널로 조회한다."""
    from quant_krx.workspace.errors import not_found_hint

    db, svc = _open_screening()
    cond = svc.get_condition(condition_id)
    available = [c.id for c in svc.list_conditions()]
    db.close()
    if cond is None:
        hint = not_found_hint(available)
        console.print(f"[red]스크리닝 조건 '{condition_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"스크리닝 조건: {cond.id}", show_lines=True)
    table.add_column("필드", style="bold")
    table.add_column("값")
    table.add_row("name", cond.name)
    table.add_row("version", cond.version)
    table.add_row("market", cond.universe.market)
    table.add_row("exclusion_filters", ", ".join(sorted(cond.universe.exclusion_filters)) or "-")
    table.add_row("schema_version", str(cond.schema_version))
    console.print(table)
    console.print(
        Panel(
            json.dumps(cond.root.to_dict(), ensure_ascii=False, indent=2),
            title="조건 트리(root)",
        )
    )


@app.command("screen-edit")
def screen_edit_cmd(
    condition_id: str = typer.Argument(..., help="수정할 스크리닝 조건 id"),
    input_source: str = typer.Argument(..., help="JSON 파일 경로 또는 '-'(stdin) — 전체 교체"),
):
    """스크리닝 조건을 전체 JSON 교체로 수정한다(부분 필드 패치 없음)."""
    from quant_krx.screening.definition import ScreeningCondition
    from quant_krx.screening.errors import ScreeningError

    db, svc = _open_screening()
    try:
        cond = ScreeningCondition.from_dict(_read_json_input(input_source))
        if cond.id != condition_id:
            db.close()
            console.print(f"[red]JSON id '{cond.id}'가 인자 id '{condition_id}'와 다릅니다[/red]")
            raise typer.Exit(1)
        svc.upsert_condition(cond, now=datetime.utcnow())
    except (ScreeningError, OSError, json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    console.print(f"[green]스크리닝 조건 '{condition_id}' 수정 완료[/green]")
    db.close()


@app.command("screen-delete")
def screen_delete_cmd(condition_id: str = typer.Argument(..., help="삭제할 스크리닝 조건 id")):
    """스크리닝 조건을 삭제한다."""
    db, svc = _open_screening()
    svc.delete_condition(condition_id)
    db.close()
    console.print(f"[green]스크리닝 조건 '{condition_id}' 삭제 완료[/green]")


@app.command("screen-list")
def screen_list_cmd():
    """저장된 스크리닝 조건 목록을 표시한다."""
    db, svc = _open_screening()
    conditions = svc.list_conditions()
    db.close()
    table = Table(title="스크리닝 조건 목록", show_lines=True)
    table.add_column("id", style="bold")
    table.add_column("name")
    table.add_column("version")
    for cond in conditions:
        table.add_row(cond.id, cond.name, cond.version)
    console.print(table)


@app.command("screen-validate")
def screen_validate_cmd(condition_id: str = typer.Argument(..., help="검증할 스크리닝 조건 id")):
    """스크리닝 조건의 참조 무결성을 실행 없이 검증한다."""
    from quant_krx.workspace.errors import not_found_hint

    db, svc = _open_screening()
    cond = svc.get_condition(condition_id)
    if cond is None:
        available = [c.id for c in svc.list_conditions()]
        db.close()
        hint = not_found_hint(available)
        console.print(f"[red]스크리닝 조건 '{condition_id}'을(를) 찾을 수 없습니다.{hint}[/red]")
        raise typer.Exit(1)
    result = svc.validate_condition(cond)
    db.close()
    if result.ok:
        console.print(f"[green]스크리닝 조건 '{condition_id}' 검증 통과[/green]")
        return
    console.print(f"[red]스크리닝 조건 '{condition_id}' 검증 실패:[/red]")
    for err in result.errors:
        console.print(f"  - {err}")
    raise typer.Exit(1)


@app.command("screen-run")
def screen_run_cmd(
    condition_id: str = typer.Argument(..., help="실행할 스크리닝 조건 id"),
    as_of: str = typer.Option(None, "--as-of", help="기준일(YYYY-MM-DD, 생략 시 오늘)"),
    data_source: str = typer.Option(
        "fixture", "--data-source", help="데이터 소스: fixture | fdr | pykrx"
    ),
):
    """스크리닝 조건을 실행해 통과 종목(코드+이름)을 rich 표로 출력한다(저장 없음)."""
    from datetime import date

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

    from quant_krx.screening.errors import ScreeningError

    if data_source not in ("fixture", "fdr", "pykrx"):
        console.print(f"[red]알 수 없는 --data-source '{data_source}'[/red]")
        raise typer.Exit(1)

    as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else date.today()

    db, svc = _open_screening(data_source)
    try:
        universe_size = svc.count_universe(condition_id)
        console.print(f"대상 종목: [bold]{universe_size}[/bold]개")

        with Progress(
            TextColumn("종목 OHLCV 확보"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("screening", total=universe_size)

            def _on_progress(processed: int, total: int) -> None:
                progress.update(task, completed=processed, total=total)

            passed = svc.run(condition_id, as_of=as_of_date, on_progress=_on_progress)
    except ScreeningError as e:
        console.print(f"[red]{e}[/red]")
        db.close()
        raise typer.Exit(1) from e
    db.close()

    table = Table(title=f"스크리닝 결과: {condition_id} (as_of={as_of_date})", show_lines=True)
    table.add_column("종목코드", style="bold")
    table.add_column("종목명")
    table.add_column("시장")
    for symbol, name, market in passed:
        table.add_row(symbol, name, market or "-")
    console.print(table)
    console.print(f"[green]통과 종목 {len(passed)}건[/green]")


if __name__ == "__main__":
    app()
