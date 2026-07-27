import { describe, expect, it } from 'vitest'
import type { FactorOption } from './types'
import {
  defaultFactorRankPredicate,
  defaultScreeningPredicate,
  factorRankEligibleFactors,
  nextCompositionOperands,
  type ScreeningCompositionJSON,
} from './screeningTypes'

const PRICE: FactorOption = {
  id: 'price',
  display_name: '가격(종가)',
  category: 'price',
  output: ['close'],
  params: [],
  required_data: ['ohlcv'],
}

const ROIC: FactorOption = {
  id: 'roic',
  display_name: 'ROIC',
  category: 'quality',
  output: ['roic'],
  params: [],
  required_data: ['financials'],
}

const PER: FactorOption = {
  id: 'per',
  display_name: 'PER',
  category: 'value',
  output: ['per'],
  params: [],
  required_data: ['valuation'],
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

describe('factorRankEligibleFactors', () => {
  it('required_data에 ohlcv가 포함된 팩터(가격·기술)는 제외한다', () => {
    const result = factorRankEligibleFactors([PRICE, ROIC, PER])
    expect(result).toEqual([ROIC, PER])
  })

  it('빈 목록이면 빈 목록을 반환한다', () => {
    expect(factorRankEligibleFactors([])).toEqual([])
  })
})

describe('defaultFactorRankPredicate', () => {
  it('OHLCV 불필요 팩터 중 첫 번째를 기본값으로 사용한다(가격·기술 팩터는 후보에서 제외)', () => {
    const result = defaultFactorRankPredicate([PRICE, ROIC, PER])
    expect(result).toEqual({
      node: 'factor_rank_predicate',
      factor_id: 'roic',
      column: 'roic',
      rank_metric: 'desc',
      top_n: 10,
      params: {},
    })
  })

  it('후보 팩터가 하나도 없으면 빈 factor_id/column으로 초기화한다', () => {
    const result = defaultFactorRankPredicate([PRICE])
    expect(result.factor_id).toBe('')
    expect(result.column).toBe('')
  })
})
