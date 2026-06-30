# Test Spec: Korean Stock Quant Assistant v1

## Scope

This test spec validates the v1 daily-batch Korean stock quant assistant described in `.omx/plans/prd-korean-stock-quant-assistant-v1.md`.

## Testable Claims

- Configuration controls the watchlist, providers, strategy profiles, report modes, and notification mode.
- Data adapters produce normalized daily OHLCV and metadata with source attribution.
- Invalid or stale data is detected before quant execution.
- VectorBT strategy runs are deterministic on fixture data.
- Signal generation is deterministic and auditable.
- Report A and Report B use the same signal id while preserving context boundaries.
- Daily dry-run executes without external side effects.
- Notification delivery is idempotent across duplicate runs and retry after failure.
- Scheduler behavior handles Asia/Seoul daily timing deterministically.
- v1 contains no order execution path.

## Required Fixtures

- Small watchlist fixture with 3-5 Korean symbols.
- Deterministic OHLCV fixture covering trend, flat, and volatile regimes.
- Benchmark fixture.
- Provider response fixtures for FinanceDataReader/PyKrx adapter contract tests.
- Mock LLM response fixtures for Report B.
- Mock notification sink.

## Unit Test Matrix

| Area | Required Tests |
| --- | --- |
| Config | required fields, invalid symbols, provider selection, profile defaults |
| Data schema | OHLCV column normalization, date ordering, duplicate handling |
| Validation | missing bars, stale data, nonpositive prices, empty provider response |
| Storage | insert/update/read for symbols, bars, runs, signals, reports |
| Quant | fixture strategy output reproducibility, fee/slippage assumptions |
| Metrics | total return, benchmark comparison, MDD, Sharpe/Sortino presence |
| Signals | buy/sell/hold/watch/no-signal mapping and risk flags |
| Reports | Report A deterministic renderer, Report B prompt inputs, signal id consistency, context separation |
| LLM | mock provider success, timeout, malformed response handling |
| Notify | dry-run sink, durable outbox state transitions, content hash duplicate guard, exactly-once live send guard |

## Integration Tests

- `daily_dry_run_with_fixtures`: fetch fixture data, validate, run quant, generate signals, render both reports, and write notification payload without sending.
- `adapter_contract_finance_data_reader`: mocked or recorded FinanceDataReader response normalized to internal schema.
- `adapter_contract_pykrx`: mocked or recorded PyKrx response normalized to internal schema.
- `storage_to_report_roundtrip`: persisted signal run can regenerate reports.
- `llm_report_modes`: Report A and Report B are generated from the same signal id and differ only by allowed context.
- `duplicate_daily_run_idempotency`: running the same daily job twice with the same report content produces one sent notification record.
- `notification_retry_after_failure`: failed outbox entries can be retried without creating duplicate sent records.
- `scheduler_timezone_contract`: scheduled run times resolve consistently for Asia/Seoul market-close and next-market-open modes.

## Smoke Tests

- `validate-config`
- `fetch --dry-run`
- `run-daily --dry-run`
- `render-report --latest`

## Verification Evidence Required Before v1 Complete

- Passing unit test summary.
- Passing daily dry-run integration output.
- Sample generated Report A and Report B.
- Run log showing provider source, symbol count, warning count, report paths, and notification status.
- Outbox evidence showing duplicate-send prevention.
- Search or test proving no order/broker execution module is active in v1.
