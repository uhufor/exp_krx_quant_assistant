# PRD: Korean Stock Quant Assistant v1

## Requirements Summary

Build a personal, local Mac mini based Korean stock quant assistant. v1 analyzes a user-managed Korean stock watchlist once per day, runs deterministic VectorBT-centered quant strategies, evaluates signals with a balanced return/risk profile, and sends one daily report. The report must separate:

- Report A: quant-only interpretation from structured quant outputs.
- Report B: context-assisted LLM interpretation from the same quant outputs plus allowed contextual data.

The user makes the final investment decision. v1 must not execute orders, send intraday realtime alerts, or crawl raw news/disclosure text.

Primary source spec: `.omx/specs/deep-interview-korean-stock-quant-assistant.md`

## RALPLAN-DR Summary

### Principles

- Keep quant signal generation deterministic, auditable, and reproducible.
- Isolate unstable external data providers behind adapters.
- Make v1 narrow enough to run unattended before expanding to themes and full-market screening.
- Separate LLM explanation from quant truth so LLM usefulness can be measured.
- Preserve a future path to brokerage/paper-trading without coupling v1 to order execution.

### Decision Drivers

- Data reliability for Korean equities matters more than broad initial coverage.
- Backtest validity must include drawdown, benchmark comparison, fees/slippage, and recent-period robustness, not only cumulative return.
- Mac mini daily-batch operation should be simple to install, observe, and recover.

### Viable Options

#### Option 1: Local Modular Batch System (Recommended)

Approach: Python app with provider adapters, local storage, VectorBT strategy runner, signal/report pipeline, scheduler, and notification module.

Pros:
- Matches Mac mini requirement and daily report cadence.
- Keeps components replaceable as data sources change.
- Enables testable quant and LLM A/B outputs.
- Avoids early broker/API coupling.

Cons:
- Requires up-front interfaces and local operational discipline.
- Provider quirks still need normalization and caching.

#### Option 2: Notebook-First Research Prototype

Approach: Start with Jupyter notebooks for data fetching, VectorBT experiments, and manual report generation.

Pros:
- Fastest for strategy exploration.
- Useful for learning VectorBT and data-source behavior.

Cons:
- Poor unattended scheduling and alerting fit.
- Harder to test, version, and run reliably every day.
- LLM report comparison can become informal and non-reproducible.

#### Option 3: Broker/API-Centered System First

Approach: Use Korea Investment Open API early as the main data and future order integration layer.

Pros:
- Best long-term bridge to paper/live trading.
- Authenticated API may reduce dependence on scraping sources.

Cons:
- Adds credentials, rate limits, account coupling, and operational complexity too early.
- Conflicts with v1 non-goal of no order execution.
- Slower path to quant/report validation.

## ADR

### Decision

Choose Option 1: a local modular daily-batch Python system, with data-provider adapters and no v1 order execution.

### Drivers

- User explicitly wants Mac mini runtime, daily reporting, adapter-based data acquisition, and future iteration across v1/v2/v3.
- The system must compare quant-only and LLM-assisted reports from the same quant signal.
- v1 should validate data quality and signal/report usefulness before adding broad screening or automation.

### Alternatives Considered

- Notebook-first research prototype.
- Broker/API-centered architecture first.
- Fully cloud-hosted scheduler and report service.

### Why Chosen

Option 1 best balances repeatable daily operation, testability, and future extensibility. It supports the user’s staged roadmap while avoiding early complexity from full-market screening, live trading, and realtime infrastructure.

### Consequences

- The initial implementation must define clean interfaces before adding many strategies.
- Data normalization and run logging become first-class v1 work.
- Some research speed is traded for a reliable daily loop.

### Follow-ups

- Validate Korean data source behavior with a small watchlist before broadening coverage.
- Add theme and rebalancing reports in v2 after v1 daily reports are stable.
- Consider Korea Investment Open API only after dry-run/report quality is proven.

## Architecture Plan

### Modules

