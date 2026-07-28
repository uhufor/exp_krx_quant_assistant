import { LineChart } from '@mantine/charts'
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Paper,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from '@mantine/core'
import { IconAlertCircle, IconShieldCheck } from '@tabler/icons-react'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'

type FoldRange = {
  index: number
  train_start: string
  train_end: string
  test_start: string
  test_end: string
}

type FoldMetrics = {
  total_return: number | null
  mdd: number | null
  sharpe: number | null
  trade_count: number | null
}

type Candidate = {
  params: Record<string, unknown>
  objective: number | null
  total_return: number | null
  mdd: number | null
  error: string
}

type Fold = {
  fold: FoldRange
  params: Record<string, unknown>
  train_metrics: FoldMetrics | null
  test_metrics: FoldMetrics | null
  candidates: Candidate[]
  error: string
}

type Summary = {
  is_objective: number | null
  oos_objective: number | null
  degradation: number | null
  param_stability: number | null
  oos_consistency: number | null
  oos_total_return: number | null
  oos_mdd: number | null
  folds_ok: number
  folds_total: number
}

type Spec = {
  mode: string
  n_folds: number
  test_ratio: number
  anchored: boolean
  objective: string
  grid: Record<string, unknown[]>
}

export type ValidationReport = {
  validation_id: string
  strategy_id: string
  spec: Spec
  summary: Summary
  folds: Fold[]
  oos_equity: Array<{ date: string; value: number }>
  executed_at: string | null
}

type ValidationSummaryRow = {
  validation_id: string
  strategy_id: string
  spec: Spec
  summary: Summary
  executed_at: string
}

const NUMBER_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 5 })

const pct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? 'N/A' : `${NUMBER_FORMATTER.format(v * 100)}%`

const num = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? 'N/A' : NUMBER_FORMATTER.format(v)

const paramsLabel = (params: Record<string, unknown>) => {
  const entries = Object.entries(params)
  if (entries.length === 0) return '-'
  return entries
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(', ')
}

/** 지표를 사람이 읽을 판정으로 요약한다 — 숫자만 던지면 해석이 사용자 몫이 된다(CLI와 동일 기준). */
function overfitWarnings(summary: Summary, spec: Spec): string[] {
  const notes: string[] = []
  if (summary.degradation != null && summary.degradation > 0.5) {
    notes.push(
      `검증 구간에서 ${spec.objective}가 ${pct(summary.degradation)} 떨어졌습니다 — 과최적화 가능성이 높습니다`,
    )
  }
  const hasGrid = Object.keys(spec.grid ?? {}).length > 0
  if (hasGrid && summary.param_stability != null && summary.param_stability < 0.5) {
    notes.push('폴드마다 다른 파라미터가 선택되었습니다 — 노이즈에 맞춰졌을 수 있습니다')
  }
  if (summary.oos_consistency != null && summary.oos_consistency < 0.5) {
    notes.push('검증 구간의 절반 이상이 손실입니다')
  }
  return notes
}

const SUMMARY_ROWS: Array<{ label: string; get: (s: Summary, spec: Spec) => string }> = [
  { label: '폴드', get: (s) => `${s.folds_ok}/${s.folds_total} 성공` },
  { label: '학습(IS)', get: (s, spec) => `${num(s.is_objective)} (${spec.objective})` },
  { label: '검증(OOS)', get: (s, spec) => `${num(s.oos_objective)} (${spec.objective})` },
  { label: '성과 저하율', get: (s) => pct(s.degradation) },
  { label: '파라미터 안정성', get: (s) => pct(s.param_stability) },
  { label: 'OOS 일관성', get: (s) => pct(s.oos_consistency) },
  { label: 'OOS 합성 수익률', get: (s) => pct(s.oos_total_return) },
  { label: 'OOS 합성 MDD', get: (s) => pct(s.oos_mdd) },
]

