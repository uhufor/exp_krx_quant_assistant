// 스크리닝(Screening) 조건 트리 JSON 형상 — 백엔드 screening/definition.py의
// to_dict()/from_dict()와 1:1 대응. rule/formula 트리 타입(./types.ts)과 이름 충돌을
//피하기 위해 전부 Screening 접두어를 붙인 독립 파일이다(INV-2: screening 정의는
// screening 패키지가 유일 진실 원천 — rule 타입 재사용 금지, 구조만 참고).
import type { FactorOption } from './types'

export type ScreeningConstantOperandJSON = { kind: 'constant'; value: number }
export type ScreeningFactorOperandJSON = {
  kind: 'factor'
  factor_id: string
  column: string
  params: Record<string, number>
}
// FormulaOperand는 definition.py에 존재하나 screening/service.py::_validate_operand가
// 항상 검증 오류로 거부한다("screening에서 아직 지원되지 않습니다") — 편집기에서 선택
// 가능한 피연산자 종류로 노출하지 않는다(선택 가능해 보이지만 항상 실패하는 UI 방지).
export type ScreeningOperandJSON = ScreeningConstantOperandJSON | ScreeningFactorOperandJSON

export const SCREENING_COMPARISON_OPS = ['>', '>=', '<', '<=', '==', '!='] as const
export const SCREENING_CROSS_OPS = ['crosses_above', 'crosses_below'] as const
export const SCREENING_PREDICATE_OPS = [
  ...SCREENING_COMPARISON_OPS,
  ...SCREENING_CROSS_OPS,
] as const

export type ScreeningPredicateJSON = {
  node: 'predicate'
  left: ScreeningOperandJSON
  operator: (typeof SCREENING_PREDICATE_OPS)[number]
  right: ScreeningOperandJSON
}

export type ScreeningCompositionJSON = {
  node: 'composition'
  op: 'AND' | 'OR' | 'NOT'
  operands: ScreeningNodeJSON[]
}

export type ScreeningWindowPredicateJSON = {
  node: 'window_predicate'
  inner: ScreeningNodeJSON
  n_bars: number
  include_current_bar: boolean
}

// ranking.py::_SNAPSHOT_COLUMNS — RankPredicate.column은 이 3종 시장 스냅샷 네이티브
// 컬럼만 허용된다(factor의 output 컬럼이 아님, 백엔드 검증과 동일 제약).
export const SCREENING_RANK_COLUMNS = ['close', 'volume', 'trading_value'] as const
export const SCREENING_RANK_METRICS = ['asc', 'desc'] as const

export type ScreeningRankPredicateJSON = {
  node: 'rank_predicate'
  factor_id: string
  column: (typeof SCREENING_RANK_COLUMNS)[number]
  rank_metric: (typeof SCREENING_RANK_METRICS)[number]
  top_n: number
  params: Record<string, number>
}

export type ScreeningNodeJSON =
  | ScreeningPredicateJSON
  | ScreeningCompositionJSON
  | ScreeningWindowPredicateJSON
  | ScreeningRankPredicateJSON

// universe.py::_SUPPORTED_FILTERS — 4종은 실제로 걸러지는 활성 필터(토글 가능).
export const SCREENING_SUPPORTED_FILTERS = ['etf', 'etn', 'preferred', 'spac'] as const
export type ScreeningSupportedFilter = (typeof SCREENING_SUPPORTED_FILTERS)[number]

// definition.py::_UNSUPPORTED_FILTERS — 예약되었으나 v1 데이터 소스가 없는 6종.
// ScanUniverse 생성자가 즉시 UnsupportedFilterError를 던지므로, GUI는 반드시 비활성화
// 상태로만 노출해야 한다(안전 요구사항 — 선택 가능해 보이지만 저장 시 항상 실패하는
// UI를 만들면 안 됨).
export const SCREENING_UNSUPPORTED_FILTERS = [
  'administrative_issue',
  'investment_alert',
  'trading_halt',
  'liquidation_trading',
  'market_alert',
  'unfaithful_disclosure',
] as const
export type ScreeningUnsupportedFilter = (typeof SCREENING_UNSUPPORTED_FILTERS)[number]

export const SCREENING_FILTER_LABELS: Record<
  ScreeningSupportedFilter | ScreeningUnsupportedFilter,
  string
> = {
  etf: 'ETF 제외',
  etn: 'ETN 제외',
  preferred: '우선주 제외',
  spac: 'SPAC 제외',
  administrative_issue: '관리종목',
  investment_alert: '투자경고/위험종목',
  trading_halt: '거래정지',
  liquidation_trading: '정리매매',
  market_alert: '환기종목',
  unfaithful_disclosure: '불성실공시기업',
}

export type ScanUniverseJSON = {
  market: string
  exclusion_filters: string[]
}

export type ScreeningConditionJSON = {
  id: string
  name: string
  version: string
  universe: ScanUniverseJSON
  root: ScreeningNodeJSON
  metadata: Record<string, unknown>
  schema_version: number
}

export function defaultScreeningOperand(factors: FactorOption[]): ScreeningOperandJSON {
  const first = factors[0]
  if (!first) return { kind: 'constant', value: 0 }
  return { kind: 'factor', factor_id: first.id, column: first.output[0] ?? '', params: {} }
}

export function defaultScreeningPredicate(factors: FactorOption[]): ScreeningPredicateJSON {
  return {
    node: 'predicate',
    left: defaultScreeningOperand(factors),
    operator: '>',
    right: defaultScreeningOperand(factors),
  }
}

/** AND/OR/NOT 전환 시 다음 operands를 결정한다 — 같은 composition 형태끼리(AND↔OR 등)
 * 전환할 때 기존 하위 트리를 보존한다(버그 리포트 I5: 전환마다 재생성하면 조립해 둔
 * 트리가 사라짐). NOT은 단항이라 첫 operand만 남기고, 2개 미만이면 AND/OR 최소
 * 요건(2개)을 채우기 위해 default를 보충한다. */
export function nextCompositionOperands(
  newOp: 'AND' | 'OR' | 'NOT',
  currentValue: ScreeningNodeJSON,
  factors: FactorOption[],
): ScreeningNodeJSON[] {
  const existingOperands = currentValue.node === 'composition' ? currentValue.operands : null
  if (newOp === 'NOT') {
    return [existingOperands?.[0] ?? defaultScreeningPredicate(factors)]
  }
  if (existingOperands && existingOperands.length >= 2) {
    return existingOperands
  }
  if (existingOperands && existingOperands.length === 1) {
    return [existingOperands[0], defaultScreeningPredicate(factors)]
  }
  return [defaultScreeningPredicate(factors), defaultScreeningPredicate(factors)]
}

// market은 백엔드 ScanUniverse 기본값("KRX")을 그대로 쓴다 — KRX는 KOSPI+KOSDAQ 통합
// 시장을 뜻하며(resolve_scan_universe가 provider.list_symbols(market="KRX")로 조회),
// 표시용 라벨만 "KOSPI+KOSDAQ"로 보여준다(ScreeningTreeEditor 참고).
export function defaultScanUniverse(): ScanUniverseJSON {
  return { market: 'KRX', exclusion_filters: [] }
}

export function defaultScreeningCondition(
  id: string,
  factors: FactorOption[],
): ScreeningConditionJSON {
  return {
    id,
    name: '',
    version: '1',
    universe: defaultScanUniverse(),
    root: defaultScreeningPredicate(factors),
    metadata: {},
    schema_version: 1,
  }
}