- `config`: watchlist, strategy profiles, evaluation profiles, provider settings, scheduler/report settings.
- `data`: adapter interfaces and implementations for Korean equity OHLCV, ticker metadata, and benchmark index data.
- `storage`: local persistence for raw pulls, normalized bars, signal runs, reports, and diagnostics.
- `quant`: VectorBT strategy runners and portfolio/stat extraction.
- `signals`: deterministic conversion from strategy/backtest outputs to buy/sell/hold/watch/no-signal records.
- `reports`: deterministic quant-only report rendering and context-assisted LLM report generation.
- `llm`: provider abstraction for external LLM APIs.
- `notify`: daily notification dispatch.
- `jobs`: daily orchestration entrypoint.
- `tests`: unit, integration, and smoke coverage.

### Data Source Strategy

Start with two provider adapters behind one interface:

- FinanceDataReader adapter for convenient KRX/KOSPI/KOSDAQ listings and price reads.
- PyKrx adapter for Korean-market OHLCV and richer KRX/Naver fields where needed.

Treat Korea Investment Open API as a later authenticated provider path, not v1 default.

Provider interface should expose:

- `list_symbols(market)`
- `fetch_ohlcv(symbol, start, end, interval="1d")`
- `fetch_benchmark(symbol_or_market, start, end)`
- `fetch_metadata(symbols)`
- source name, fetch timestamp, and adjustment assumptions

### Storage Strategy

Use local SQLite or DuckDB in v1, plus filesystem report artifacts.

Minimum tables/artifacts:

- `symbols`
- `ohlcv_daily`
- `data_fetch_runs`
- `strategy_runs`
- `signals`
- `reports`
- `notification_outbox`
- `run_events`

`notification_outbox` must enforce a storage-level uniqueness constraint on `run_id + channel + content_hash`, not only an application-level duplicate check.

### Quant And Signal Strategy

Implement one or two baseline strategies first:

- Moving-average crossover trend baseline.
- RSI or volatility breakout baseline.

Do not optimize many parameters in v1. Parameter search should be explicit and logged to reduce overfitting.

Balanced evaluation profile:

- Benchmark-relative total return.
- Maximum drawdown guardrail.
- Sharpe or Sortino.
- Trade count/frequency.
- Fees and slippage assumptions.
- Recent-period robustness, for example recent 6-12 months.

Signal object should include:

- symbol, date, signal type, strategy name, score/confidence, current position recommendation, evidence metrics, risk flags, and source run id.

### Report Strategy

Report A must be a pure deterministic renderer from stored structured quant outputs. It must not call any LLM provider and must not consume raw text context.

Report B may use structured quant outputs plus allowed contextual fields through the LLM provider. Since v1 excludes raw news/disclosure crawling, allowed context should initially be:

- manually configured theme labels,
- ticker metadata,
- recent price/volume regime summaries generated by the system,

Defer user-curated text snippets to v2 unless the user explicitly changes the v1 scope. This keeps the quant-only versus context-assisted comparison cleaner.

LLM prompts should require:

- explicit separation of fact, inference, and recommendation,
- no hidden signal changes without referencing quant inputs,
- visible risk flags,
- comparison against Report A when relevant.

### Scheduling And Notification

Use Mac mini local scheduling:

- v1 default: run after Korean market close using completed daily bars, or before next market open.
- Candidate mechanisms: `launchd` for macOS-native scheduling, or a Python scheduler wrapped by `launchd`.

Notification channel should be abstracted:

- v1 default can be email, Telegram, Slack/Discord webhook, or local report file plus notification.
- Choose the simplest channel available during implementation after credential availability is known.
- Use a durable notification outbox keyed by `run_id + channel + content_hash` so retries and `launchd` restarts do not send duplicate reports.

## Implementation Steps

1. Scaffold Python project and configuration.
   - Add package layout, dependency management, typed configuration, sample watchlist, and local env template.
   - Acceptance: the app can load config and validate a watchlist without network calls.

2. Implement data provider interface and first adapters.
   - Add FinanceDataReader and PyKrx adapters behind the same interface.
   - Add caching and source metadata.
   - Acceptance: a small watchlist fetch produces normalized daily OHLCV with provider/source timestamps.

