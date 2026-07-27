# TRD-R01-D — DART 재무제표 실데이터 연동 (Deferred TR-R01-D01~D04 확정)

**작성일**: 2026-07-26
**Status**: 확정 (구현 착수 가능)
**전제**: `TRD-R01-FACTOR_PLATFORM.md` §4.7 / `PRD-R01-FACTOR_PLATFORM.md` §8이 "선행 명세 확정 전 착수 시 어댑터 구현 공전"이라 명시한 4개 Deferred TR(D01~D04)을 본 문서가 확정한다. 완료 정의: `DartFundamentalAdapter.fetch_financials`가 실 종목에서 F2 재무 팩터 14종에 NaN 아닌 값을 산출.

**범위 경계**: 본 문서는 `fetch_financials`만 다룬다. `fetch_valuation`(PER/PBR/시가총액 등)은 DART가 제공하지 않는 시장 데이터이므로 `DartFundamentalAdapter.fetch_valuation`은 계속 `NotImplementedError`를 유지하고, 밸류에이션은 기존대로 `PyKrxFundamentalAdapter`가 전담한다.

---

## 1. 근거 자료

DART Open API 공식 개발가이드(opendart.fss.or.kr/guide) 확인 완료:
- 고유번호(`corpCode.xml`, `apiGrpCd=DS001`)
- 단일회사 전체 재무제표(`fnlttSinglAcntAll`, `apiGrpCd=DS003&apiId=2019020`)

---

## 2. TR-R01-D01 — 종목코드 → `corp_code` 해결

**API**: `GET https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={KEY}` → ZIP(내부 `CORPCODE.xml`).

**응답 필드**: `corp_code`(8자리) · `corp_name` · `corp_eng_name` · `stock_code`(6자리, 비상장사는 공백) · `modify_date`(YYYYMMDD).

**해결 규약**:
1. `stock_code`가 공백인 레코드(비상장법인)는 필터링해 제외한다.
2. `stock_code`(6자리, zfill) → `corp_code` 1:1 매핑 테이블을 로컬 캐시에 저장한다. 저장 위치는 `~/.cache/quant_krx/dart_corp_code.parquet`(프로젝트 DB와 분리 — corp_code는 종목 마스터 데이터이지 시계열 수집 데이터가 아니므로 `financial_statements`와 같은 as-of 정합 대상이 아니다).
3. 캐시 갱신 정책: 캐시 파일이 없거나, 캐시에 기록된 최대 `modify_date`가 7일 이상 경과했으면 재다운로드한다(상장/상폐 반영 지연 최소화, 매 호출 재다운로드는 API 낭비).
4. 조회 시 캐시에 없는 종목코드는 캐시를 강제 갱신 후 재조회 1회, 그래도 없으면 해당 종목을 결과에서 제외(전체 배치를 실패시키지 않음 — 기존 "결측은 NaN" 원칙과 동일한 결을 유지).

## 3. TR-R01-D02 — `account_nm`/`account_id` → 14계정 완전 매핑

**API**: `GET https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json?crtfc_key={KEY}&corp_code={8자리}&bsns_year={YYYY}&reprt_code={5자리}&fs_div={CFS|OFS}`

**응답 핵심 필드**: `rcept_no`(14자리) · `sj_div`(BS/IS/CIS/CF/SCE) · `sj_nm` · `account_id` · `account_nm` · `account_detail` · `thstrm_amount`(당기) · `frmtrm_amount`(전기) · `bfefrmtrm_amount`(전전기).

**매핑 원칙**: `account_id`는 IFRS 표준태그(`ifrs-full_*`)가 존재하면 그것을 최우선 키로 매칭하고, 기업이 커스텀 태그(`dart_*`, 확장 분류)를 쓴 경우를 대비해 `account_nm` 완전일치 문자열을 폴백으로 둔다. 두 키 모두 불일치하면 `FactorNote.MISSING_INPUT`으로 귀결되는 기존 degrade 경로를 그대로 탄다(본 매핑표가 어댑터 층의 유일 진실 원천이며 팩터 층은 무관).

`financial_statements`의 16개 값 컬럼 중 `invested_capital`은 DART 원천 태그가 없는 **파생 컬럼**이다 — `tests/fixtures/sample_financials.csv` 검증 결과 기존 관례가 `invested_capital == total_assets`이므로(ROIC 분모 정의, `factors/catalog/financial.py::roic`), 실데이터 연동에서도 동일하게 `total_assets` 값을 그대로 대입한다(별도 DART 조회 없음).

