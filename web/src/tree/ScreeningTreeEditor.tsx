import {
  ActionIcon,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core'
import { IconPlus, IconX } from '@tabler/icons-react'
import {
  SCREENING_PREDICATE_OPS,
  SCREENING_RANK_COLUMNS,
  SCREENING_RANK_METRICS,
  defaultScreeningPredicate,
  nextCompositionOperands,
} from './screeningTypes'
import type {
  ScreeningCompositionJSON,
  ScreeningNodeJSON,
  ScreeningOperandJSON,
  ScreeningPredicateJSON,
  ScreeningRankPredicateJSON,
  ScreeningWindowPredicateJSON,
} from './screeningTypes'
import type { FactorOption } from './types'

type ScreeningTreeEditorProps = {
  value: ScreeningNodeJSON
  onChange: (v: ScreeningNodeJSON) => void
  factors: FactorOption[]
  depth?: number
}

const NODE_TYPE_DATA = [
  { value: 'predicate', label: '조건(비교/크로스)' },
  { value: 'AND', label: 'AND(모두 만족)' },
  { value: 'OR', label: 'OR(하나 이상 만족)' },
  { value: 'NOT', label: 'NOT(반전)' },
  { value: 'window_predicate', label: '기간 조건(최근 N봉 이내)' },
  { value: 'rank_predicate', label: '순위 조건(Top-N)' },
]

const DEPTH_COLORS = ['indigo', 'pink', 'cyan', 'lime'] as const

const wrapKindOf = (value: ScreeningNodeJSON): string =>
  value.node === 'composition' ? value.op : value.node

/** 스크리닝(Screening) 조건 트리 재귀 편집기 — Predicate/Composition(AND·OR·NOT) +
 * 신규 노드 2종(WindowPredicate/RankPredicate). RuleTreeEditor 패턴을 참고했으나
 * screening 전용 타입(screeningTypes.ts)만 사용하는 독립 구현이다(INV-2). */
export function ScreeningTreeEditor({
  value,
  onChange,
  factors,
  depth = 0,
}: ScreeningTreeEditorProps) {
  const accent = DEPTH_COLORS[depth % DEPTH_COLORS.length]

  const handleTypeChange = (newType: string | null) => {
    if (newType === 'predicate') {
      onChange(defaultScreeningPredicate(factors))
    } else if (newType === 'AND' || newType === 'OR' || newType === 'NOT') {
      // AND/OR/NOT 사이 전환은 같은 composition 형태이므로 기존 하위 트리(operands)를
      // 보존한다(버그 리포트 I5) — nextCompositionOperands 참고.
      const operands = nextCompositionOperands(newType, value, factors)
      onChange({ node: 'composition', op: newType, operands })
    } else if (newType === 'window_predicate') {
      onChange({
        node: 'window_predicate',
        inner: defaultScreeningPredicate(factors),
        n_bars: 5,
        include_current_bar: true,
      })
    } else if (newType === 'rank_predicate') {
      const first = factors[0]
      onChange({
        node: 'rank_predicate',
        factor_id: first?.id ?? 'trading_value',
        column: 'trading_value',
        rank_metric: 'desc',
        top_n: 10,
        params: {},
      })
    }
  }

  return (
    <Paper
      withBorder
      p="sm"
      radius="sm"
      style={{ borderLeft: `3px solid var(--mantine-color-${accent}-5)` }}
    >
      <Stack gap="xs">
        <Select
          label="노드 유형"
          data={NODE_TYPE_DATA}
          value={wrapKindOf(value)}
          onChange={handleTypeChange}
          w={220}
        />

        {value.node === 'predicate' && (
          <ScreeningPredicateEditor value={value} onChange={onChange} factors={factors} />
        )}

        {value.node === 'composition' && (
          <ScreeningCompositionEditor
            value={value}
            onChange={onChange}
            factors={factors}
            depth={depth}
          />
        )}

        {value.node === 'window_predicate' && (
          <ScreeningWindowPredicateEditor value={value} onChange={onChange} factors={factors} />
        )}

        {value.node === 'rank_predicate' && (
          <ScreeningRankPredicateEditor value={value} onChange={onChange} factors={factors} />
        )}
      </Stack>
    </Paper>
  )
}

const OPERAND_KIND_DATA = [
  { value: 'constant', label: '상수' },
  { value: 'factor', label: '팩터' },
]

/** 리프 피연산자(상수/팩터) 편집 — formula 종류는 노출하지 않는다(screeningTypes.ts 주석 참고,
 * screening/service.py가 FormulaOperand를 항상 검증 오류로 거부하기 때문). */
function ScreeningOperandEditor({
  value,
  onChange,
  factors,
}: {
  value: ScreeningOperandJSON
  onChange: (v: ScreeningOperandJSON) => void
  factors: FactorOption[]
}) {
  const handleKindChange = (kind: string | null) => {
    if (kind === 'constant') onChange({ kind: 'constant', value: 0 })
    else if (kind === 'factor') {
      const f = factors[0]
      onChange({ kind: 'factor', factor_id: f?.id ?? '', column: f?.output[0] ?? '', params: {} })
    }
  }

  return (
    <Group gap="xs" wrap="nowrap" align="flex-end">
      <Select
        label="유형"
        data={OPERAND_KIND_DATA}
        value={value.kind}
        onChange={handleKindChange}
        w={100}
      />

      {value.kind === 'constant' && (
        <NumberInput
          label="값"
          value={value.value}
          onChange={(v) => onChange({ kind: 'constant', value: Number(v) || 0 })}
          w={100}
        />
      )}

      {value.kind === 'factor' &&
        (() => {
          const v = value
          const selected = factors.find((f) => f.id === v.factor_id)
          return (
            <Group gap="xs" wrap="nowrap" align="flex-end">
              <Select
                label="팩터"
                data={factors.map((f) => ({ value: f.id, label: `${f.display_name}(${f.id})` }))}
                value={v.factor_id}
                onChange={(id) => {
                  const f = factors.find((ff) => ff.id === id)
                  onChange({
                    kind: 'factor',
                    factor_id: id ?? '',
                    column: f?.output[0] ?? '',
                    params: {},
                  })
                }}
                w={170}
              />
              <Select
                label="컬럼"
                data={selected?.output ?? [v.column]}
                value={v.column}
                onChange={(col) => onChange({ ...v, column: col ?? v.column })}
                w={100}
              />
              {selected?.params.map((p) => (
                <NumberInput
                  key={p.name}
                  label={p.name}
                  value={v.params[p.name] ?? p.default}
                  min={p.min ?? undefined}
                  max={p.max ?? undefined}
                  onChange={(val) =>
                    onChange({ ...v, params: { ...v.params, [p.name]: Number(val) || 0 } })
                  }
                  w={80}
                />
              ))}
            </Group>
          )
        })()}
    </Group>
  )
}

function ScreeningPredicateEditor({
  value,
  onChange,
  factors,
}: {
  value: ScreeningPredicateJSON
  onChange: (v: ScreeningNodeJSON) => void
  factors: FactorOption[]
}) {
  return (
    <Group gap="xs" wrap="wrap" align="flex-end">
      <ScreeningOperandEditor
        value={value.left}
        onChange={(left) => onChange({ ...value, left })}
        factors={factors}
      />
      <Select
        label="연산자"
        data={[...SCREENING_PREDICATE_OPS]}
        value={value.operator}
        onChange={(op) =>
          onChange({ ...value, operator: (op ?? '>') as ScreeningPredicateJSON['operator'] })
        }
        w={130}
      />
      <ScreeningOperandEditor
        value={value.right}
        onChange={(right) => onChange({ ...value, right })}
        factors={factors}
      />
    </Group>
  )
}

function ScreeningCompositionEditor({
  value,
  onChange,
  factors,
  depth,
}: {
  value: ScreeningCompositionJSON
  onChange: (v: ScreeningNodeJSON) => void
  factors: FactorOption[]
  depth: number
}) {
  const minOperands = value.op === 'NOT' ? 1 : 2
  const canRemove = value.op !== 'NOT' && value.operands.length > minOperands
  const canAdd = value.op !== 'NOT'

  const updateOperand = (index: number, node: ScreeningNodeJSON) => {
    const next = [...value.operands]
    next[index] = node
    onChange({ ...value, operands: next })
  }

  const removeOperand = (index: number) => {
    onChange({ ...value, operands: value.operands.filter((_, i) => i !== index) })
  }

  const addOperand = () => {
    onChange({ ...value, operands: [...value.operands, defaultScreeningPredicate(factors)] })
  }

  return (
    <Stack gap="xs" pl="md">
      {value.operands.map((operand, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <Group key={i} align="flex-start" gap={4} wrap="nowrap">
          <div style={{ flex: 1 }}>
            <ScreeningTreeEditor
              value={operand}
              onChange={(node) => updateOperand(i, node)}
              factors={factors}
              depth={depth + 1}
            />
          </div>
          {canRemove && (
            <ActionIcon color="red" variant="subtle" onClick={() => removeOperand(i)} mt={6}>
              <IconX size={16} />
            </ActionIcon>
          )}
        </Group>
      ))}
      {canAdd && (
        <Button
          variant="light"
          size="xs"
          leftSection={<IconPlus size={14} />}
          onClick={addOperand}
          style={{ alignSelf: 'flex-start' }}
        >
          조건 추가
        </Button>
      )}
    </Stack>
  )
}

function ScreeningWindowPredicateEditor({
  value,
  onChange,
  factors,
}: {
  value: ScreeningWindowPredicateJSON
  onChange: (v: ScreeningNodeJSON) => void
  factors: FactorOption[]
}) {
  return (
    <Stack gap="xs">
      <Group gap="xs" align="flex-end">
        <NumberInput
          label="n_bars(최근 봉수)"
          value={value.n_bars}
          min={0}
          onChange={(v) => onChange({ ...value, n_bars: Math.max(0, Math.trunc(Number(v) || 0)) })}
          w={140}
        />
        <Checkbox
          label="현재봉 포함(include_current_bar)"
          checked={value.include_current_bar}
          onChange={(e) => onChange({ ...value, include_current_bar: e.currentTarget.checked })}
          mb={6}
        />
      </Group>
      <Text size="xs" c="dimmed">
        내부 조건이 최근 n_bars봉 중 한 번이라도 성립하면 통과합니다.
      </Text>
      <div style={{ paddingLeft: 12 }}>
        <ScreeningTreeEditor
          value={value.inner}
          onChange={(inner) => onChange({ ...value, inner })}
          factors={factors}
          depth={1}
        />
      </div>
    </Stack>
  )
}

function ScreeningRankPredicateEditor({
  value,
  onChange,
  factors,
}: {
  value: ScreeningRankPredicateJSON
  onChange: (v: ScreeningNodeJSON) => void
  factors: FactorOption[]
}) {
  return (
    <Stack gap="xs">
      <Group gap="xs" align="flex-end" wrap="wrap">
        <Select
          label="factor_id(참조용, lookback 추정에만 사용)"
          data={factors.map((f) => ({ value: f.id, label: `${f.display_name}(${f.id})` }))}
          value={value.factor_id || null}
          onChange={(id) => onChange({ ...value, factor_id: id ?? value.factor_id })}
          searchable
          w={220}
        />
        <Select
          label="column(시장 스냅샷 컬럼)"
          data={[...SCREENING_RANK_COLUMNS]}
          value={value.column}
          onChange={(col) =>
            onChange({
              ...value,
              column: (col ?? value.column) as ScreeningRankPredicateJSON['column'],
            })
          }
          w={160}
        />
        <Select
          label="순위 기준"
          data={[
            { value: 'desc', label: '내림차순(desc, 상위값)' },
            { value: 'asc', label: '오름차순(asc, 하위값)' },
          ]}
          value={value.rank_metric}
          onChange={(m) =>
            onChange({
              ...value,
              rank_metric: (m ?? value.rank_metric) as (typeof SCREENING_RANK_METRICS)[number],
            })
          }
          w={200}
        />
        <NumberInput
          label="top_n"
          value={value.top_n}
          min={1}
          onChange={(v) => onChange({ ...value, top_n: Math.max(1, Math.trunc(Number(v) || 1)) })}
          w={100}
        />
      </Group>
      <Tooltip label="column은 팩터 근사치가 아니라 시장 스냅샷(close/volume/trading_value)에서 직접 계산됩니다.">
        <Text size="xs" c="dimmed" style={{ cursor: 'help', width: 'fit-content' }}>
          상위 top_n 종목만 통과하는 횡단면 순위 조건
        </Text>
      </Tooltip>
    </Stack>
  )
}
