// Formula/Rule 트리 JSON 형상 — 백엔드 formula/definition.py·rule/definition.py의
// to_dict()/from_dict()와 1:1 대응(신규 스키마 발명 없음, 기존 계약을 TS로 미러링).

export type FactorParamSpec = {
  name: string
  type: string
  default: number
  description: string
  min: number | null
  max: number | null
  choices: number[] | null
}

export type FactorOption = {
  id: string
  display_name: string
  category: string
  output: string[]
  params: FactorParamSpec[]
}

export type ConstantOperandJSON = { kind: 'constant'; value: number }
export type FactorOperandJSON = {
  kind: 'factor'
  factor_id: string
  column: string
  params: Record<string, number>
}
export type FormulaOperandJSON = { kind: 'formula'; formula_id: string; column: string }
export type OperandJSON = ConstantOperandJSON | FactorOperandJSON | FormulaOperandJSON

export type BinaryOpJSON = {
  node: 'binary'
  op: '+' | '-' | '*' | '/'
  left: ExprJSON
  right: ExprJSON
}
export type UnaryOpJSON = { node: 'unary'; op: 'neg'; operand: ExprJSON }
export type ExprJSON = BinaryOpJSON | UnaryOpJSON | OperandJSON

export const COMPARISON_OPS = ['>', '>=', '<', '<=', '==', '!='] as const
export const CROSS_OPS = ['crosses_above', 'crosses_below'] as const
export const PREDICATE_OPS = [...COMPARISON_OPS, ...CROSS_OPS] as const

export type PredicateJSON = {
  node: 'predicate'
  left: OperandJSON
  operator: (typeof PREDICATE_OPS)[number]
  right: OperandJSON
}
export type CompositionJSON = {
  node: 'composition'
  op: 'AND' | 'OR' | 'NOT'
  operands: RuleNodeJSON[]
}
export type RuleNodeJSON = PredicateJSON | CompositionJSON

export function defaultOperand(factors: FactorOption[]): OperandJSON {
  // 팩터 카탈로그가 로드된 상태면 첫 팩터를, 아니면 상수 0을 기본값으로 사용.
  const first = factors[0]
  if (!first) return { kind: 'constant', value: 0 }
  return { kind: 'factor', factor_id: first.id, column: first.output[0] ?? '', params: {} }
}

export function defaultExpr(factors: FactorOption[]): ExprJSON {
  return defaultOperand(factors)
}

export function defaultPredicate(factors: FactorOption[]): PredicateJSON {
  return {
    node: 'predicate',
    left: defaultOperand(factors),
    operator: '>',
    right: defaultOperand(factors),
  }
}

export function defaultRuleNode(factors: FactorOption[]): RuleNodeJSON {
  return defaultPredicate(factors)
}

export function isOperand(v: ExprJSON): v is OperandJSON {
  return 'kind' in v
}