| 컬럼 | `sj_div` | `account_id` (1순위) | `account_nm` (폴백) | 비고 |
|---|---|---|---|---|
| `revenue` | IS | `ifrs-full_Revenue` | 매출액 / 수익(매출액) | |
| `gross_profit` | IS | `ifrs-full_GrossProfit` | 매출총이익 | |
| `operating_income` | IS | `dart_OperatingIncomeLoss` | 영업이익(손실) | IFRS는 영업이익 별도 표준 태그 없음 — 국내 커스텀 태그가 사실상 표준 |
| `net_income` | IS | `ifrs-full_ProfitLoss` | 당기순이익(손실) | |
| `pretax_income` | IS | `ifrs-full_ProfitLossBeforeTax` | 법인세비용차감전순이익(손실) | |
| `income_tax` | IS | `ifrs-full_IncomeTaxExpenseContinuingOperations` | 법인세비용 | |
| `total_assets` | BS | `ifrs-full_Assets` | 자산총계 | |
| `total_debt` | BS | `ifrs-full_Liabilities` | 부채총계 | |
| `total_equity` | BS | `ifrs-full_Equity` | 자본총계 | |
| `current_assets` | BS | `ifrs-full_CurrentAssets` | 유동자산 | |
| `current_liabilities` | BS | `ifrs-full_CurrentLiabilities` | 유동부채 | |
| `operating_cash_flow` | CF | `ifrs-full_CashFlowsFromUsedInOperatingActivities` | 영업활동으로 인한 현금흐름 / 영업활동현금흐름 | |
| `interest_expense` | IS | `ifrs-full_InterestExpense` | 이자비용 | 미분류/미공시 기업 다수 — NaN 빈도 높음 (Fixture "이자비용 0" 경계케이스와 정합) |
| `depreciation_amortization` | CF | (표준 태그 없음, `dart_Depreciation*` 계열) | 감가상각비 (+ 무형자산상각비 존재 시 합산) | 회사별 커스텀 태그 편차 큼 — NaN 빈도 가장 높을 것으로 예상 |
| `cash_and_equivalents` | BS | `ifrs-full_CashAndCashEquivalents` | 현금및현금성자산 | |
| `invested_capital` | — | — | — | 파생: `total_assets` 그대로 대입(§3 상단 근거) |

**주의**: 위 `account_id` 값은 IFRS 표준 태그명이며 DART 공식 가이드가 계정별 고정 매핑표를 제공하지 않는다(기업 자율 태깅). 따라서 이 표는 **잠정(provisional)** 매핑이며, 실 API 키로 실제 응답을 받아본 뒤 회사별 태그 편차가 확인되면 갱신한다 — 완료 정의(§0)의 "실 종목에서 F2 14종이 NaN 아닌 값 산출" 통합테스트가 이 표의 검증 게이트다.

## 4. TR-R01-D03 — `disclosure_date`/`period_end` 추출 규약

- **`disclosure_date`**: `fnlttSinglAcntAll` 응답은 `rcept_dt`를 직접 주지 않고 `rcept_no`(14자리, `YYYYMMDD` + 당일 순번 6자리)만 반환한다. `disclosure_date = date(rcept_no[:8])`로 파싱한다.
- **`period_end`**: 응답에 회계기간 종료일이 별도 필드로 오지 않으므로, 요청 파라미터 `bsns_year` + `reprt_code`에서 결정론적으로 도출한다(문자열 파싱 대신 고정 매핑 — 더 견고):

| `reprt_code` | 명칭 | `fiscal_quarter` | `period_end` |
|---|---|---|---|
| `11013` | 1분기보고서 | 1 | `{bsns_year}-03-31` |
| `11012` | 반기보고서 | 2 | `{bsns_year}-06-30` |
| `11014` | 3분기보고서 | 3 | `{bsns_year}-09-30` |
| `11011` | 사업보고서 | 4 | `{bsns_year}-12-31` |

동일 `disclosure_date`에 복수 레코드가 있는 경우(정정공시 등) tie-break은 기존 as-of 규약(`factors/asof.py`: `(disclosure_date asc, period_end desc)` 정렬 후 그룹 최상단)을 그대로 따르며 어댑터 층에서 별도 처리하지 않는다.

## 5. TR-R01-D04 — 연결(CFS) 우선 → 별도(OFS) 폴백

`fs_div=CFS`로 우선 조회하고, 응답이 빈 배열이거나 오류코드(`013` 데이터없음 등)면 `fs_div=OFS`로 재조회한다. 채택된 쪽의 `statement_scope`를 각각 `consolidated`/`separate`로 기록한다(스키마 CHECK 제약과 일치). 연결·별도 모두 실패하면 해당 분기는 결과에서 제외(NaN 경로).

## 6. 운영 고려사항 (PRD/TRD에 없던 실무 보강)

- **인증키**: `opendart.fss.or.kr`에서 무료 발급(40자리). 환경변수 `DART_API_KEY`(`.env`) — `config/settings.py`에 추가(§ 후속 작업).
- **호출 한도**: 미승인 키는 일 10,000건(승인 시 확대 가능) — 대량 종목 배치 수집 시 상한 도달 가능성을 사용자에게 안내.
- **오류코드**: `000`(성공) 외 `010`(미등록키) · `013`(데이터없음, 하드 실패 아님 — 결측 처리) · `020`(사용한도초과) · `800`(점검중) 구분 처리. `010`/`020`은 `PyKrxFundamentalAdapter.fetch_valuation`의 KRX_ID/KRX_PW 미설정 패턴과 동일하게 명확한 `RuntimeError`, `013`은 결측(빈 프레임)으로 무시.
- **HTTP 클라이언트**: 프로젝트에 이미 존재하는 `httpx`를 런타임 의존성으로 승격(현재 dev-only) — 신규 의존성 추가 없음.

## 7. 범위 외 (본 문서에서 다루지 않음)

관리종목/투자경고·위험/거래정지/정리매매/환기종목(5종)은 DART 영역이 아니라 KRX 자체 데이터(data.krx.co.kr)이므로 본 DART 연동으로 해결되지 않는다 — `EPIC_R03/PRD-R03-SCREENING.md` FR-12가 이미 별도 EPIC 후보로 분리해둔 상태를 유지한다. 다만 "불성실공시기업" 1종은 DART가 별도 API(`unfaithful`)로 제공하므로 EPIC_R03 재검토 시 참고 가능(본 문서 범위 밖, 정보 제공 목적 기록만).
