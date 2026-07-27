# RESEARCH-R04 — 팩터/데이터 확장 조사 기록

**작성일**: 2026-07-26
**Status**: 조사 완료, 착수 전(별도 작업 예정) — 본 문서는 PRD/TRD가 아니라 후속 작업의 입력이 되는 조사 기록이다.
**계기**: `EPIC_R03/PRD-R03-SCREENING.md` §8 "ADR Follow-up #1"(6종 제외 필터 데이터 소스 미확보, 사용자 재확인 필요)의 후속 조사 + 현재 32종(+스크리닝 3종) 팩터 카탈로그 대비 업계 팩터 갭 조사.

**범위**: 조사만 수행하고 구현은 하지 않았다. 이후 별도 세션에서 우선순위에 따라 PRD/TRD를 작성하고 착수한다.

---

## 1. 하드 잠금 6종 상태 플래그 — 데이터 소스 조사

`EPIC_R03`에서 v1 하드 비활성화된 6종(관리종목/투자경고·위험/거래정지/정리매매/환기종목/불성실공시기업)의 실제 데이터 출처를 확인했다.

| 상태 플래그 | 출처 | 접근 방식 | 비고 |
|---|---|---|---|
| 관리종목 | `data.krx.co.kr` MDC 통계화면(`menuId=MDC02020701`, 관리종목현황/지정내역/지정일전후 등락률) | 비공식 스크래핑(OTP 발급 → CSV 다운로드 — `pykrx`가 내부적으로 쓰는 것과 동일 패턴) | 공식 문서화 API 아님. `pykrx`에 래핑된 함수 없음 — 자체 스크레이퍼 필요 |
| 투자주의/경고/위험종목 | `kind.krx.co.kr/investwarn/investattentwarnrisky.do?method=investattentwarnriskyMain` | HTML 폼 기반 조회 화면(공식 오픈API 아님). 시장(KOSPI/KOSDAQ/KONEX)·종목명·기간 필터 지원, 엑셀 export 존재 | 위와 동일 — 스크래핑 대상 |
| 거래정지 | `data.krx.co.kr` MDC 계열 통계화면(관리종목현황과 인접) | 위와 동일 | 위와 동일 |
| 정리매매 | `data.krx.co.kr`/`kind.krx.co.kr` 동일 계열 | 위와 동일 | 위와 동일 |
| 환기종목 | `kind.krx.co.kr` 공시 카테고리 내 | 위와 동일 | 위와 동일 |
| 불성실공시기업 | **미확정** — `opendart.fss.or.kr` 공식 Open API 가이드를 재확인한 결과 6개 그룹(공시정보/정기보고서 주요정보·재무정보/지분공시 종합정보/주요사항보고서 주요정보/증권신고서 주요정보) 어디에도 해당 엔드포인트가 없음. `dart.fss.or.kr` 웹사이트 자체 열람 메뉴에만 존재하는 것으로 추정(미확인) | 스크래핑 필요 가능성 — 별도 확인 필요 | **정정**: 이전 세션 보고에서 "DART API로 제공"이라 했던 것은 오류. Open API에는 없다 |

**결론**: 6종 전부 **공식 오픈API가 아니라 KRX/DART 웹 화면 스크래핑 대상**이다. `pykrx`가 이미 `data.krx.co.kr`에 대해 이 패턴(OTP+CSV)으로 다른 데이터를 가져오므로, 구현한다면 그 방식을 참고한 프로젝트 자체 스크레이퍼 모듈이 필요하다 — 비공식 API 의존이라 KRX/DART가 화면 구조를 바꾸면 깨지는 유지보수 리스크가 있다. 이번 DART 재무제표 연동(`TRD-R01-D-DART_FINANCIALS.md`, 공식 Open API 기반)과는 성격이 다른 별도 작업으로 분리하는 것을 권장한다(기존 PRD-R03 D4/§8 결정과 일치).

**대안**: 불성실공시기업처럼 확정 데이터가 없는 항목은, 이미 수집 중인 DART 재무데이터(정정공시 빈도, 감사의견 등 — DS002 정기보고서 주요정보 그룹에 감사인 관련 정보 존재 가능성, 미확인)로 "공시 리스크 근사 점수"를 자체 구성하는 대체 경로도 있다(§3-C 참고).

---

## 2. 업계에서 쓰이는 팩터 카테고리 (현재 카탈로그 대비 조망)

현재 카탈로그는 35종(가격·기술 9 + 밸류에이션 11 + 재무제표 14 + 스크리닝용 신규 3: 거래대금·거래량·52주 최고가)이며 Value/Quality/Growth/Momentum/Trend/Stability 카테고리를 다룬다. 학계·업계에서 널리 쓰이지만 현재 빠진 축:

- **Accruals(발생액)** — Sloan(1996) accruals anomaly
- **Investment/Asset Growth** — 총자산 증가율(과잉투자 페널티, Cooper et al.)
- **Low-volatility / Beta** — 저변동성 이상현상, 시장 베타
- **Composite risk score** — Piotroski F-Score, Altman Z-Score, Ohlson O-Score
- **Ownership/Insider** — 외국인·기관 보유비율, 임원 지분 변동
- **Short interest** — 공매도 비중
- **Liquidity 미시구조** — Amihud illiquidity, 회전율
- **Analyst/Consensus** — 목표주가, 컨센서스 서프라이즈(국내는 유료 소스 필요)
- **ESG** — KRX ESG 지수/데이터

---

## 3. 갭 분석 — 데이터 가용성 기준 3단계

### A. 이미 수집 중인 데이터로 지금 당장 팩터화 가능(신규 수집 불필요, 계산 로직만 추가)

