import { ActionIcon, Button, Group, Paper, Select, Stack } from '@mantine/core'
import { IconPlus, IconX } from '@tabler/icons-react'
import { OperandEditor } from './OperandEditor'
import type { CompositionJSON, FactorOption, PredicateJSON, RuleNodeJSON } from './types'
import { PREDICATE_OPS, defaultPredicate } from './types'

type RuleTreeEditorProps = {
  value: RuleNodeJSON
  onChange: (v: RuleNodeJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
  depth?: number
}

const NODE_TYPE_DATA = [
  { value: 'predicate', label: '조건(비교/크로스)' },
  { value: 'AND', label: 'AND(모두 만족)' },
  { value: 'OR', label: 'OR(하나 이상 만족)' },
  { value: 'NOT', label: 'NOT(반전)' },
]

const DEPTH_COLORS = ['indigo', 'pink', 'cyan', 'lime'] as const

/** 규칙(Rule) 조건 트리 재귀 편집기(Predicate 비교/크로스, Composition AND/OR/NOT). */
export function RuleTreeEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth = 0,
}: RuleTreeEditorProps) {
  const accent = DEPTH_COLORS[depth % DEPTH_COLORS.length]

  const handleTypeChange = (newType: string | null) => {
    if (newType === 'predicate') {
      onChange(defaultPredicate(factors))
    } else if (newType) {
      const operands =
        newType === 'NOT'
          ? [defaultPredicate(factors)]
          : [defaultPredicate(factors), defaultPredicate(factors)]
      onChange({ node: 'composition', op: newType as CompositionJSON['op'], operands })
    }
  }

  const wrapKind = value.node === 'predicate' ? 'predicate' : value.op

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
          value={wrapKind}
          onChange={handleTypeChange}
          w={200}
        />

        {value.node === 'predicate' && (
          <PredicateEditor
            value={value}
            onChange={onChange}
            factors={factors}
            formulaIds={formulaIds}
          />
        )}

        {value.node === 'composition' && (
          <CompositionEditor
            value={value}
            onChange={onChange}
            factors={factors}
            formulaIds={formulaIds}
            depth={depth}
          />
        )}
      </Stack>
    </Paper>
  )
}

function PredicateEditor({
  value,
  onChange,
  factors,
  formulaIds,
}: {
  value: PredicateJSON
  onChange: (v: RuleNodeJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
}) {
  return (
    <Group gap="xs" wrap="wrap" align="flex-end">
      <OperandEditor
        value={value.left}
        onChange={(left) => onChange({ ...value, left })}
        factors={factors}
        formulaIds={formulaIds}
      />
      <Select
        label="연산자"
        data={[...PREDICATE_OPS]}
        value={value.operator}
        onChange={(op) =>
          onChange({ ...value, operator: (op ?? '>') as PredicateJSON['operator'] })
        }
        w={130}
      />
      <OperandEditor
        value={value.right}
        onChange={(right) => onChange({ ...value, right })}
        factors={factors}
        formulaIds={formulaIds}
      />
    </Group>
  )
}

function CompositionEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth,
}: {
  value: CompositionJSON
  onChange: (v: RuleNodeJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
  depth: number
}) {
  const minOperands = value.op === 'NOT' ? 1 : 2
  const canRemove = value.op !== 'NOT' && value.operands.length > minOperands
  const canAdd = value.op !== 'NOT'

  const updateOperand = (index: number, node: RuleNodeJSON) => {
    const next = [...value.operands]
    next[index] = node
    onChange({ ...value, operands: next })
  }

  const removeOperand = (index: number) => {
    onChange({ ...value, operands: value.operands.filter((_, i) => i !== index) })
  }

  const addOperand = () => {
    onChange({ ...value, operands: [...value.operands, defaultPredicate(factors)] })
  }

  return (
    <Stack gap="xs" pl="md">
      {value.operands.map((operand, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <Group key={i} align="flex-start" gap={4} wrap="nowrap">
          <div style={{ flex: 1 }}>
            <RuleTreeEditor
              value={operand}
              onChange={(node) => updateOperand(i, node)}
              factors={factors}
              formulaIds={formulaIds}
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
