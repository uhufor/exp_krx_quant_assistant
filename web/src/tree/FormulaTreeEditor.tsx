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

/** 공식(Formula) 표현식 트리 재귀 편집기(PRD CRUD — JSON 직접 입력 없이 UI로 생성). */
export function FormulaTreeEditor({
  value,
  onChange,
  factors,
  formulaIds,
  depth = 0,
}: FormulaTreeEditorProps) {
  const wrapKind = isOperand(value) ? 'leaf' : value.node

  const handleTypeChange = (newType: string) => {
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
        <option value="leaf">값(상수/팩터/공식)</option>
        <option value="binary">이항 연산(+,-,*,/)</option>
        <option value="unary">단항 연산(음수)</option>
      </select>

      {isOperand(value) && (
        <OperandEditor value={value} onChange={onChange} factors={factors} formulaIds={formulaIds} />
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
    </div>
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
    <div style={{ marginLeft: '1rem' }}>
      <select
        value={value.op}
        onChange={(e) => onChange({ ...value, op: e.target.value as BinaryOpJSON['op'] })}
      >
        {(['+', '-', '*', '/'] as const).map((op) => (
          <option key={op} value={op}>
            {op}
          </option>
        ))}
      </select>
      <div>좌항</div>
      <FormulaTreeEditor
        value={value.left}
        onChange={(left) => onChange({ ...value, left })}
        factors={factors}
        formulaIds={formulaIds}
        depth={depth + 1}
      />
      <div>우항</div>
      <FormulaTreeEditor
        value={value.right}
        onChange={(right) => onChange({ ...value, right })}
        factors={factors}
        formulaIds={formulaIds}
        depth={depth + 1}
      />
    </div>
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
    <div style={{ marginLeft: '1rem' }}>
      <span>neg(피연산자 부호 반전)</span>
      <FormulaTreeEditor
        value={value.operand}
        onChange={(operand) => onChange({ ...value, operand })}
        factors={factors}
        formulaIds={formulaIds}
        depth={depth + 1}
      />
    </div>
  )
}
