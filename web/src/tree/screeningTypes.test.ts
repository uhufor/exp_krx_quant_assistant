import { describe, expect, it } from 'vitest'
import type { FactorOption } from './types'
import {
  defaultScreeningPredicate,
  nextCompositionOperands,
  type ScreeningCompositionJSON,
} from './screeningTypes'

const PRICE: FactorOption = {
  id: 'price',
  display_name: '가격(종가)',
  category: 'price',
  output: ['close'],
  params: [],
}

describe('nextCompositionOperands', () => {
  it('AND에서 OR로 전환 시 기존 operands(5개)를 그대로 보존한다(버그 리포트 I5)', () => {
    const operands = Array.from({ length: 5 }, () => defaultScreeningPredicate([PRICE]))
    const and: ScreeningCompositionJSON = { node: 'composition', op: 'AND', operands }
    expect(nextCompositionOperands('OR', and, [PRICE])).toBe(operands)
  })

  it('AND에서 NOT으로 전환 시 첫 operand만 남긴다(단항 제약)', () => {
    const first = defaultScreeningPredicate([PRICE])
    const second = defaultScreeningPredicate([PRICE])
    const and: ScreeningCompositionJSON = { node: 'composition', op: 'AND', operands: [first, second] }
    expect(nextCompositionOperands('NOT', and, [PRICE])).toEqual([first])
  })

  it('NOT(1개)에서 AND로 전환 시 기존 operand를 유지하고 default 1개를 보충한다', () => {
    const only = defaultScreeningPredicate([PRICE])
    const not_: ScreeningCompositionJSON = { node: 'composition', op: 'NOT', operands: [only] }
    const result = nextCompositionOperands('AND', not_, [PRICE])
    expect(result).toHaveLength(2)
    expect(result[0]).toBe(only)
  })

  it('predicate 노드에서 AND로 전환 시 기존 predicate를 버리고 default 2개로 초기화한다(기존 동작 유지)', () => {
    const predicate = defaultScreeningPredicate([PRICE])
    const result = nextCompositionOperands('AND', predicate, [PRICE])
    expect(result).toHaveLength(2)
    expect(result[0]).not.toBe(predicate)
  })
})