| 팩터 | 산식 | 필요 필드(전부 이미 `financial_statements`/`fundamental_daily`에 존재) |
|---|---|---|
| Accruals | `(net_income - operating_cash_flow) / total_assets` | net_income, operating_cash_flow, total_assets |
| OCF Yield | `operating_cash_flow / market_cap` | operating_cash_flow(재무제표), market_cap(밸류에이션) |
| Net Debt / EBITDA | `(total_debt - cash_and_equivalents) / (operating_income + depreciation_amortization)` | 전부 존재 |
| Asset Turnover | `revenue / total_assets` | 존재 |
| Cash Ratio | `cash_and_equivalents / current_liabilities` | 존재 |
| DuPont 분해 ROE | `net_margin × asset_turnover × (total_assets/total_equity)` | 존재(현재 `roe_approx`는 eps/bps 근사치뿐, 진짜 분해 없음) |
| Piotroski F-Score(9개 중 8개) | ROA>0·ΔROA>0·CFO>0·CFO>NI·Δ레버리지·Δ유동비율·Δ총마진·Δ자산회전율 | financial_statements + fundamental_daily(shares 변화)로 조합 가능 |

**→ 가장 비용 대비 효과가 큰 확장 지점.** `factors/catalog/financial.py`에 계산 로직만 추가하면 된다(신규 데이터 소스·스키마 변경 불필요).

### B. 기존 소스(KRX/DART)에 있지만 우리 파이프라인이 아직 안 가져오는 것(필드/어댑터 확장 필요)

| 팩터 | 막힌 이유 | 해결 방향 |
|---|---|---|
| Altman Z-Score, 이익잉여금 관련 지표 | `retained_earnings`(이익잉여금) 필드 없음 | `financial_statements`에 컬럼 additive 추가 + `dart_account_mapping.py`에 `ifrs-full_RetainedEarnings` 매핑 추가 |
| Quick Ratio(당좌비율), 재고회전율 | `inventory`(재고자산) 필드 없음 | 위와 동일 패턴 |
| 진짜 FCF Yield(capex 반영) | `capex` 필드 없음 | DART CF 항목에서 유형자산취득 관련 태그 추가(위와 동일 패턴) |
| 외국인/기관 순매수, 보유비율 | `pykrx.get_market_trading_value_by_date` 등이 이미 제공하나 `PyKrxAdapter`/`PyKrxFundamentalAdapter` 어디서도 호출하지 않음 | 새 어댑터 메서드 추가(신규 외부 소스 아님, 이미 의존성에 있는 pykrx 활용) |
| 공매도 비중 | `pykrx.get_shorting_balance_by_date`가 제공(단, KRX 특성상 T+2 지연 있음) | 위와 동일 |
| 임원·주요주주 지분변동(내부자 매매 시그널) | DART DS004(지분공시 종합정보) 그룹 — `대량보유상황보고`(`apiId=2019021`)/`임원·주요주주소유보고`(`apiId=2019022`)가 **공식 문서화되어 있음**(확인 완료, opendart.fss.or.kr) | 이미 발급받은 `DART_API_KEY`로 바로 가능. 현재 `DartFundamentalAdapter`는 DS003(재무정보)만 다루므로 DS004 전용 신규 메서드/어댑터로 확장 |

### C. 완전히 새로운 외부 소스가 필요한 것

- **애널리스트 컨센서스(목표주가·EPS 추정치)** — KRX/DART 어디에도 없음. FnGuide/WiseFn/Naver금융 컨센서스 크롤링 또는 유료 API(Refinitiv 등) 필요
- **ESG 점수** — `openapi.krx.co.kr`에 "ESG 증권상품/채권/지수" 카테고리가 실제 존재(공식 Open API 목록에서 확인). 신규 가입/토큰 발급 필요하지만 소스 자체는 KRX가 공식 제공
- **6종 상태 플래그**(§1) — 공식 API 없음, 스크래핑 전용

---

## 4. 후속 작업 시 우선순위 제안 (참고용, 확정 아님)

1. **A그룹 전체**(Accruals·OCF Yield·Net Debt/EBITDA·DuPont ROE·F-Score) — 신규 데이터 수집 없이 즉시 팩터 추가 가능, 최우선
2. **B그룹 중 pykrx 기반**(외국인/기관 순매수, 공매도) — 이미 있는 의존성 재활용
3. **B그룹 중 DART DS004**(지분공시) — 이미 있는 `DART_API_KEY` 재활용, DS004 어댑터 신규 추가
4. **B그룹 중 필드확장형**(retained_earnings/inventory/capex) — 스키마 additive 변경 + `dart_account_mapping.py` 확장
5. **C그룹**(ESG, 컨센서스) — 별도 소스 계약/가입 필요, 우선순위 낮음
6. **6종 상태 플래그 스크래핑** — 비공식 API 의존이라 유지보수 리스크 큼, 별도 EPIC으로 격리 권장(기존 PRD-R03 §8 결정과 일치)

## 5. 미확인/후속 확인 필요 사항 (Open Questions)

- 불성실공시기업 데이터가 `dart.fss.or.kr` 웹사이트의 어느 메뉴에 있는지, 스크래핑 가능한 안정적 구조인지 확인 필요
- DART DS002(정기보고서 주요정보) 그룹에 감사인/감사의견 관련 API가 있는지 — 있다면 §1 대안(공시 리스크 근사 점수)의 입력으로 사용 가능
- `data.krx.co.kr`의 관리종목/거래정지/정리매매 통계화면이 pykrx의 OTP 메커니즘과 동일 인증 흐름으로 접근되는지 실제 요청으로 검증 필요(현재는 웹 검색 기반 추정)
- ESG용 `openapi.krx.co.kr` 가입 절차·비용·토큰 발급 방식 확인 필요
