# Deep Interview Transcript: Korean Stock Quant Assistant

- Profile: standard
- Context type: greenfield
- Context snapshot: `.omx/context/korean-stock-quant-assistant-20260627T172044Z.md`
- Final ambiguity: 17.8%
- Threshold: 20%

## Condensed Transcript

### Round 1
- Target: Intent / Decision Boundary
- Question: What responsibility level should the buy/sell signal have?
- Answer: The current goal is a strong recommendation while the user makes the final decision. If performance is good, this may later expand to automated trading. The tool is personal-only, not a commercial service, so legal/compliance concerns are out of scope.

### Round 2
- Target: Success Criteria / Scope
- Question: What does "good performance" mean?
- Answer: The user initially assumed cumulative return, meaning a buy timing identified by backtest should produce high profit, but asked for a better evaluation standard.

### Round 3
- Target: Success Criteria / Tradeoff
- Question: Should the first version optimize for aggressive return, balanced return/risk, conservative drawdown control, or research-mode comparison?
- Answer: Use the balanced profile as the default, and allow later changes.

### Round 4
- Target: Decision Boundaries / LLM Role
- Question: How much should the LLM participate in buy/sell judgment?
- Answer: Build both A and B report paths from the same quant signal. One report explains the quant signal only; the other uses news/disclosure/theme context to produce a separate assisted judgment.

### Round 5
- Target: Non-goals / Scope
- Question: What should be explicitly out of scope for v1?
- Answer: Exclude auto order execution, real-time intraday alerts, and raw news/disclosure crawling from v1. Include rebalancing optimization as a recommendation report. Theme discovery should be available as a report.

### Round 6
- Target: Constraints / Data Universe
- Question: What universe should v1 analyze?
- Answer: Use a staged approach. v1 starts with a user-defined watchlist. v2 expands to theme reports. v3 and later can test full Korean market screening.

### Round 7
- Target: Decision Boundaries / Closure
- Question: May the planner choose practical defaults for data source, notification channel, and runtime environment?
- Answer: Yes. The user prefers a local Mac mini for quant engine, scheduling, and notification sending; external Codex or Claude Code API for LLM integration; a researched stock data acquisition layer with adapters; and one report per day.

## Pressure-Pass Findings

- Original assumption: cumulative return alone might be the performance standard.
- Pressure result: cumulative return alone is insufficient because it can hide high drawdown, overtrading, and poor live feasibility.
- Resolution: default to a balanced evaluation profile: benchmark-relative return, MDD guardrail, risk-adjusted metrics, transaction-cost/slippage assumptions, trade frequency, and recent-period robustness.

## Research Notes

- VectorBT Portfolio statistics support return, drawdown, risk/performance, Sharpe/Sortino, benchmark-related metrics, and trade records.
- FinanceDataReader supports KRX/KOSPI/KOSDAQ listings, delisting/admin listings, Korean individual stock price reads, and KRX/Naver/Yahoo source selection.
- PyKrx provides KRX/Naver scraping for Korean stock/bond market data and OHLCV access, with maintainer warnings about scraping, data differences, and rate discipline.
- Korea Investment Open API provides domestic stock API documentation, test bed, REST/WebSocket examples, and a path for later brokerage integration.

