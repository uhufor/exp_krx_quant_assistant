import { LineChart } from '@mantine/charts'
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core'
import { IconAlertCircle, IconRefresh } from '@tabler/icons-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api/client'

export type RunMetrics = {
  total_return: number | null
  mdd: number | null
  sharpe: number | null
  sortino: number | null
  win_rate: number | null
  trade_count: number | null
  excess_return: number | null
  benchmark_return: number | null
}

export type RunSummary = {
  run_id: string
  strategy_id: string
  params: {
    symbols: string[]
    start: string | null
    end: string | null
    fees: number
    slippage: number
    data_source: string
    benchmark: string | null
  }
  metrics: RunMetrics
  definition_hash: string
  coverage_fingerprint: string
  executed_at: string
}

type CurvePoint = { date: string; value: number }
type RunDetail = RunSummary & { equity_curves: Record<string, { equity: CurvePoint[] }> }

const NUMBER_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 5 })

const pct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? 'N/A' : `${NUMBER_FORMATTER.format(v * 100)}%`

const num = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? 'N/A' : NUMBER_FORMATTER.format(v)

const SERIES_COLORS = ['blue.6', 'grape.6', 'teal.6', 'orange.6', 'red.6']

/** 비교 표의 행 정의 — 라벨과 추출 함수를 한 곳에 두어 열/행이 어긋나지 않게 한다. */
const COMPARE_ROWS: Array<{ label: string; get: (r: RunSummary) => string }> = [
  { label: '전략', get: (r) => r.strategy_id },
  { label: '기간', get: (r) => `${r.params.start ?? '?'} ~ ${r.params.end ?? '?'}` },
  { label: '종목', get: (r) => r.params.symbols.join(', ') || '-' },
  { label: '데이터소스', get: (r) => r.params.data_source || '-' },
  { label: '수수료/슬리피지', get: (r) => `${r.params.fees} / ${r.params.slippage}` },
  { label: '총수익률', get: (r) => pct(r.metrics.total_return) },
  { label: '초과수익률', get: (r) => pct(r.metrics.excess_return) },
  { label: '최대낙폭(MDD)', get: (r) => pct(r.metrics.mdd) },
  { label: '샤프지수', get: (r) => num(r.metrics.sharpe) },
  { label: '소르티노', get: (r) => num(r.metrics.sortino) },
  { label: '승률', get: (r) => pct(r.metrics.win_rate) },
  { label: '거래횟수', get: (r) => String(r.metrics.trade_count ?? 0) },
  { label: '정의 지문', get: (r) => r.definition_hash.slice(0, 12) },
  { label: '데이터 지문', get: (r) => r.coverage_fingerprint.slice(0, 12) },
]

/** 선택된 실행들의 자본곡선을 날짜 합집합으로 병합한다(run_id별 계열). */
function mergeRunCurves(details: RunDetail[]): Array<Record<string, string | number>> {
  const byDate = new Map<string, Record<string, string | number>>()
  for (const detail of details) {
    // 종목별 곡선을 합산하지 않고 첫 종목만 쓴다 — 현재 백테스트는 종목별 독립 실행이라
    // 합산 자본곡선의 의미가 정의되어 있지 않다(포트폴리오 백테스트 도입 시 재검토).
    const [curve] = Object.values(detail.equity_curves)
    if (!curve) continue
    for (const point of curve.equity) {
      const row = byDate.get(point.date) ?? { date: point.date }
      row[detail.run_id] = point.value
      byDate.set(point.date, row)
    }
  }
  return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)))
}

