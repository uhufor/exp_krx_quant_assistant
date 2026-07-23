import {
  Alert,
  Button,
  Checkbox,
  Group,
  List,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core'
import { IconAlertCircle, IconCheck, IconPlayerPlay, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { useFactors, useResourceIds } from '../api/hooks'
import { ResourceListPanel } from '../components/ResourceListPanel'
import { notifyError, notifySuccess } from '../notify'
import { ScreeningTreeEditor } from '../tree/ScreeningTreeEditor'
import {
  SCREENING_FILTER_LABELS,
  SCREENING_SUPPORTED_FILTERS,
  SCREENING_UNSUPPORTED_FILTERS,
  defaultScreeningCondition,
} from '../tree/screeningTypes'
import type { ScanUniverseJSON, ScreeningConditionJSON } from '../tree/screeningTypes'

type ValidationResult = { ok: boolean; errors: string[] }
type RunResultItem = { symbol: string; name: string }
type RunResult = {
  condition_id: string
  as_of: string
  passed: RunResultItem[]
  count: number
}

/** 스캔 유니버스(ScanUniverse) 편집 — market은 고정 표시, 제외 필터는 4종 활성 토글 +
 * 6종 예약 필터(항상 비활성, "v1 미지원" 툴팁)로 구성한다. 6종은 절대 선택 가능한
 * 상태로 렌더링하지 않는다(선택해도 저장 시 UnsupportedFilterError로 항상 실패하는
 * 함정 UI를 방지하는 안전 요구사항). */
function ScanUniverseEditor({
  value,
  onChange,
}: {
  value: ScanUniverseJSON
  onChange: (v: ScanUniverseJSON) => void
}) {
  const toggle = (filter: string, checked: boolean) => {
    const next = checked
      ? [...value.exclusion_filters, filter]
      : value.exclusion_filters.filter((f) => f !== filter)
    onChange({ ...value, exclusion_filters: next })
  }

  return (
    <div>
      <Title order={5} mb="xs">
        스캔 대상(universe)
      </Title>
      <Stack gap="xs">
        <TextInput label="시장(market)" value="KOSPI+KOSDAQ" disabled w={200} />

        <Text size="sm" fw={500}>
          제외 필터
        </Text>
        <Group gap="md">
          {SCREENING_SUPPORTED_FILTERS.map((filter) => (
            <Checkbox
              key={filter}
              label={SCREENING_FILTER_LABELS[filter]}
              checked={value.exclusion_filters.includes(filter)}
              onChange={(e) => toggle(filter, e.currentTarget.checked)}
            />
          ))}
        </Group>

        <Text size="sm" fw={500} c="dimmed" mt="xs">
          예약됨(v1 미지원)
        </Text>
        <Group gap="md">
          {SCREENING_UNSUPPORTED_FILTERS.map((filter) => (
            <Tooltip
              key={filter}
              label="v1 미지원(데이터 소스 없음) — 선택할 수 없습니다"
              multiline
              w={220}
            >
              <Checkbox
                label={SCREENING_FILTER_LABELS[filter]}
                checked={false}
                disabled
                readOnly
              />
            </Tooltip>
          ))}
        </Group>
      </Stack>
    </div>
  )
}

function RunResultTable({ result }: { result: RunResult }) {
  return (
    <Stack gap="xs">
      <Text size="sm">
        기준일 {result.as_of} — 통과 {result.count}종목
      </Text>
      {result.passed.length === 0 ? (
        <Text size="sm" c="dimmed">
          통과한 종목이 없습니다.
        </Text>
      ) : (
        <Table striped highlightOnHover withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>종목코드</Table.Th>
              <Table.Th>종목명</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {result.passed.map((row) => (
              <Table.Tr key={row.symbol}>
                <Table.Td>{row.symbol}</Table.Td>
                <Table.Td>{row.name}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  )
}

/** 스크리닝(Screening) 조건 CRUD + 실행 — 조건 트리는 재귀 편집기(ScreeningTreeEditor),
 * 나머지 필드는 폼(RuleBuilderPage/StrategyBuilderPage와 동일 관례, JSON 직접 입력 없음). */
export function ScreeningBuilderPage() {
  const factors = useFactors()
  const [refreshKey, setRefreshKey] = useState(0)
  const screeningIds = useResourceIds('screenings', refreshKey)
  const [selectedId, setSelectedId] = useState('')
  const [newId, setNewId] = useState('')
  const [doc, setDoc] = useState<ScreeningConditionJSON | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [asOf, setAsOf] = useState('')
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const [running, setRunning] = useState(false)
  const [universeSize, setUniverseSize] = useState<number | null>(null)
  const [checkingUniverseSize, setCheckingUniverseSize] = useState(false)

  const load = (id: string) => {
    setSelectedId(id)
    setValidation(null)
    setRunResult(null)
    setUniverseSize(null)
    if (!id) {
      setDoc(null)
      return
    }
    api
      .get<ScreeningConditionJSON>(`/screenings/${id}`)
      .then(setDoc)
      .catch((e: ApiError) => notifyError(`조회 실패: ${e.message}`))
  }

  const startNew = () => {
    if (!newId) {
      notifyError('신규 id를 입력하세요')
      return
    }
    setSelectedId('')
    setDoc(defaultScreeningCondition(newId, factors))
    setValidation(null)
    setRunResult(null)
  }

  const handleValidate = () => {
    if (!selectedId) return
    api
      .post<ValidationResult>(`/screenings/${selectedId}/validate`)
      .then(setValidation)
      .catch((e: ApiError) => notifyError(`검증 요청 실패: ${e.message}`))
  }

  const handleSave = () => {
    if (!doc) return
    const id = selectedId || newId
    const isNew = !selectedId
    const request = isNew
      ? api.post<ScreeningConditionJSON>('/screenings', doc)
      : api.put<ScreeningConditionJSON>(`/screenings/${id}`, doc)
    request
      .then(() => {
        notifySuccess(`'${id}' 저장 완료`)
        setNewId('')
        setRefreshKey((k) => k + 1)
        load(id)
      })
      .catch((e: ApiError) => notifyError(`저장 실패: ${e.message}`))
  }

  const handleDelete = () => {
    if (!selectedId) return
    api
      .del(`/screenings/${selectedId}`)
      .then(() => {
        notifySuccess(`'${selectedId}' 삭제 완료`)
        setSelectedId('')
        setDoc(null)
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => notifyError(`삭제 실패: ${e.message}`))
  }

  const handleCheckUniverseSize = () => {
    if (!selectedId) return
    setCheckingUniverseSize(true)
    setUniverseSize(null)
    api
      .get<{ condition_id: string; count: number }>(`/screenings/${selectedId}/universe-size`)
      .then((result) => setUniverseSize(result.count))
      .catch((e: ApiError) => notifyError(`대상 종목수 조회 실패: ${e.message}`))
      .finally(() => setCheckingUniverseSize(false))
  }

  const handleRun = () => {
    if (!selectedId) return
    setRunning(true)
    setRunResult(null)
    api
      .post<RunResult>(`/screenings/${selectedId}/run`, asOf ? { as_of: asOf } : {})
      .then((result) => {
        setRunResult(result)
        notifySuccess(`실행 완료 — 통과 ${result.count}종목`)
      })
      .catch((e: ApiError) => notifyError(`실행 실패: ${e.message}`))
      .finally(() => setRunning(false))
  }

  return (
    <Group align="flex-start" gap="md">
      <ResourceListPanel
        title="스크리닝 조건 목록"
        ids={screeningIds}
        selectedId={selectedId}
        onSelect={load}
        newId={newId}
        onNewIdChange={setNewId}
        onStartNew={startNew}
        newLabel="새 조건"
      />

      {doc && (
        <Paper withBorder p="md" radius="md" style={{ flex: 1 }}>
          <Stack gap="md">
            <Group align="flex-end">
              <TextInput label="ID" value={doc.id} disabled w={180} />
              <TextInput
                label="이름"
                value={doc.name}
                onChange={(e) => setDoc({ ...doc, name: e.currentTarget.value })}
              />
              <TextInput
                label="버전"
                value={doc.version}
                onChange={(e) => setDoc({ ...doc, version: e.currentTarget.value })}
                w={80}
              />
            </Group>

            <ScanUniverseEditor
              value={doc.universe}
              onChange={(universe) => setDoc({ ...doc, universe })}
            />

            <div>
              <Title order={5} mb="xs">
                조건
              </Title>
              <ScreeningTreeEditor
                value={doc.root}
                onChange={(root) => setDoc({ ...doc, root })}
                factors={factors}
              />
            </div>

            <Group>
              <Button variant="default" onClick={handleValidate} disabled={!selectedId}>
                검증
              </Button>
              <Button onClick={handleSave}>저장</Button>
              <Button
                color="red"
                variant="outline"
                leftSection={<IconTrash size={14} />}
                onClick={handleDelete}
                disabled={!selectedId}
              >
                삭제
              </Button>
            </Group>

            {validation && (
              <Alert
                icon={validation.ok ? <IconCheck size={16} /> : <IconAlertCircle size={16} />}
                color={validation.ok ? 'green' : 'red'}
                title={validation.ok ? '검증 통과' : '검증 실패'}
              >
                {!validation.ok && (
                  <List size="sm">
                    {validation.errors.map((err) => (
                      <List.Item key={err}>{err}</List.Item>
                    ))}
                  </List>
                )}
              </Alert>
            )}

            <div>
              <Title order={5} mb="xs">
                실행
              </Title>
              <Group align="flex-end">
                <TextInput
                  label="기준일(as_of, 생략 시 오늘)"
                  placeholder="YYYY-MM-DD"
                  value={asOf}
                  onChange={(e) => setAsOf(e.currentTarget.value)}
                  w={180}
                />
                <Button
                  variant="default"
                  onClick={handleCheckUniverseSize}
                  disabled={!selectedId}
                  loading={checkingUniverseSize}
                >
                  대상 종목수 확인
                </Button>
                <Button
                  leftSection={<IconPlayerPlay size={14} />}
                  onClick={handleRun}
                  disabled={!selectedId || running}
                  loading={running}
                >
                  실행
                </Button>
              </Group>
              {universeSize !== null && (
                <Text size="sm" c="dimmed" mt="xs">
                  대상 종목: <b>{universeSize}</b>개 — 실행은 이 종목들의 시계열 데이터를
                  확보하며 진행되므로 종목 수가 많으면 시간이 걸릴 수 있습니다.
                </Text>
              )}
              {runResult && (
                <div style={{ marginTop: 12 }}>
                  <RunResultTable result={runResult} />
                </div>
              )}
            </div>
          </Stack>
        </Paper>
      )}
    </Group>
  )
}
