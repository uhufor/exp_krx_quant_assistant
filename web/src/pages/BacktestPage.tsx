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
    { equity_curve: Array<{ date: string; value: number }>; trades: Record<string, unknown>[] }
  >
}

const pct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? 'N/A' : `${(v * 100).toFixed(2)}%`

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
            placeholder="콤마 구분, 생략 시 universe/watchlist"
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
              <MetricStat label="MDD" value={pct(metrics.mdd)} color="red" />
              <MetricStat
                label="Sharpe"
                value={metrics.sharpe?.toFixed(3) ?? 'N/A'}
              />
              <MetricStat label="승률" value={pct(metrics.win_rate)} />
              <MetricStat label="거래횟수" value={String(metrics.trade_count)} />
              <MetricStat
                label="총비용"
                value={(metrics.fees_paid + metrics.slippage_cost).toFixed(2)}
              />
              {metrics.benchmark_return != null && (
                <>
                  <MetricStat label="벤치마크 수익률" value={pct(metrics.benchmark_return)} />
                  <MetricStat
                    label="초과수익률"
                    value={pct(metrics.excess_return)}
                    color={
                      (metrics.excess_return ?? 0) >= 0 ? 'teal' : 'red'
                    }
                  />
                </>
              )}
            </SimpleGrid>
          )}

          {result && result.equity_curve.length > 0 && (
            <Paper withBorder p="md" radius="md">
              <Title order={5} mb="sm">
                자산곡선(Equity Curve)
              </Title>
              <LineChart
                h={280}
                data={result.equity_curve}
                dataKey="date"
                series={[{ name: 'value', color: 'blue.6' }]}
                curveType="monotone"
                withDots={false}
                gridAxis="xy"
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
                        {Object.keys(result.trades[0]).map((col) => (
                          <Table.Th key={col}>{col}</Table.Th>
                        ))}
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {result.trades.map((trade, i) => (
                        // eslint-disable-next-line react/no-array-index-key
                        <Table.Tr key={i}>
                          {Object.values(trade).map((v, j) => (
                            // eslint-disable-next-line react/no-array-index-key
                            <Table.Td key={j}>{String(v)}</Table.Td>
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
