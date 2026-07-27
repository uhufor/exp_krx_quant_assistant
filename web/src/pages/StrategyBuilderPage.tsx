import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Checkbox,
  FileButton,
  Group,
  List,
  MultiSelect,
  NumberInput,
  Paper,
  Select,
  Stack,
  TagsInput,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconCheck,
  IconDownload,
  IconPlus,
  IconTrash,
  IconUpload,
} from '@tabler/icons-react'
import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { useFactors, useResourceIds, useTemplates } from '../api/hooks'
import type { TemplateInfo } from '../api/hooks'
import { ResourceListPanel } from '../components/ResourceListPanel'
import { notifyError, notifySuccess } from '../notify'
import type { FactorOption } from '../tree/types'

type FactorRefJSON = { factor_id: string; params: Record<string, number> }
type RuleBindingJSON = { roles: { entry: string[]; exit: string[] } }
type RankingJSON =
  | { kind: 'factor'; factor_id: string; column: string; params: Record<string, number>; descending: boolean }
  | { kind: 'formula'; formula_id: string; descending: boolean }
type PortfolioJSON = {
  max_positions: number
  rebalance: 'weekly' | 'monthly' | 'quarterly'
  sizing: 'equal_weight'
  initial_cash: number
  ranking: RankingJSON | null
}
type StrategyDoc = {
  id: string
  name: string
  version: string
  factor_refs: FactorRefJSON[]
  universe: { symbols: string[] }
  rule: RuleBindingJSON | null
  metadata: Record<string, unknown>
  portfolio: PortfolioJSON | null
}

const DEFAULT_PORTFOLIO: PortfolioJSON = {
  max_positions: 5,
  rebalance: 'monthly',
  sizing: 'equal_weight',
  initial_cash: 10_000_000,
  ranking: null,
}

type ValidationResult = { ok: boolean; errors: string[] }

function emptyDoc(id: string, factors: FactorOption[]): StrategyDoc {
  const first = factors[0]
  return {
    id,
    name: '',
    version: '1',
    factor_refs: first ? [{ factor_id: first.id, params: {} }] : [],
    universe: { symbols: [] },
    rule: null, // 초안 — RuleBinding은 entry가 비어있으면 저장이 거부되므로 null(초안)이 유효한 기본값
    metadata: {},
    portfolio: null, // 미설정 = 종목별 독립 백테스트(기존 동작)
  }
}