3. Add local storage and data validation.
   - Persist symbols, OHLCV, fetch runs, and validation diagnostics.
   - Validate missing bars, duplicate dates, nonpositive prices, and stale data.
   - Acceptance: bad or stale data is flagged before quant runs.

4. Implement VectorBT baseline strategy runner.
   - Add at least one trend baseline and one alternative baseline if feasible.
   - Extract balanced metrics.
   - Acceptance: a deterministic run produces stats and trade records for the sample watchlist.

5. Implement signal engine.
   - Convert strategy metrics/current positions into buy/sell/hold/watch/no-signal.
   - Acceptance: each signal has evidence metrics, risk flags, and run id.

6. Implement report generation.
   - Generate Report A as a deterministic renderer without any LLM call.
   - Generate Report B using the same signal object plus allowed context.
   - Acceptance: both reports clearly reference the same signal id and differ only in allowed interpretation context.

7. Implement LLM provider abstraction.
   - Support external API integration through a provider interface.
   - Keep prompts and model settings configurable.
   - Acceptance: report generation can run in mock mode and real-provider mode.

8. Implement daily job and notification adapter.
   - One command runs fetch -> validate -> quant -> signal -> reports -> notify.
   - Add notification outbox with `pending`, `sent`, and `failed` states and content-hash based duplicate prevention.
   - Acceptance: local dry run writes reports and logs without sending notifications; live run sends one report; duplicate retries do not resend the same report.

9. Add operational packaging for Mac mini.
   - Add `launchd` plist template or setup instructions.
   - Add log/report retention settings.
   - Acceptance: job can be scheduled and observed through logs.

10. Add documentation and roadmap notes.
   - README with setup, configuration, daily operation, and v2/v3 roadmap.
   - Acceptance: a new local clone can be configured for dry-run operation from docs.

## Acceptance Criteria

- Watchlist symbols can be changed through config without code edits.
- The data layer can switch between at least two adapters through config or dependency injection.
- Daily OHLCV data is normalized and validated before strategy execution.
- At least one VectorBT-backed strategy run is reproducible for the same input data and parameters.
- Backtest output includes total return, benchmark-relative return, MDD, Sharpe or Sortino, trade count, fee/slippage assumptions, and recent-period performance.
- Signals are deterministic and store evidence metrics.
- Report A and Report B are generated from the same signal id.
- Report A is deterministic and does not use LLM calls or raw news/disclosure/context sources.
- Report B clearly labels any non-quant context and does not overwrite the deterministic signal without explanation.
- A dry-run daily job completes without external notification side effects.
- A live daily job sends exactly one report per run.
- Re-running the same completed daily job does not duplicate notifications.
- A failed notification can be retried from the durable outbox.
- All network-dependent tests have mock or fixture alternatives.
- No order API or brokerage execution path exists in v1.

## Test Specification

### Unit Tests

- Config validation for watchlist, provider, strategy, report, and notification settings.
- Data normalization for OHLCV schema, timezone/date handling, and source metadata.
- Data validation for missing dates, duplicate bars, stale bars, and invalid prices.
- Signal classification from sample strategy metrics.
- Report input construction and Report A/B separation.
- LLM provider mock responses and failure handling.

### Integration Tests

- Adapter contract tests with recorded fixtures or mocked provider responses.
- Storage roundtrip for OHLCV, strategy runs, signals, and reports.
- VectorBT strategy run on deterministic fixture data.
- Daily job dry-run end-to-end using local fixtures and mock LLM/notification.
- Duplicate daily job execution with the same `run_id` and report content.
- Notification retry after a simulated delivery failure.
- Scheduler timezone behavior for Asia/Seoul market-close and next-market-open modes.

### Smoke Tests

- `app validate-config`
- `app fetch --dry-run`
- `app run-daily --dry-run`
- `app render-report --latest`

### Observability Checks

- Each run writes a run id, start/end time, status, provider source, symbol count, warning count, generated report paths, and notification status.
- Failures are visible in logs and do not silently send partial reports unless explicitly configured.

## Risks And Mitigations

