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

/** 규칙(Rule) 조건 트리 재귀 편집기(Predicate 비교/크로스, Composition AND/OR/NOT). */
export function RuleTreeEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth = 0,
}: RuleTreeEditorProps) {
  const handleTypeChange = (newType: string) => {
    if (newType === 'predicate') {
      onChange(defaultPredicate(factors))
    } else {
      const operands =
        newType === 'NOT'
          ? [defaultPredicate(factors)]
          : [defaultPredicate(factors), defaultPredicate(factors)]
      onChange({ node: 'composition', op: newType as CompositionJSON['op'], operands })
    }
  }

  const wrapKind = value.node === 'predicate' ? 'predicate' : value.op

  return (
    <div
      style={{
        border: '1px solid #ddd',
        borderRadius: 4,
        padding: '0.4rem',
        marginTop: '0.25rem',
        background: depth % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.02)',
      }}
    >
      <select value={wrapKind} onChange={(e) => handleTypeChange(e.target.value)}>
        <option value="predicate">조건(비교/크로스)</option>
        <option value="AND">AND(모두 만족)</option>
        <option value="OR">OR(하나 이상 만족)</option>
        <option value="NOT">NOT(반전)</option>
      </select>

      {value.node === 'predicate' && (
        <PredicateEditor value={value} onChange={onChange} factors={factors} formulaIds={formulaIds} />
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
    </div>
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
    <div style={{ marginLeft: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
      <OperandEditor
        value={value.left}
        onChange={(left) => onChange({ ...value, left })}
        factors={factors}
        formulaIds={formulaIds}
      />
      <select
        value={value.operator}
        onChange={(e) =>
          onChange({ ...value, operator: e.target.value as PredicateJSON['operator'] })
        }
      >
        {PREDICATE_OPS.map((op) => (
          <option key={op} value={op}>
            {op}
          </option>
        ))}
      </select>
      <OperandEditor
        value={value.right}
        onChange={(right) => onChange({ ...value, right })}
        factors={factors}
        formulaIds={formulaIds}
      />
    </div>
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
    <div style={{ marginLeft: '1rem' }}>
      {value.operands.map((operand, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.25rem' }}>
          <RuleTreeEditor
            value={operand}
            onChange={(node) => updateOperand(i, node)}
            factors={factors}
            formulaIds={formulaIds}
            depth={depth + 1}
          />
          {canRemove && (
            <button type="button" onClick={() => removeOperand(i)}>
              제거
            </button>
          )}
        </div>
      ))}
      {canAdd && (
        <button type="button" onClick={addOperand}>
          + 조건 추가
        </button>
      )}
    </div>
  )
}