/** 백테스트 실행 이력 목록 + 선택 비교(P3). */
export function BacktestHistoryPanel({
  strategyId,
  refreshKey,
}: {
  strategyId: string | null
  refreshKey: number
}) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [details, setDetails] = useState<RunDetail[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    const query = strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ''
    api
      .get<RunSummary[]>(`/backtests/runs${query}`)
      .then((items) => {
        setRuns(items)
        // 목록에서 사라진 실행이 선택 상태로 남지 않게 정리한다.
        const alive = new Set(items.map((i) => i.run_id))
        setSelected((prev) => prev.filter((id) => alive.has(id)))
      })
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false))
  }, [strategyId])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  useEffect(() => {
    if (selected.length < 2) {
      setDetails([])
      return
    }
    let cancelled = false
    Promise.all(selected.map((id) => api.get<RunDetail>(`/backtests/runs/${id}`)))
      .then((items) => {
        if (!cancelled) setDetails(items)
      })
      .catch((e: ApiError) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [selected])

  const chartData = useMemo(() => mergeRunCurves(details), [details])
  const selectedRuns = useMemo(
    () => selected.map((id) => runs.find((r) => r.run_id === id)).filter((r): r is RunSummary => !!r),
    [selected, runs],
  )

  const toggle = (runId: string) =>
    setSelected((prev) =>
      prev.includes(runId) ? prev.filter((id) => id !== runId) : [...prev, runId],
    )

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <Title order={5}>실행 이력</Title>
            <Badge variant="light">{runs.length}건</Badge>
          </Group>
          <Button
            variant="subtle"
            size="xs"
            leftSection={<IconRefresh size={14} />}
            onClick={load}
            loading={loading}
          >
            새로고침
          </Button>
        </Group>

        {error && (
          <Alert icon={<IconAlertCircle size={16} />} color="red" mb="sm">
            {error}
          </Alert>
        )}

        {runs.length === 0 ? (
          <Text size="sm" c="dimmed">
            저장된 실행 이력이 없습니다. 백테스트를 실행하면 자동으로 기록됩니다.
          </Text>
        ) : (
          <>
            <Text size="xs" c="dimmed" mb="xs">
              2건 이상 선택하면 아래에 비교 표와 자산 곡선이 함께 표시됩니다.
            </Text>
            <ScrollArea>
              <Table striped highlightOnHover withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40} />
                    <Table.Th>run_id</Table.Th>
                    <Table.Th>전략</Table.Th>
                    <Table.Th>기간</Table.Th>
                    <Table.Th>소스</Table.Th>
                    <Table.Th>총수익률</Table.Th>
                    <Table.Th>MDD</Table.Th>
                    <Table.Th>샤프</Table.Th>
                    <Table.Th>실행시각</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {runs.map((run) => (
                    <Table.Tr key={run.run_id}>
                      <Table.Td>
                        <Checkbox
                          checked={selected.includes(run.run_id)}
                          onChange={() => toggle(run.run_id)}
                          aria-label={`${run.run_id} 비교 선택`}
                        />
                      </Table.Td>
                      <Table.Td>{run.run_id}</Table.Td>
                      <Table.Td>{run.strategy_id}</Table.Td>
                      <Table.Td>
                        {run.params.start ?? '?'} ~ {run.params.end ?? '?'}
                      </Table.Td>
                      <Table.Td>{run.params.data_source || '-'}</Table.Td>
                      <Table.Td>{pct(run.metrics.total_return)}</Table.Td>
                      <Table.Td>{pct(run.metrics.mdd)}</Table.Td>
                      <Table.Td>{num(run.metrics.sharpe)}</Table.Td>
                      <Table.Td>{new Date(run.executed_at).toLocaleString('ko-KR')}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </>
        )}
      </Paper>

      {selectedRuns.length >= 2 && (
        <Paper withBorder p="md" radius="md">
          <Title order={5} mb="sm">
            실행 비교
          </Title>
          <ScrollArea>
            <Table withTableBorder striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>항목</Table.Th>
                  {selectedRuns.map((run) => (
                    <Table.Th key={run.run_id}>{run.run_id}</Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {COMPARE_ROWS.map((row) => (
                  <Table.Tr key={row.label}>
                    <Table.Td fw={500}>{row.label}</Table.Td>
                    {selectedRuns.map((run) => (
                      <Table.Td key={run.run_id}>{row.get(run)}</Table.Td>
                    ))}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>

          {chartData.length > 0 && (
            <>
              <Title order={6} mt="md" mb="sm">
                자산 곡선 비교
              </Title>
              <LineChart
                h={280}
                data={chartData}
                dataKey="date"
                series={details.map((detail, i) => ({
                  name: detail.run_id,
                  label: detail.run_id,
                  color: SERIES_COLORS[i % SERIES_COLORS.length],
                }))}
                curveType="monotone"
                withDots={false}
                withLegend
                gridAxis="xy"
                valueFormatter={(value) => num(value)}
              />
              <Text size="xs" c="dimmed" mt="xs">
                각 실행의 첫 종목 자산 곡선을 겹쳐 표시합니다.
              </Text>
            </>
          )}
        </Paper>
      )}
    </Stack>
  )
}