- Data source instability: use adapter isolation, caching, fixtures, and fallback provider support.
- Data mismatch across providers: store source and adjustment assumptions; compare sample outputs before trusting results.
- Backtest overfitting: start with simple baselines and log all parameters; defer broad optimization.
- LLM overconfidence: keep Report A/B separated and require risk labels.
- Mac mini operational drift: provide dry-run command, logs, and scheduler setup docs.
- Duplicate notifications after restarts: use durable outbox, content hashes, and exactly-once send tests.
- Notification credential friction: abstract channel and support file-only dry-run.

## Available Agent Types Roster

- `explore`: repo and file/symbol discovery.
- `researcher`: official docs and external API behavior.
- `dependency-expert`: package/API selection and upgrade/replacement decisions.
- `planner`: task sequencing and decomposition.
- `architect`: architecture, interfaces, and long-horizon tradeoffs.
- `critic`: plan/design challenge and quality gate.
- `executor`: implementation.
- `test-engineer`: test strategy and fixture design.
- `verifier`: completion evidence and validation.
- `code-reviewer`: final review.
- `writer`: user docs and setup guide.

## Follow-up Staffing Guidance

### Default `$ultragoal`

Use `$ultragoal` to convert this plan into durable implementation goals. Suggested sequential goals:

- Project scaffold and config.
- Data provider adapters and storage.
- Quant and signal engine.
- Report/LLM/notification.
- Scheduler/docs/verification.

### Team + Ultragoal

Use `$team` under Ultragoal if parallel delivery is desired:

- Lane 1 `executor`: data adapters and storage.
- Lane 2 `executor`: VectorBT quant and signal engine.
- Lane 3 `executor`: LLM reports and notifications.
- Lane 4 `test-engineer`: fixtures, dry-run, and integration tests.
- Lane 5 `writer`: README and Mac mini operation guide.

Suggested reasoning:

- Data/quant/report executors: medium.
- Test engineer: medium.
- Architect/verifier gates: high.

### Explicit Ralph Fallback

Use `$ralph` only if the user explicitly wants a single persistent owner to implement and verify one narrowed slice, such as v1 data adapter plus dry-run job.

## Launch Hints

Default durable path:

```bash
$ultragoal create-goals --brief-file .omx/plans/prd-korean-stock-quant-assistant-v1.md
$ultragoal complete-goals
```

Parallel delivery path:

```bash
$team .omx/plans/prd-korean-stock-quant-assistant-v1.md
```

## Team Verification Path

Before Team shutdown, require:

- All lane outputs merged without source conflicts.
- Dry-run daily job proof.
- Fixture-backed data/quant/report tests.
- Evidence that Report A and Report B share the same signal id.
- Explicit proof that no order execution path was added.

Ultragoal should checkpoint:

- implemented files,
- test outputs,
- dry-run report artifact path,
- remaining risks and deferred v2/v3 items.

## Goal-Mode Follow-up Suggestions

- `$ultragoal`: default next step for durable implementation tracking.
- `$team`: use with Ultragoal if parallel lanes are desired.
- `$performance-goal`: not the first follow-up; use later when optimizing backtest/runtime performance or measurable signal evaluation speed.
- `$autoresearch-goal`: not the first follow-up; use only if the next deliverable becomes a research report comparing data providers or strategy theory.
- `$ralph`: explicit fallback only for a narrowed single-owner implementation loop.

## Applied Consensus Changelog

- Initial draft created from deep-interview spec.
- Applied Architect iteration 1 feedback:
  - Report A is now a deterministic non-LLM renderer only.
  - Added durable notification outbox keyed by `run_id + channel + content_hash`.
  - Made the outbox uniqueness requirement storage-level.
  - Limited v1 Report B context to metadata/theme labels and system-generated regime summaries.
  - Added retry, duplicate-run, and scheduler/timezone requirements.
  - Strengthened acceptance criteria around exactly-once delivery.
- Architect iteration 2 verdict: APPROVE.
- Critic verdict: APPROVE.
- Durable consensus handoff: `.omx/plans/ralplan-consensus-korean-stock-quant-assistant-v1.md`.
