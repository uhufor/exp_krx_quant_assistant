import { Group, Paper, Select, Stack, Text } from '@mantine/core'
import { OperandEditor } from './OperandEditor'
import type { BinaryOpJSON, ExprJSON, FactorOption, UnaryOpJSON } from './types'
import { defaultOperand, isOperand } from './types'

type FormulaTreeEditorProps = {
  value: ExprJSON
  onChange: (v: ExprJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
  depth?: number
}

const NODE_TYPE_DATA = [
  { value: 'leaf', label: '값(상수/팩터/공식)' },
  { value: 'binary', label: '이항 연산(+,-,*,/)' },
  { value: 'unary', label: '단항 연산(음수)' },
]

const DEPTH_COLORS = ['blue', 'grape', 'teal', 'orange'] as const

/** 공식(Formula) 표현식 트리 재귀 편집기(PRD CRUD — JSON 직접 입력 없이 UI로 생성). */
export function FormulaTreeEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth = 0,
}: FormulaTreeEditorProps) {
  const wrapKind = isOperand(value) ? 'leaf' : value.node
  const accent = DEPTH_COLORS[depth % DEPTH_COLORS.length]

  const handleTypeChange = (newType: string | null) => {
    if (newType === 'binary') {
      onChange({
        node: 'binary',
        op: '+',
        left: defaultOperand(factors),
        right: defaultOperand(factors),
      })
    } else if (newType === 'unary') {
      onChange({ node: 'unary', op: 'neg', operand: defaultOperand(factors) })
    } else {
      onChange(defaultOperand(factors))
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
          value={wrapKind}
          onChange={handleTypeChange}
          w={220}
        />

        {isOperand(value) && (
          <OperandEditor
            value={value}
            onChange={onChange}
            factors={factors}
            formulaIds={formulaIds}
          />
        )}

        {!isOperand(value) && value.node === 'binary' && (
          <BinaryEditor
            value={value}
            onChange={onChange}
            factors={factors}
            formulaIds={formulaIds}
            depth={depth}
          />
        )}

        {!isOperand(value) && value.node === 'unary' && (
          <UnaryEditor
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

function BinaryEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth,
}: {
  value: BinaryOpJSON
  onChange: (v: ExprJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
  depth: number
}) {
  return (
    <Stack gap={4} pl="md">
      <Select
        label="연산자"
        data={['+', '-', '*', '/']}
        value={value.op}
        onChange={(op) => onChange({ ...value, op: (op ?? '+') as BinaryOpJSON['op'] })}
        w={80}
      />
      <Group gap={4}>
        <Text size="xs" c="dimmed" w={40}>
          좌항
        </Text>
        <div style={{ flex: 1 }}>
          <FormulaTreeEditor
            value={value.left}
            onChange={(left) => onChange({ ...value, left })}
            factors={factors}
            formulaIds={formulaIds}
            depth={depth + 1}
          />
        </div>
      </Group>
      <Group gap={4}>
        <Text size="xs" c="dimmed" w={40}>
          우항
        </Text>
        <div style={{ flex: 1 }}>
          <FormulaTreeEditor
            value={value.right}
            onChange={(right) => onChange({ ...value, right })}
            factors={factors}
            formulaIds={formulaIds}
            depth={depth + 1}
          />
        </div>
      </Group>
    </Stack>
  )
}

function UnaryEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth,
}: {
  value: UnaryOpJSON
  onChange: (v: ExprJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
  depth: number
}) {
  return (
    <Stack gap={4} pl="md">
      <Text size="xs" c="dimmed">
        neg(피연산자 부호 반전)
      </Text>
      <FormulaTreeEditor
        value={value.operand}
        onChange={(operand) => onChange({ ...value, operand })}
        factors={factors}
        formulaIds={formulaIds}
        depth={depth + 1}
      />
    </Stack>
  )
}
