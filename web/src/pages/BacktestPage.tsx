import { LineChart } from '@mantine/charts'
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { IconAlertCircle, IconPlayerPlay } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
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
  results: Record<
    string,
    {
      equity_curve: Array<{ date: string; value: number }>
      price_curve: Array<{ date: string; value: number }>
      trades: Record<string, unknown>[]
    }
  >
  errors: Record<string, string>
}

// 결과 화면 전 영역 공통 — 소수점은 최대 5자리까지만 표시(요청사항).
const NUMBER_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 5 })

function fmtNum(v: unknown): string {
  if (v == null) return '-'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return 'N/A'
    return NUMBER_FORMATTER.format(v)
  }
  return String(v)
}

const pct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? 'N/A' : `${NUMBER_FORMATTER.format(v * 100)}%`

// 백엔드가 vectorbt records_readable 컬럼을 snake_case로 정규화해 내려주므로(예: entry_timestamp,
// avg_entry_price), 원본 id/key를 그대로 노출하지 않고 한국어 용어로 매핑한다.
const TRADE_COLUMN_LABELS: Record<string, string> = {
  exit_trade_id: '거래번호',
  entry_trade_id: '거래번호',
  column: '종목번호',
  size: '수량',
  entry_timestamp: '진입일',
  entry_date: '진입일',
  avg_entry_price: '진입가',
  entry_price: '진입가',
  entry_fees: '진입수수료',
  exit_timestamp: '청산일',
  exit_date: '청산일',
  avg_exit_price: '청산가',
  exit_price: '청산가',
  exit_fees: '청산수수료',
  pnl: '손익',
  return: '수익률',
  direction: '방향',
  status: '상태',
  position_id: '포지션번호',
}

function tradeColumnLabel(key: string): string {
  return (
    TRADE_COLUMN_LABELS[key] ??
    key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  )
}

// vectorbt 버전마다 컬럼명이 entry_timestamp/entry_date 등으로 다를 수 있어(위 주석 참고)
// 자산 곡선 마커도 표와 동일하게 여러 후보 키 중 존재하는 값을 그대로 쓴다.
const TRADE_ENTRY_DATE_KEYS = ['entry_timestamp', 'entry_date']
const TRADE_EXIT_DATE_KEYS = ['exit_timestamp', 'exit_date']
const TRADE_ID_KEYS = ['position_id', 'exit_trade_id', 'entry_trade_id']

function pickTradeField(trade: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (trade[key] != null) return trade[key]
  }
  return undefined
}

type TradeMarker = { x: string; label: string; color: string }

/** 자산 곡선(value)과 주가 곡선(price)을 날짜 기준으로 한 배열로 합친다 — 두 시계열은
 * 같은 OHLCV 인덱스에서 나오므로 날짜 집합이 대개 일치하지만, 혹시 어긋나도 안전하게
 * 합집합 날짜로 병합한다(값이 없는 쪽은 undefined -> 차트에서 해당 지점만 끊김). */
function mergeCurves(
  equityCurve: Array<{ date: string; value: number }>,
  priceCurve: Array<{ date: string; value: number }>,
): Array<{ date: string; value?: number; price?: number }> {
  const valueByDate = new Map(equityCurve.map((p) => [p.date, p.value]))
  const priceByDate = new Map(priceCurve.map((p) => [p.date, p.value]))
  const dates = Array.from(new Set([...valueByDate.keys(), ...priceByDate.keys()])).sort()
  return dates.map((date) => ({
    date,
    value: valueByDate.get(date),
    price: priceByDate.get(date),
  }))
}

/** 거래 내역(진입/청산)을 자산 곡선 위 세로 기준선으로 표시할 마커 목록을 만든다 —
 * 라벨의 거래번호는 표의 "거래번호" 컬럼과 동일한 값을 쓴다(없으면 1부터 순번). */
function buildTradeMarkers(trades: Record<string, unknown>[]): TradeMarker[] {
  return trades.flatMap((trade, i) => {
    const idRaw = pickTradeField(trade, TRADE_ID_KEYS)
    const tradeNo = idRaw != null ? String(idRaw) : String(i + 1)
    const entryDate = pickTradeField(trade, TRADE_ENTRY_DATE_KEYS)
    const exitDate = pickTradeField(trade, TRADE_EXIT_DATE_KEYS)
    const marks: TradeMarker[] = []
    if (typeof entryDate === 'string') {
      marks.push({ x: entryDate, label: `#${tradeNo} 진입`, color: 'teal' })
    }
    if (typeof exitDate === 'string') {
      marks.push({ x: exitDate, label: `#${tradeNo} 청산`, color: 'red' })
    }
    return marks
  })
}

const DIRECTION_LABELS: Record<string, string> = { long: '매수', short: '매도' }
const STATUS_LABELS: Record<string, string> = { closed: '청산완료', open: '보유중' }

function tradeCellValue(key: string, v: unknown): string {
  if (v == null) return '-'
  if (key === 'direction' && typeof v === 'string') {
    return DIRECTION_LABELS[v.toLowerCase()] ?? v
  }
  if (key === 'status' && typeof v === 'string') {
    return STATUS_LABELS[v.toLowerCase()] ?? v
  }
  if (key === 'return' && typeof v === 'number') {
    return pct(v)
  }
  if (typeof v === 'number') {
    return fmtNum(v)
  }
  return String(v)
}

function MetricStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Card withBorder padding="sm" radius="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text size="lg" fw={600} c={color}>
        {value}
      </Text>
    </Card>
  )
}