/** OOS/워크포워드 검증 실행 + 결과(P4). 백테스트 폼의 대상·기간·데이터소스를 그대로 물려받는다. */
export function ValidationPanel({
  strategyId,
  symbols,
  start,
  end,
  dataSource,
  benchmark,
}: {
  strategyId: string | null
  symbols: string
  start: string
  end: string
  dataSource: string
  benchmark: string
}) {
  const [mode, setMode] = useState('walkforward')
  const [nFolds, setNFolds] = useState<number>(3)
  const [testRatio, setTestRatio] = useState<number>(0.3)
  const [anchored, setAnchored] = useState(true)
  const [objective, setObjective] = useState('sharpe')
  const [gridText, setGridText] = useState('')
  const [report, setReport] = useState<ValidationReport | null>(null)
  const [history, setHistory] = useState<ValidationSummaryRow[]>([])
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  const loadHistory = useCallback(() => {
    const query = strategyId ? `?strategy_id=${encodeURIComponent(strategyId)}` : ''
    api
      .get<ValidationSummaryRow[]>(`/validations${query}`)
      .then(setHistory)
      .catch(() => setHistory([]))
  }, [strategyId])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  const handleRun = () => {
    if (!strategyId) {
      setError('전략을 선택하세요')
      return
    }
    let grid: Record<string, unknown[]> = {}
    if (gridText.trim()) {
      try {
        grid = JSON.parse(gridText)
      } catch {
        setError('파라미터 그리드가 올바른 JSON이 아닙니다')
        return
      }
    }
    setRunning(true)
    setError('')
    api
      .post<ValidationReport>('/validations', {
        strategy_id: strategyId,
        symbols: symbols ? symbols.split(',').map((s) => s.trim()) : undefined,
        start: start || undefined,
        end: end || undefined,
        data_source: dataSource,
        benchmark: benchmark || undefined,
        mode,
        n_folds: nFolds,
        test_ratio: testRatio,
        anchored,
        objective,
        grid,
      })
      .then((r) => {
        setReport(r)
        loadHistory()
      })
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setRunning(false))
  }

  const openRun = (validationId: string) => {
    api
      .get<ValidationReport>(`/validations/${validationId}`)
      .then(setReport)
      .catch((e: ApiError) => setError(e.message))
  }

  const warnings = report ? overfitWarnings(report.summary, report.spec) : []

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="sm">
        <Title order={5}>OOS / 워크포워드 검증</Title>
        <Text size="xs" c="dimmed">
          대상 종목·기간·데이터소스는 위 백테스트 설정을 그대로 사용합니다
        </Text>
      </Group>

      <Group align="flex-end" gap="sm" wrap="wrap" mb="sm">
        <Select
          label="방식"
          data={[
            { value: 'walkforward', label: '워크포워드' },
            { value: 'holdout', label: '단일 분할' },
          ]}
          value={mode}
          onChange={(v) => setMode(v ?? 'walkforward')}
          w={130}
        />
        <NumberInput
          label="폴드 수"
          value={nFolds}
          onChange={(v) => setNFolds(Number(v) || 1)}
          min={1}
          max={12}
          w={90}
          disabled={mode === 'holdout'}
        />
        <NumberInput
          label="검증 비율"
          value={testRatio}
          onChange={(v) => setTestRatio(Number(v) || 0.3)}
          min={0.05}
          max={0.95}
          step={0.05}
          decimalScale={2}
          w={110}
        />
        <Select
          label="목적함수"
          data={['sharpe', 'total_return', 'calmar']}
          value={objective}
          onChange={(v) => setObjective(v ?? 'sharpe')}
          w={140}
        />
        <Checkbox
          label="학습창 확장"
          checked={anchored}
          onChange={(e) => setAnchored(e.currentTarget.checked)}
          mb={6}
        />
        <Button
          leftSection={<IconShieldCheck size={16} />}
          onClick={handleRun}
          loading={running}
        >
          검증 실행
        </Button>
      </Group>

      <Textarea
        label="파라미터 그리드 (JSON, 선택)"
        description={
          '예: {"portfolio.max_positions": [3, 5], "factor.sma@5.window": [3, 5, 8], ' +
          '"rule.per_rule.threshold": [10, 15]} — 비우면 파라미터 선택 없이 IS/OOS 성과만 비교합니다'
        }
        placeholder='{"factor.sma@5.window": [3, 5, 8]}'
        value={gridText}
        onChange={(e) => setGridText(e.currentTarget.value)}
        autosize
        minRows={2}
        mb="sm"
      />

      {error && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" title="검증 실패" mb="sm">
          {error}
        </Alert>
      )}

      {report && (
        <Stack gap="md">
          <Group gap="xs">
            <Badge variant="light" color={warnings.length > 0 ? 'yellow' : 'teal'}>
              {warnings.length > 0 ? '과최적화 의심' : '뚜렷한 과최적화 신호 없음'}
            </Badge>
            <Text size="xs" c="dimmed">
              validation_id: {report.validation_id}
              {report.executed_at &&
                ` · ${new Date(report.executed_at).toLocaleString('ko-KR')}`}
            </Text>
          </Group>

          {warnings.length > 0 && (
            <Alert icon={<IconAlertCircle size={16} />} color="yellow">
              <Stack gap={4}>
                {warnings.map((note) => (
                  <Text key={note} size="sm">
                    {note}
                  </Text>
                ))}
              </Stack>
            </Alert>
          )}

          <Table withTableBorder striped>
            <Table.Tbody>
              {SUMMARY_ROWS.map((row) => (
                <Table.Tr key={row.label}>
                  <Table.Th w={180}>{row.label}</Table.Th>
                  <Table.Td>{row.get(report.summary, report.spec)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>

          {report.oos_equity.length > 0 && (
            <div>
              <Text size="sm" fw={500} mb={4}>
                OOS 합성 자산곡선
              </Text>
              <Text size="xs" c="dimmed" mb="xs">
                각 폴드의 검증 구간 수익률만 이어붙인 곡선입니다 — 학습 구간 성과는 포함되지
                않습니다.
              </Text>
              <LineChart
                h={240}
                data={report.oos_equity}
                dataKey="date"
                series={[{ name: 'value', label: 'OOS 누적', color: 'teal.6' }]}
                curveType="linear"
                withDots={false}
              />
            </div>
          )}

          <ScrollArea>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>#</Table.Th>
                  <Table.Th>학습 구간</Table.Th>
                  <Table.Th>검증 구간</Table.Th>
                  <Table.Th>선택 파라미터</Table.Th>
                  <Table.Th>IS 수익률</Table.Th>
                  <Table.Th>OOS 수익률</Table.Th>
                  <Table.Th>OOS MDD</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {report.folds.map((fold) => (
                  <Table.Tr key={fold.fold.index}>
                    <Table.Td>{fold.fold.index + 1}</Table.Td>
                    <Table.Td>
                      {fold.fold.train_start} ~ {fold.fold.train_end}
                    </Table.Td>
                    <Table.Td>
                      {fold.fold.test_start} ~ {fold.fold.test_end}
                    </Table.Td>
                    <Table.Td>{paramsLabel(fold.params)}</Table.Td>
                    {fold.error ? (
                      <Table.Td colSpan={3}>
                        <Text size="sm" c="red">
                          {fold.error}
                        </Text>
                      </Table.Td>
                    ) : (
                      <>
                        <Table.Td>{pct(fold.train_metrics?.total_return)}</Table.Td>
                        <Table.Td>{pct(fold.test_metrics?.total_return)}</Table.Td>
                        <Table.Td>{pct(fold.test_metrics?.mdd)}</Table.Td>
                      </>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Stack>
      )}

      {history.length > 0 && (
        <Stack gap="xs" mt="md">
          <Text size="sm" fw={500}>
            검증 이력
          </Text>
          <ScrollArea.Autosize mah={240}>
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>validation_id</Table.Th>
                  <Table.Th>방식</Table.Th>
                  <Table.Th>폴드</Table.Th>
                  <Table.Th>저하율</Table.Th>
                  <Table.Th>OOS 수익률</Table.Th>
                  <Table.Th>실행 시각</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {history.map((row) => (
                  <Table.Tr
                    key={row.validation_id}
                    onClick={() => openRun(row.validation_id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <Table.Td>{row.validation_id}</Table.Td>
                    <Table.Td>
                      {row.spec.mode} · {row.spec.objective}
                    </Table.Td>
                    <Table.Td>
                      {row.summary.folds_ok}/{row.summary.folds_total}
                    </Table.Td>
                    <Table.Td>{pct(row.summary.degradation)}</Table.Td>
                    <Table.Td>{pct(row.summary.oos_total_return)}</Table.Td>
                    <Table.Td>{new Date(row.executed_at).toLocaleString('ko-KR')}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>
        </Stack>
      )}
    </Paper>
  )
}
