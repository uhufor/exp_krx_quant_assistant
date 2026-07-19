import { Group, NumberInput, Select } from '@mantine/core'
import type { FactorOption, OperandJSON } from './types'

type OperandEditorProps = {
  value: OperandJSON
  onChange: (v: OperandJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
}

const KIND_DATA = [
  { value: 'constant', label: '상수' },
  { value: 'factor', label: '팩터' },
  { value: 'formula', label: '공식 참조' },
]

/** 리프 피연산자(상수/팩터/공식참조) 편집 — Formula 표현식·Rule Predicate 양쪽이 공유. */
export function OperandEditor({ value, onChange, factors, formulaIds }: OperandEditorProps) {
  const handleKindChange = (kind: string | null) => {
    if (kind === 'constant') onChange({ kind: 'constant', value: 0 })
    else if (kind === 'factor') {
      const f = factors[0]
      onChange({ kind: 'factor', factor_id: f?.id ?? '', column: f?.output[0] ?? '', params: {} })
    } else if (kind === 'formula') {
      onChange({ kind: 'formula', formula_id: formulaIds[0] ?? '', column: 'value' })
    }
  }

  return (
    <Group gap="xs" wrap="nowrap" align="flex-end">
      <Select label="유형" data={KIND_DATA} value={value.kind} onChange={handleKindChange} w={110} />

      {value.kind === 'constant' && (
        <NumberInput
          label="값"
          value={value.value}
          onChange={(v) => onChange({ kind: 'constant', value: Number(v) || 0 })}
          w={100}
        />
      )}

      {value.kind === 'factor' && (() => {
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

      {value.kind === 'formula' && (
        <Select
          label="공식"
          placeholder="공식 선택"
          data={formulaIds}
          value={value.formula_id || null}
          onChange={(id) => onChange({ kind: 'formula', formula_id: id ?? '', column: 'value' })}
          w={170}
        />
      )}
    </Group>
  )
}
