import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, ApiError } from '../api/client'

type Metrics = {
  total_return: number
  mdd: number
  sharpe: number
  win_rate: number
  trade_count: number
  fees_paid: number
  slippage_cost: number
  benchmark_return: number | null
  excess_return: number | null
  benchmark_note: string
}

type BacktestReport = {
  metrics: Metrics
  per_symbol: Record<string, Metrics>
  results: Record<string, { equity_curve: Array<{ date: string; value: number }>; trades: Record<string, unknown>[] }>
}

const pct = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? 'N/A' : `${(v * 100).toFixed(2)}%`)

/** 백테스트 실행 + 결과 시각화(PRD 백테스트 AC1-4, M4). */
export function BacktestPage() {
  const [strategyIds, setStrategyIds] = useState<string[]>([])
  const [strategyId, setStrategyId] = useState('')
  const [symbols, setSymbols] = useState('')
  const [dataSource, setDataSource] = useState<'fixture' | 'fdr' | 'pykrx'>('fixture')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [benchmark, setBenchmark] = useState('')
  const [report, setReport] = useState<BacktestReport | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<string>('')
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    api
      .get<Array<{ id: string }>>('/strategies')
      .then((items) => setStrategyIds(items.map((i) => i.id)))
      .catch((e: ApiError) => setError(e.message))
  }, [])

  const handleRun = () => {
    if (!strategyId) {
      setError('전략을 선택하세요')
      return
    }
    setRunning(true)
    setError('')
    api
      .post<BacktestReport>('/backtests', {
        strategy_id: strategyId,
        symbols: symbols ? symbols.split(',').map((s) => s.trim()) : undefined,
        start: start || undefined,
        end: end || undefined,
        data_source: dataSource,
        benchmark: benchmark || undefined,
      })
      .then((r) => {
        setReport(r)
        const first = Object.keys(r.results)[0] ?? ''
        setSelectedSymbol(first)
      })
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setRunning(false))
  }

  const result = report && selectedSymbol ? report.results[selectedSymbol] : null
  const metrics = report && selectedSymbol ? report.per_symbol[selectedSymbol] : report?.metrics

  return (
    <div>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
          <option value="">전략 선택</option>
          {strategyIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
        <input
          placeholder="종목(콤마 구분, 생략 시 universe/watchlist)"
          value={symbols}
          onChange={(e) => setSymbols(e.target.value)}
        />
        <select value={dataSource} onChange={(e) => setDataSource(e.target.value as typeof dataSource)}>
          <option value="fixture">fixture</option>
          <option value="fdr">fdr</option>
          <option value="pykrx">pykrx</option>
        </select>
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        <input
          placeholder="벤치마크(선택, 예: KOSPI)"
          value={benchmark}
          onChange={(e) => setBenchmark(e.target.value)}
        />
        <button type="button" onClick={handleRun} disabled={running}>
          {running ? '실행 중...' : '백테스트 실행'}
        </button>
      </div>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {report && (
        <div>
          {Object.keys(report.results).length > 1 && (
            <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}>
              {Object.keys(report.results).map((sym) => (
                <option key={sym} value={sym}>
                  {sym}
                </option>
              ))}
            </select>
          )}

          {metrics && (
            <table>
              <tbody>
                <tr>
                  <th>총수익률</th>
                  <td>{pct(metrics.total_return)}</td>
                  <th>MDD</th>
                  <td>{pct(metrics.mdd)}</td>
                  <th>Sharpe</th>
                  <td>{metrics.sharpe?.toFixed(3) ?? 'N/A'}</td>
                </tr>
                <tr>
                  <th>승률</th>
                  <td>{pct(metrics.win_rate)}</td>
                  <th>거래횟수</th>
                  <td>{metrics.trade_count}</td>
                  <th>총비용</th>
                  <td>{(metrics.fees_paid + metrics.slippage_cost).toFixed(2)}</td>
                </tr>
                {metrics.benchmark_return != null && (
                  <tr>
                    <th>벤치마크 수익률</th>
                    <td>{pct(metrics.benchmark_return)}</td>
                    <th>초과수익률</th>
                    <td>{pct(metrics.excess_return)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}

          {result && result.equity_curve.length > 0 && (
            <div style={{ height: 300, marginTop: '1rem' }}>
              <h3>자산곡선(Equity Curve)</h3>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.equity_curve}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis domain={['auto', 'auto']} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {result && (
            <div style={{ marginTop: '1rem' }}>
              <h3>거래 내역({result.trades.length}건)</h3>
              {result.trades.length > 0 && (
                <table>
                  <thead>
                    <tr>
                      {Object.keys(result.trades[0]).map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((trade, i) => (
                      // eslint-disable-next-line react/no-array-index-key
                      <tr key={i}>
                        {Object.values(trade).map((v, j) => (
                          // eslint-disable-next-line react/no-array-index-key
                          <td key={j}>{String(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
