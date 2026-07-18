import type { FactorOption, OperandJSON } from './types'

type OperandEditorProps = {
  value: OperandJSON
  onChange: (v: OperandJSON) => void
  factors: FactorOption[]
  formulaIds: string[]
}

/** 리프 피연산자(상수/팩터/공식참조) 편집 — Formula 표현식·Rule Predicate 양쪽이 공유. */
export function OperandEditor({ value, onChange, factors, formulaIds }: OperandEditorProps) {
  const handleKindChange = (kind: string) => {
    if (kind === 'constant') onChange({ kind: 'constant', value: 0 })
    else if (kind === 'factor') {
      const f = factors[0]
      onChange({ kind: 'factor', factor_id: f?.id ?? '', column: f?.output[0] ?? '', params: {} })
    } else if (kind === 'formula') {
      onChange({ kind: 'formula', formula_id: formulaIds[0] ?? '', column: 'value' })
    }
  }

  return (
    <span style={{ display: 'inline-flex', gap: '0.25rem', alignItems: 'center' }}>
      <select value={value.kind} onChange={(e) => handleKindChange(e.target.value)}>
        <option value="constant">상수</option>
        <option value="factor">팩터</option>
        <option value="formula">공식 참조</option>
      </select>

      {value.kind === 'constant' && (
        <input
          type="number"
          value={value.value}
          onChange={(e) => onChange({ kind: 'constant', value: Number(e.target.value) })}
          style={{ width: '6rem' }}
        />
      )}

      {value.kind === 'factor' && (() => {
        const v = value
        const selected = factors.find((f) => f.id === v.factor_id)
        return (
          <>
            <select
              value={v.factor_id}
              onChange={(e) => {
                const f = factors.find((ff) => ff.id === e.target.value)
                onChange({
                  kind: 'factor',
                  factor_id: e.target.value,
                  column: f?.output[0] ?? '',
                  params: {},
                })
              }}
            >
              {factors.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.display_name}({f.id})
                </option>
              ))}
            </select>
            <select value={v.column} onChange={(e) => onChange({ ...v, column: e.target.value })}>
              {(selected?.output ?? [v.column]).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            {selected?.params.map((p) => (
              <label key={p.name} style={{ fontSize: '0.85em' }}>
                {p.name}
                <input
                  type="number"
                  value={v.params[p.name] ?? p.default}
                  min={p.min ?? undefined}
                  max={p.max ?? undefined}
                  onChange={(e) =>
                    onChange({ ...v, params: { ...v.params, [p.name]: Number(e.target.value) } })
                  }
                  style={{ width: '4rem' }}
                />
              </label>
            ))}
          </>
        )
      })()}

      {value.kind === 'formula' && (
        <select
          value={value.formula_id}
          onChange={(e) => onChange({ kind: 'formula', formula_id: e.target.value, column: 'value' })}
        >
          <option value="">(선택)</option>
          {formulaIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      )}
    </span>
  )
}