/** 전략(Strategy) CRUD — factor_refs/universe/rule 참조를 폼으로 편집(JSON 직접 작성 없음, PRD CRUD AC1). */
export function StrategyBuilderPage() {
  const factors = useFactors()
  const [refreshKey, setRefreshKey] = useState(0)
  const strategyIds = useResourceIds('strategies', refreshKey)
  const ruleIds = useResourceIds('rules', refreshKey)
  const formulaIds = useResourceIds('formulas', refreshKey)
  const templates = useTemplates(refreshKey)
  const [selectedId, setSelectedId] = useState('')
  const [newId, setNewId] = useState('')
  const [doc, setDoc] = useState<StrategyDoc | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [activeState, setActiveState] = useState<boolean | null>(null)
  const [saveAsTemplateId, setSaveAsTemplateId] = useState('')

  const load = (id: string) => {
    setSelectedId(id)
    setValidation(null)
    setActiveState(null)
    if (!id) {
      setDoc(null)
      return
    }
    api
      .get<StrategyDoc>(`/strategies/${id}`)
      .then(setDoc)
      .catch((e: ApiError) => notifyError(`조회 실패: ${e.message}`))
  }

  const startNew = () => {
    if (!newId) {
      notifyError('신규 id를 입력하세요')
      return
    }
    setSelectedId('')
    setDoc(emptyDoc(newId, factors))
    setValidation(null)
    setActiveState(null)
  }

  const handleCreateFromTemplate = (templateId: string | null) => {
    if (!templateId) return
    if (!newId) {
      notifyError('템플릿에서 생성할 신규 id를 입력하세요')
      return
    }
    api
      .post<{ id: string }>(`/templates/from/${templateId}`, { new_id: newId })
      .then((defn) => {
        notifySuccess(`템플릿 '${templateId}'에서 '${defn.id}' 생성 완료`)
        setNewId('')
        setRefreshKey((k) => k + 1)
        load(defn.id)
      })
      .catch((e: ApiError) => notifyError(`템플릿 생성 실패: ${e.message}`))
  }

  const handleSaveAsTemplate = () => {
    if (!selectedId) return
    if (!saveAsTemplateId) {
      notifyError('저장할 template id를 입력하세요')
      return
    }
    api
      .post('/templates', { strategy_id: selectedId, template_id: saveAsTemplateId })
      .then(() => {
        notifySuccess(`'${selectedId}'을(를) 템플릿 '${saveAsTemplateId}'로 저장 완료`)
        setSaveAsTemplateId('')
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => notifyError(`템플릿 저장 실패: ${e.message}`))
  }

  const handleValidate = () => {
    if (!doc) return
    api
      .post<ValidationResult>('/strategies/validate', doc)
      .then(setValidation)
      .catch((e: ApiError) => notifyError(`검증 요청 실패: ${e.message}`))
  }

  const handleSave = () => {
    if (!doc) return
    const id = selectedId || newId
    api
      .put(`/strategies/${id}`, doc)
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
      .del(`/strategies/${selectedId}`)
      .then(() => {
        notifySuccess(`'${selectedId}' 삭제 완료`)
        setSelectedId('')
        setDoc(null)
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => notifyError(`삭제 실패(활성 참조 중일 수 있음): ${e.message}`))
  }

  const handleActivate = (active: boolean) => {
    if (!selectedId) return
    api
      .post(`/strategies/${selectedId}/${active ? 'activate' : 'deactivate'}`)
      .then(() => {
        setActiveState(active)
        notifySuccess(`'${selectedId}' ${active ? '활성화' : '비활성화'} 완료`)
      })
      .catch((e: ApiError) => notifyError(`전환 실패: ${e.message}`))
  }

  const handleExport = () => {
    if (!selectedId) return
    api
      .get<object>(`/strategies/${selectedId}/export`)
      .then((bundle) => {
        const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${selectedId}.json`
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch((e: ApiError) => notifyError(`Export 실패: ${e.message}`))
  }

  const handleImport = (file: File | null) => {
    if (!file) return
    file
      .text()
      .then((text) => api.post('/strategies/import', JSON.parse(text)))
      .then(() => {
        notifySuccess('Import 완료')
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError | Error) => notifyError(`Import 실패: ${e.message}`))
  }

  return (
    <Group align="flex-start" gap="md">
      <ResourceListPanel
        title="전략 목록"
        ids={strategyIds}
        selectedId={selectedId}
        onSelect={load}
        newId={newId}
        onNewIdChange={setNewId}
        onStartNew={startNew}
        newLabel="새 전략(빈 정의)"
      >
        <Select
          label="템플릿에서 생성"
          placeholder="템플릿 선택..."
          data={templates.map((t: TemplateInfo) => ({
            value: t.template_id,
            label: `${t.name} (${t.origin})`,
          }))}
          value={null}
          onChange={handleCreateFromTemplate}
          size="sm"
        />
        <FileButton onChange={handleImport} accept="application/json">
          {(props) => (
            <Button
              {...props}
              variant="light"
              size="sm"
              fullWidth
              leftSection={<IconUpload size={14} />}
            >
              Import
            </Button>
          )}
        </FileButton>
      </ResourceListPanel>

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

            <FactorRefsEditor
              value={doc.factor_refs}
              onChange={(factor_refs) => setDoc({ ...doc, factor_refs })}
              factors={factors}
            />

            <TagsInput
              label="대상 종목(universe.symbols, 비어있으면 백테스트 시 종목을 직접 지정해야 함)"
              placeholder="종목코드 입력 후 Enter(예: 005930)"
              value={doc.universe.symbols}
              onChange={(symbols) => setDoc({ ...doc, universe: { symbols } })}
            />

            <RuleBindingEditor
              value={doc.rule}
              onChange={(rule) => setDoc({ ...doc, rule })}
              ruleIds={ruleIds}
            />

            <PortfolioPolicyEditor
              value={doc.portfolio}
              onChange={(portfolio) => setDoc({ ...doc, portfolio })}
              factors={factors}
              formulaIds={formulaIds}
            />

            <Group>
              <Button variant="default" onClick={handleValidate}>
                저장 전 검증
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
              <Button
                variant="light"
                color="teal"
                onClick={() => handleActivate(true)}
                disabled={!selectedId}
              >
                활성화
              </Button>
              <Button
                variant="light"
                color="gray"
                onClick={() => handleActivate(false)}
                disabled={!selectedId}
              >
                비활성화
              </Button>
              <Button
                variant="subtle"
                leftSection={<IconDownload size={14} />}
                onClick={handleExport}
                disabled={!selectedId}
              >
                Export
              </Button>
            </Group>

            <Group align="flex-end">
              <TextInput
                label="템플릿 id"
                placeholder="template id"
                value={saveAsTemplateId}
                onChange={(e) => setSaveAsTemplateId(e.currentTarget.value)}
                disabled={!selectedId}
                size="sm"
              />
              <Button
                variant="subtle"
                size="sm"
                onClick={handleSaveAsTemplate}
                disabled={!selectedId}
              >
                템플릿으로 저장
              </Button>
              {activeState != null && (
                <Badge color={activeState ? 'teal' : 'gray'}>
                  {activeState ? '활성' : '비활성'}
                </Badge>
              )}
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
          </Stack>
        </Paper>
      )}
    </Group>
  )
}

/** 포트폴리오 정책(P1) — 미설정이면 기존 종목별 독립 백테스트가 유지된다. */
function PortfolioPolicyEditor({
  value,
  onChange,
  factors,
  formulaIds,
}: {
  value: PortfolioJSON | null
  onChange: (v: PortfolioJSON | null) => void
  factors: FactorOption[]
  formulaIds: string[]
}) {
  const enabled = value !== null
  const policy = value ?? DEFAULT_PORTFOLIO
  const update = (patch: Partial<PortfolioJSON>) => onChange({ ...policy, ...patch })
  // 지역 변수로 받아야 판별 유니온 좁히기가 유지된다(policy.ranking?.kind로는 좁혀지지 않음).
  const ranking = policy.ranking
  const rankingKind = ranking?.kind ?? 'none'
  const rankingFactor =
    ranking?.kind === 'factor' ? factors.find((f) => f.id === ranking.factor_id) : undefined

  const setRankingKind = (kind: string | null) => {
    if (kind === 'factor') {
      const first = factors[0]
      update({
        ranking: {
          kind: 'factor',
          factor_id: first?.id ?? '',
          column: first?.output[0] ?? '',
          params: {},
          descending: true,
        },
      })
    } else if (kind === 'formula') {
      update({
        ranking: { kind: 'formula', formula_id: formulaIds[0] ?? '', descending: true },
      })
    } else {
      update({ ranking: null })
    }
  }

  return (
    <div>
      <Group gap="xs" mb="xs">
        <Title order={5}>포트폴리오(portfolio)</Title>
        <Checkbox
          label="자본 공유 포트폴리오 모드 사용"
          checked={enabled}
          onChange={(e) => onChange(e.currentTarget.checked ? DEFAULT_PORTFOLIO : null)}
        />
      </Group>
      {!enabled ? (
        <Text size="xs" c="dimmed">
          미설정 시 종목별로 독립 백테스트를 수행합니다(각 종목이 자본 100%를 쓴다고 가정).
        </Text>
      ) : (
        <Stack gap="xs">
          <Group gap="xs" align="flex-end" wrap="wrap">
            <NumberInput
              label="최대 보유 종목"
              min={1}
              value={policy.max_positions}
              onChange={(v) => update({ max_positions: Math.max(1, Number(v) || 1) })}
              w={130}
            />
            <Select
              label="리밸런싱 주기"
              data={[
                { value: 'weekly', label: '주간' },
                { value: 'monthly', label: '월간' },
                { value: 'quarterly', label: '분기' },
              ]}
              value={policy.rebalance}
              onChange={(v) => update({ rebalance: (v as PortfolioJSON['rebalance']) ?? 'monthly' })}
              w={130}
            />
            <Select
              label="비중 배분"
              data={[{ value: 'equal_weight', label: '균등 분배' }]}
              value={policy.sizing}
              onChange={() => undefined}
              w={130}
            />
            <NumberInput
              label="초기 자본(원)"
              min={1}
              step={1_000_000}
              thousandSeparator=","
              value={policy.initial_cash}
              onChange={(v) => update({ initial_cash: Number(v) || 1 })}
              w={180}
            />
          </Group>

          <Group gap="xs" align="flex-end" wrap="wrap">
            <Select
              label="종목 선별 기준(후보가 최대 보유 수보다 많을 때)"
              data={[
                { value: 'none', label: '없음(종목코드 오름차순)' },
                { value: 'factor', label: '팩터 값' },
                { value: 'formula', label: '공식 값' },
              ]}
              value={rankingKind}
              onChange={setRankingKind}
              w={280}
            />
            {ranking?.kind === 'factor' && (
              <>
                <Select
                  label="팩터"
                  data={factors.map((f) => ({ value: f.id, label: `${f.display_name}(${f.id})` }))}
                  value={ranking.factor_id}
                  onChange={(id) => {
                    const picked = factors.find((f) => f.id === id)
                    update({
                      ranking: {
                        kind: 'factor',
                        factor_id: id ?? '',
                        column: picked?.output[0] ?? '',
                        params: {},
                        descending: ranking.descending,
                      },
                    })
                  }}
                  w={200}
                />
                <Select
                  label="컬럼"
                  data={rankingFactor?.output ?? []}
                  value={ranking.column}
                  onChange={(column) => update({ ranking: { ...ranking, column: column ?? '' } })}
                  w={130}
                />
                {rankingFactor?.params.map((p) => (
                  <NumberInput
                    key={p.name}
                    label={p.name}
                    value={ranking.params[p.name] ?? p.default}
                    onChange={(v) =>
                      update({
                        ranking: {
                          ...ranking,
                          params: { ...ranking.params, [p.name]: Number(v) || 0 },
                        },
                      })
                    }
                    w={90}
                  />
                ))}
              </>
            )}
            {ranking?.kind === 'formula' && (
              <Select
                label="공식"
                data={formulaIds}
                value={ranking.formula_id}
                onChange={(formula_id) =>
                  update({ ranking: { ...ranking, formula_id: formula_id ?? '' } })
                }
                w={200}
              />
            )}
            {ranking && (
              <Select
                label="정렬"
                data={[
                  { value: 'desc', label: '값이 큰 순' },
                  { value: 'asc', label: '값이 작은 순' },
                ]}
                value={ranking.descending ? 'desc' : 'asc'}
                onChange={(v) => update({ ranking: { ...ranking, descending: v !== 'asc' } })}
                w={140}
              />
            )}
          </Group>
          {ranking?.kind === 'factor' && (
            <Text size="xs" c="dimmed">
              선별에 쓰는 팩터도 위 팩터 참조(factor_refs)에 선언되어 있어야 저장됩니다.
            </Text>
          )}
        </Stack>
      )}
    </div>
  )
}

function FactorRefsEditor({
  value,
  onChange,
  factors,
}: {
  value: FactorRefJSON[]
  onChange: (v: FactorRefJSON[]) => void
  factors: FactorOption[]
}) {
  const updateRow = (i: number, row: FactorRefJSON) => {
    const next = [...value]
    next[i] = row
    onChange(next)
  }
  const removeRow = (i: number) => onChange(value.filter((_, idx) => idx !== i))
  const addRow = () => {
    const first = factors[0]
    onChange([...value, { factor_id: first?.id ?? '', params: {} }])
  }

  return (
    <div>
      <Title order={5} mb="xs">
        팩터 참조(factor_refs)
      </Title>
      <Stack gap="xs">
        {value.map((ref, i) => {
          const selected = factors.find((f) => f.id === ref.factor_id)
          return (
            // eslint-disable-next-line react/no-array-index-key
            <Group key={i} gap="xs" wrap="nowrap" align="flex-end">
              <Select
                label="팩터"
                data={factors.map((f) => ({ value: f.id, label: `${f.display_name}(${f.id})` }))}
                value={ref.factor_id}
                onChange={(id) => updateRow(i, { factor_id: id ?? '', params: {} })}
                w={200}
              />
              {selected?.params.map((p) => (
                <NumberInput
                  key={p.name}
                  label={p.name}
                  value={ref.params[p.name] ?? p.default}
                  onChange={(v) =>
                    updateRow(i, { ...ref, params: { ...ref.params, [p.name]: Number(v) || 0 } })
                  }
                  w={80}
                />
              ))}
              <ActionIcon color="red" variant="subtle" onClick={() => removeRow(i)}>
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          )
        })}
        <Button
          variant="light"
          size="xs"
          leftSection={<IconPlus size={14} />}
          onClick={addRow}
          style={{ alignSelf: 'flex-start' }}
        >
          팩터 추가
        </Button>
      </Stack>
    </div>
  )
}

function RuleBindingEditor({
  value,
  onChange,
  ruleIds,
}: {
  value: RuleBindingJSON | null
  onChange: (v: RuleBindingJSON | null) => void
  ruleIds: string[]
}) {
  const isDraft = value === null

  return (
    <div>
      <Title order={5} mb="xs">
        규칙 바인딩(rule)
      </Title>
      <Stack gap="xs">
        <Checkbox
          checked={isDraft}
          onChange={(e) =>
            onChange(e.currentTarget.checked ? null : { roles: { entry: [], exit: [] } })
          }
          label="초안(규칙 미지정 — 활성화/백테스트 불가)"
        />

        {!isDraft && value && (
          <>
            <MultiSelect
              label="진입(entry, 최소 1개 필수)"
              data={ruleIds}
              value={value.roles.entry}
              onChange={(entry) => onChange({ roles: { ...value.roles, entry } })}
            />
            <MultiSelect
              label="청산(exit, 생략 가능)"
              data={ruleIds}
              value={value.roles.exit}
              onChange={(exit) => onChange({ roles: { ...value.roles, exit } })}
            />
          </>
        )}
        {isDraft && (
          <Text size="xs" c="dimmed">
            초안 상태에서는 활성화·백테스트를 실행할 수 없습니다.
          </Text>
        )}
      </Stack>
    </div>
  )
}
