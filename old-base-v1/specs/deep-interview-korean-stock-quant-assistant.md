# Execution Spec: Korean Stock Quant Assistant

## Metadata

- Source workflow: deep-interview
- Profile: standard
- Context type: greenfield
- Final ambiguity: 17.8%
- Threshold: 20%
- Context snapshot: `.omx/context/korean-stock-quant-assistant-20260627T172044Z.md`
- Transcript: `.omx/interviews/korean-stock-quant-assistant-20260627T172044Z.md`

## Intent

Build a personal Korean stock decision-support assistant that turns quantitative signals into daily actionable reports. The first product goal is not automatic trading. It is a strong recommendation system where the user makes the final decision. If measured signal quality is good enough, the architecture should allow later expansion toward automated trading.

## Desired Outcome

Every day, the system runs on a local Mac mini, updates Korean stock data, runs quant strategies/backtests through a VectorBT-centered engine, evaluates signals with a balanced risk/return profile, and sends one daily report. The report should include both:

- Quant-only interpretation: deterministic explanation of the quant signal.
- Quant plus LLM context interpretation: separate assisted report that uses the same quant signal plus allowed contextual inputs.

## In Scope

- Local Mac mini runtime for quant engine, scheduling, data refresh, report generation, and notification dispatch.
- Python-based quant/backtesting engine using VectorBT.
- Korean stock data adapter layer so sources can be replaced.
- v1 universe: user-defined watchlist of selected Korean stocks.
- v2 direction: user-specified theme and theme-member reports.
- v3+ direction: full KOSPI/KOSDAQ screening after data-quality handling is mature.
- Balanced signal evaluation profile as default.
- Configurable strategy/evaluation profiles so aggressive, balanced, conservative, and research modes can be tested later.
- Daily one-time report generation.
- External LLM API integration, with provider abstraction for Codex/OpenAI-compatible APIs and Claude/Anthropic-style APIs where feasible.
- Rebalancing optimization as recommendation/report only.
- Theme discovery as report output, not automatic trade execution.

## Out Of Scope / Non-goals

- v1 automatic order execution.
- v1 real-time intraday alerts.
- v1 raw news/disclosure crawling.
- Commercial/public service requirements.
- Legal/compliance productization.
- Fully autonomous portfolio rebalancing.
- Treating LLM output as the sole source of buy/sell truth.

## Decision Boundaries

The planner/implementer may choose practical defaults for:

- Initial data source adapters.
- Local scheduler mechanism.
- Report storage format.
- Notification channel for v1.
- Project structure and testing approach.
- Initial strategy templates.

The planner/implementer must preserve these boundaries:

- The user makes the final investment decision.
- No v1 order API integration.
- Quant signal generation remains deterministic and auditable.
- LLM output must be separated into quant-only and context-assisted reports.
- Data ingestion must be replaceable through adapters.
- Future automation should be possible without forcing v1 into brokerage coupling.

## Recommended Architecture

Use a modular local-batch architecture:

1. `data adapters`
   - Normalize OHLCV, ticker metadata, market index data, and later theme/context data.
   - Candidate adapters:
     - FinanceDataReader for convenient KRX/KOSPI/KOSDAQ listings and historical price reads.
     - PyKrx for KRX/Naver market data and OHLCV where richer Korean-market fields are needed.
     - Korea Investment Open API as later-stage adapter for authenticated market/brokerage workflows.

2. `data store`
   - Start with local files or SQLite/DuckDB.
   - Store raw pulls, normalized OHLCV, adjusted prices, ticker metadata, and run logs.
   - Track source, fetch timestamp, and adjustment assumptions.

3. `quant engine`
   - VectorBT-centered strategy runner.
   - Strategy templates should be parameterized.
   - Evaluation should include benchmark-relative return, MDD, Sharpe/Sortino, trade count/frequency, fees/slippage, and recent-period robustness.

4. `signal engine`
   - Converts strategy outputs into `buy`, `sell`, `hold/watch`, or `no signal`.
   - Records the reason, strategy source, confidence/score, risk flags, and benchmark comparison.

5. `LLM report engine`
   - Report A: quant-only explanation based strictly on structured quant outputs.
   - Report B: context-assisted interpretation using the same quant output plus allowed context sources.
   - The two reports must be clearly separated so their usefulness can be compared.

6. `scheduler`
   - Runs once daily on the Mac mini.
   - Default timing should be after market close, or before the next market open using the latest available completed daily bar.

7. `notification`
   - Sends one daily text report.
   - Channel can be selected in planning; practical candidates include email, Slack/Discord webhook, Telegram, Kakao-related webhook if feasible, or local file plus push mechanism.

## Success Criteria

v1 is successful when:

- A configured watchlist can be fetched, normalized, cached, and validated.
- At least one baseline quant strategy can run reproducibly through VectorBT.
- Backtest reports include total return, benchmark comparison, MDD, Sharpe/Sortino or equivalent, trade count, fees/slippage assumptions, and recent-period performance.
- The default signal quality profile is balanced: benchmark-relative return plus drawdown guardrail plus transaction-cost awareness.
- A daily report contains both quant-only and context-assisted interpretations from the same signal input.
- The scheduler can run unattended on the Mac mini.
- Reports are stored historically so later signal quality can be reviewed.
- Configuration allows adding/removing watched stocks without code changes.

## Suggested Roadmap

### v1: Watchlist Daily Quant Assistant

- Mac mini local batch runtime.
- Watchlist config.
- FinanceDataReader and/or PyKrx adapter behind a common interface.
- VectorBT baseline strategies.
- Balanced evaluation profile.
- Daily report generation and notification.
- A/B report split for LLM role comparison.

### v2: Theme And Rebalancing Reports

- Theme configuration.
- Theme member mapping, initially manual or semi-manual.
- Rebalancing recommendation report, not automatic execution.
- Compare quant-only vs context-assisted report usefulness.

### v3: Market Screening

- Broader KOSPI/KOSDAQ screening.
- Survivorship-bias and delisting/admin stock handling.
- Data-quality scoring.
- Candidate ranking and filtering.

### v4: Broker/API Preparation

- Optional Korea Investment Open API adapter.
- Paper-trading or dry-run order simulation.
- Explicit user approval gates before any order execution work.

## Key Risks

- Data quality and adjustment differences can dominate signal quality.
- Scraping-based sources can break or rate-limit; use caching and adapter isolation.
- Backtests can overfit if many strategies/parameters are tested without walk-forward or out-of-sample discipline.
- LLM context-assisted reports can sound confident even when the quant signal is weak; keep structured quant facts visible.
- Full-market screening too early can bury the project under data hygiene issues.

## Planning Handoff

Recommended next workflow: `$ralplan`.

Reason: requirements are clear enough to stop interviewing, but architecture, data-source validation, test shape, and roadmap decomposition still need a careful plan before implementation.

After `$ralplan`, use `$ultragoal` for durable implementation tracking. Use `$team` only if implementation is split into parallel lanes such as data adapters, quant engine, LLM reporting, scheduler/notifications, and QA.