/** 백테스트 실행 + 결과 시각화(PRD 백테스트 AC1-4, M4). */
export function BacktestPage() {
  const [strategyIds, setStrategyIds] = useState<string[]>([])
  const [strategyId, setStrategyId] = useState<string | null>(null)
  const [symbols, setSymbols] = useState('')
  const [dataSource, setDataSource] = useState<'fixture' | 'fdr' | 'pykrx'>('fixture')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [benchmark, setBenchmark] = useState('')
  const [report, setReport] = useState<BacktestReport | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState('')
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
  const tradeColumns = result && result.trades.length > 0 ? Object.keys(result.trades[0]) : []
  const tradeMarkers = result ? buildTradeMarkers(result.trades) : []
  const chartData = result ? mergeCurves(result.equity_curve, result.price_curve) : []

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Group align="flex-end" gap="sm" wrap="wrap">
          <Select
            label="전략"
            placeholder="전략 선택"
            data={strategyIds}
            value={strategyId}
            onChange={setStrategyId}
            w={180}
          />
          <TextInput
            label="종목"
            placeholder="콤마 구분, 생략 시 전략 universe.symbols 사용"
            value={symbols}
            onChange={(e) => setSymbols(e.currentTarget.value)}
            w={220}
          />
          <Select
            label="데이터소스"
            data={['fixture', 'fdr', 'pykrx']}
            value={dataSource}
            onChange={(v) => setDataSource((v as typeof dataSource) ?? 'fixture')}
            w={110}
          />
          <TextInput
            label="시작일"
            type="date"
            value={start}
            onChange={(e) => setStart(e.currentTarget.value)}
          />
          <TextInput
            label="종료일"
            type="date"
            value={end}
            onChange={(e) => setEnd(e.currentTarget.value)}
          />
          <TextInput
            label="벤치마크"
            placeholder="선택, 예: KOSPI"
            value={benchmark}
            onChange={(e) => setBenchmark(e.currentTarget.value)}
            w={130}
          />
          <Button
            leftSection={<IconPlayerPlay size={16} />}
            onClick={handleRun}
            loading={running}
          >
            백테스트 실행
          </Button>
        </Group>
      </Paper>

      {error && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="백테스트 실패">
          {error}
        </Alert>
      )}

      {report && (
        <Stack gap="md">
          {Object.keys(report.errors).length > 0 && (
            <Alert icon={<IconAlertCircle size={16} />} color="yellow" title="일부 종목 제외됨">
              <Stack gap={4}>
                {Object.entries(report.errors).map(([sym, msg]) => (
                  <Text key={sym} size="sm">
                    {sym}: {msg}
                  </Text>
                ))}
              </Stack>
            </Alert>
          )}

          {Object.keys(report.results).length > 1 && (
            <Select
              label="종목"
              data={Object.keys(report.results)}
              value={selectedSymbol}
              onChange={(v) => setSelectedSymbol(v ?? '')}
              w={160}
            />
          )}

          {metrics && (
            <SimpleGrid cols={{ base: 2, sm: 3, md: 6 }}>
              <MetricStat label="총수익률" value={pct(metrics.total_return)} />
              <MetricStat label="최대낙폭(MDD)" value={pct(metrics.mdd)} color="red" />
              <MetricStat label="샤프지수" value={fmtNum(metrics.sharpe)} />
              <MetricStat label="승률" value={pct(metrics.win_rate)} />
              <MetricStat label="거래횟수" value={String(metrics.trade_count)} />
              <MetricStat
                label="총비용"
                value={fmtNum(metrics.fees_paid + metrics.slippage_cost)}
              />
              <MetricStat label="벤치마크 수익률" value={pct(metrics.benchmark_return)} />
              <MetricStat
                label="초과수익률"
                value={pct(metrics.excess_return)}
                color={(metrics.excess_return ?? 0) >= 0 ? 'teal' : 'red'}
              />
            </SimpleGrid>
          )}

          {metrics && metrics.benchmark_note && (
            <Text size="xs" c="dimmed">
              벤치마크 참고: {metrics.benchmark_note}
            </Text>
          )}

          {result && result.equity_curve.length > 0 && (
            <Paper withBorder p="md" radius="md">
              <Title order={5} mb="sm">
                자산 곡선
              </Title>
              <LineChart
                h={280}
                data={chartData}
                dataKey="date"
                series={[
                  { name: 'value', label: '자산가치', color: 'blue.6' },
                  { name: 'price', label: '주가', color: 'grape.6', yAxisId: 'right' },
                ]}
                curveType="monotone"
                withDots={false}
                withLegend
                gridAxis="xy"
                valueFormatter={(value) => fmtNum(value)}
                referenceLines={tradeMarkers}
                withRightYAxis
                rightYAxisLabel="주가"
              />
            </Paper>
          )}

          {result && (
            <Paper withBorder p="md" radius="md">
              <Group justify="space-between" mb="sm">
                <Title order={5}>거래 내역</Title>
                <Badge variant="light">{result.trades.length}건</Badge>
              </Group>
              {result.trades.length > 0 && (
                <ScrollArea>
                  <Table striped highlightOnHover withTableBorder>
                    <Table.Thead>
                      <Table.Tr>
                        {tradeColumns.map((col) => (
                          <Table.Th key={col}>{tradeColumnLabel(col)}</Table.Th>
                        ))}
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {result.trades.map((trade, i) => (
                        // eslint-disable-next-line react/no-array-index-key
                        <Table.Tr key={i}>
                          {tradeColumns.map((col) => (
                            <Table.Td key={col}>{tradeCellValue(col, trade[col])}</Table.Td>
                          ))}
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </ScrollArea>
              )}
            </Paper>
          )}
        </Stack>
      )}
    </Stack>
  )
}
