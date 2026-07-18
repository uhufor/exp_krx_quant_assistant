import { describe, expect, it } from 'vitest'
import type { ExprJSON, FactorOption } from './types'
import { defaultOperand, defaultPredicate, defaultRuleNode, isOperand } from './types'

const SMA: FactorOption = {
  id: 'sma',
  display_name: '단순이동평균',
  category: 'trend',
  output: ['sma'],
  params: [{ name: 'window', type: 'int', default: 20, description: '', min: 2, max: null, choices: null }],
}

describe('defaultOperand', () => {
  it('팩터 카탈로그가 있으면 첫 팩터를 기본값으로 사용한다', () => {
    const op = defaultOperand([SMA])
    expect(op).toEqual({ kind: 'factor', factor_id: 'sma', column: 'sma', params: {} })
  })

  it('팩터 카탈로그가 비어 있으면 상수 0을 기본값으로 사용한다', () => {
    expect(defaultOperand([])).toEqual({ kind: 'constant', value: 0 })
  })
})

describe('defaultPredicate', () => {
  it('좌/우 피연산자와 기본 연산자(>)를 갖는 predicate 노드를 만든다', () => {
    const p = defaultPredicate([SMA])
    expect(p.node).toBe('predicate')
    expect(p.operator).toBe('>')
    expect(p.left.kind).toBe('factor')
    expect(p.right.kind).toBe('factor')
  })
})

describe('defaultRuleNode', () => {
  it('predicate 형태를 반환한다(백엔드 rule/definition.py의 root 계약과 정합)', () => {
    expect(defaultRuleNode([]).node).toBe('predicate')
  })
})

describe('isOperand', () => {
  it('리프 피연산자(kind 태그)를 true로 판정한다', () => {
    expect(isOperand({ kind: 'constant', value: 1 })).toBe(true)
  })

  it('BinaryOp/UnaryOp(node 태그)를 false로 판정해 재귀 순회가 올바르게 분기한다', () => {
    const nested: ExprJSON = {
      node: 'binary',
      op: '-',
      left: { node: 'unary', op: 'neg', operand: { kind: 'constant', value: 1 } },
      right: { kind: 'constant', value: 5 },
    }
    expect(isOperand(nested)).toBe(false)
    if (!isOperand(nested)) {
      const left = nested.left
      expect(isOperand(left)).toBe(false)
      if (!isOperand(left) && left.node === 'unary') {
        expect(isOperand(left.operand)).toBe(true)
      }
      expect(isOperand(nested.right)).toBe(true)
    }
  })
})
