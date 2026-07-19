# 유명·실증된 퀀트/트레이딩 전략 조사 리포트

시장에서 오래 검증되었거나 학술적으로 실증된 트레이딩·투자 전략을 조사한 결과다.
`quant-krx`의 No-Code Strategy Workspace로 무엇을 재현할 수 있는지 판단하기 위한
사전 조사 자료이며, 실제 적용 가능 여부와 CLI 예제는
[APPLICABLE_STRATEGIES_CLI_GUIDE.md](APPLICABLE_STRATEGIES_CLI_GUIDE.md)에 별도 정리했다.

> **핵심 주의사항**: 아래 수익률·통계는 원저자 발표치 또는 널리 인용되는 수치이며,
> 독립 재검증 시 대체로 하향 조정된다(McLean & Pontiff 2016, 5번 항목 참고).
> 생존편향·거래비용 미반영·데이터 스누핑이 원 발표치를 부풀리는 공통 원인이다.

---

## 1. 추세추종·모멘텀 계열

| 전략 | 핵심 로직 | 발표/재현 수익률(연) | 비고 |
|---|---|---|---|
| **Turtle Trading**(Richard Dennis & William Eckhardt, 1983) | Donchian 채널 20일/55일 고점 돌파 진입, ATR 기반 포지션 사이징, 피라미딩 | 1983-1988 실거래 계좌 연 80%+ 보고(소수 트레이더, 초기 국면) | 표본 극소수(터틀 학생 ~20명), 1980년대 원자재 강세장 편향, 현재 재현 시 수익률 크게 하회 |
| **Golden Cross / Death Cross**(SMA 50/200 교차) | 단기 이평선이 장기 이평선을 상향(골든)/하향(데드) 돌파 시 매수/매도 | S&P500 장기 백테스트: Buy&Hold 대비 CAGR은 낮으나 MDD 절반 이하로 축소 | 횡보장에서 휩쏘(whipsaw) 잦음, "손실 회피"에는 유효하나 "초과수익"은 불명확 |
| **Cross-sectional Momentum**(Jegadeesh & Titman, 1993) | 과거 3~12개월 수익률 상위 종목 매수, 하위 종목 매도(12-1 모멘텀, 최근 1개월 skip) | 1965-1989 미국 주식 월 ~1%(연 12%대) 초과수익, 통계적으로 유의 | 가장 널리 재현된 팩터 중 하나. 2000년대 이후 알파 축소, 모멘텀 크래시(2009) 존재 |
| **Dual/Absolute Momentum · GEM**(Gary Antonacci) | 자산군(주식/채권 등) 상대모멘텀으로 종목 선택 + 절대모멘텀(현금 대비)으로 리스크오프 회피 | 저자 백테스트(1974-2013) CAGR 약 15~17%, MDD 완화 | 월간 리밸런싱 단순 규칙, 저자 자신의 책 기준 수치(독립검증 낮은 편) |
| **52주 신고가 모멘텀**(George & Hwang, 2004) | 52주 신고가 근접 종목이 신고가와 먼 종목보다 향후 수익률 높음 | 원 논문 연 상당한 초과수익 보고, 이후 다수 재현 | 전통 모멘텀보다 "신고가 근접도"가 더 강한 예측력이라는 것이 핵심 주장 |
| **CTA/관리선물(Managed Futures)** | 다중 자산군 추세추종 시스템의 집합(개별 전략 비공개, 지수로만 관측) | SG Trend Index 등 장기 연 5~8%대, 낮은 주식 상관관계 | 위기 시(2008, 2020) 플러스 수익으로 분산투자 가치 입증, 최근 저변동성 국면엔 수익 저조 |

---

## 2. 가치·퀄리티 계열

| 전략 | 핵심 로직 | 발표/재현 수익률(연) | 비고 |
|---|---|---|---|
| **Magic Formula**(Joel Greenblatt, 2005) | 이익수익률(EBIT/EV) + 투하자본이익률(ROIC) 두 팩터를 각각 순위화, 합산 순위 상위 종목 매수 | 저자 백테스트(1988-2004) 연 30.8% 주장 | 독립 재현 시 연 13~17%대로 하향(거래비용·소형주 유동성 미반영, 표본 구간 편향 지적) |
| **Piotroski F-Score**(2000) | 재무제표 기반 9개 이진 기준(수익성/재무건전성/운영효율) 합산 점수, 저PBR군 내 고득점 종목 매수 | 1976-1996 저PBR 롱-숏 초과수익 연 7.5%p(고득점-저득점 스프레드) | 저PBR(가치주) 유니버스 내에서만 유효, 원 논문 자체가 소형·저유동성 종목 비중 높음 |
| **QMJ(Quality Minus Junk)**(Asness, Frazzini, Pedersen — AQR) | 수익성·성장성·안전성·배당성향 복합 스코어로 퀄리티 롱, 정크 숏 | 다지역 장기 Sharpe 0.4~0.6대(팩터 자체) | AQR 자체 논문+운용상품으로 실제 검증. 순수 롱-숏 팩터라 롱온리 재현 시 효과 약화 |
| **GP/A(Gross Profitability)**(Novy-Marx, 2013) | 매출총이익/총자산이 높은 종목이 저PBR 못지않은 예측력 보유 | 원 논문 기준 연 5%p대 팩터 프리미엄(퀄리티 대비 가치보다 강건) | "가치주의 저품질 함정"을 보완하는 팩터로 제시, 이후 광범위하게 인용·재현 |
| **저변동성 이상현상(Low-Volatility Anomaly)** | 실현변동성/베타가 낮은 종목이 CAPM 예측보다 높은 위험조정수익 | 다수 연구에서 저변동 종목 Sharpe > 고변동 종목 Sharpe, 절대수익도 대등하거나 우위 | 전통 CAPM(고위험=고수익)에 정면으로 배치되는 대표적 이상현상. 최근 저금리기 상대적 부진 |
| **Warren Buffett / Berkshire Hathaway 스타일** | 저평가된 우량기업(ROE 높고 부채 낮음)을 장기 보유, 집중투자 | 1965-2023 Berkshire 주가 연 ~19.8%(S&P500 총수익 연 ~10.2%) | 프레이저드(Fama-French 스타일 팩터 회귀 시 상당 부분이 Value+Quality+저변동+레버리지 노출로 설명됨, AQR 논문 "Buffett's Alpha") |

---

## 3. 전설적 헤지펀드 — Renaissance Technologies Medallion Fund

- 1988~2018년 연평균 총수익률(gross) 약 66%, 수수료 차감 후(net) 약 39% — 헤지펀드 역사상 최고 성과로 꼽힘.
- 순수 퀀트·고빈도 통계적 차익거래 기반이며, 전략 세부는 철저히 비공개.
- **재현 불가**: 펀드 자체 자본만 운용(외부 투자자 배제), 막대한 데이터·인프라·인재 집중, 시장 임팩트를 최소화하기 위한 용량 제한(capacity-constrained) 전략이라 소액 개인/일반 자산운용에 그대로 적용 불가능.
- 참고 사례로서의 의미: "단일 팩터가 아니라 수천 개의 약한 신호를 결합한 앙상블 모델"이 극단적 성과의 원천이라는 통념이 일반적으로 받아들여짐(공식 논문·검증 없음, 업계 정설 수준).

---

## 4. ⚠️ 한국 시장 특이사항 — 미국 실증 결과를 그대로 적용하면 안 되는 이유

한국 학술 문헌(KCI/DBpia)을 조사한 결과, 미국 시장에서 강건한 몇몇 팩터가 한국에서는
**반대 방향**이거나 **유의하지 않은** 것으로 나타난다.

- **모멘텀 반전**: 한국 주식시장에서는 미국식 12-1 모멘텀이 오히려 유의하지 않거나 단기(1개월 내) 반전 현상이 두드러진다는 연구가 다수. 미국 모멘텀 전략을 한국에 그대로 이식하면 기대와 반대 결과가 나올 수 있음.
- **사이즈 효과 지배적**: 소형주 효과(Size effect)가 한국 시장에서 가장 강건하고 지배적인 팩터로 반복 확인됨. 개인투자자 비중이 높은 시장 구조, 유동성 프리미엄과 결합되어 있다는 해석이 일반적.
- **가치 팩터 유의**: PBR/PER 기반 가치 팩터는 한국에서도 유의한 초과수익을 보이는 것으로 나타남(미국과 방향 일치).
- **BAB(Betting Against Beta) 비유의**: 저베타 종목이 고베타 대비 초과수익을 낸다는 BAB 전략은 한국 시장에서 통계적 유의성이 약하거나 재평가가 필요하다는 연구 존재.
- **극단적 수익률 주장에 대한 경계**: 조사 중 한국 소형주 대상 GP/A류 퀀트 전략이 연 60%+ CAGR을 주장하는 자료를 발견했으나, 방법론(생존편향 제거 여부, 유동성/체결가능성 반영 여부, 거래비용 반영 여부)이 불명확해 신뢰도가 낮다고 판단함 — **액면 그대로 신뢰하지 말 것**.

**시사점**: `quant-krx`로 전략을 만들 때 미국발 팩터(특히 모멘텀)를 그대로 가져오기보다, 가치·사이즈·역발상 조합을 우선 검토하고 반드시 자체 백테스트로 재검증해야 한다.

---

## 5. 공통 함정 — 왜 백테스트 수익률을 그대로 믿으면 안 되는가

1. **발표 후 알파 감소(McLean & Pontiff, 2016, *Journal of Finance*)**: 학술 논문으로 발표된 팩터는 발표 이후 평균적으로 초과수익의 약 3분의 1이 사라지고(발견 편향 제거 효과), 실제 상품화(ETF 등)된 이후에는 약 절반이 사라진다는 실증 연구. "알려진 전략일수록 미래 수익력이 약하다"는 강력한 근거.
2. **원저자 vs 독립 재검증 괴리**: Magic Formula(30.8% → 13~17%), Turtle Trading(80%+ → 재현 시 크게 하회) 등 위 표에서 보듯, 원저자/1차 자료의 수치와 제3자 독립 재현치 사이에 항상 상당한 괴리가 존재한다.
3. **생존편향(Survivorship Bias)**: 상장폐지·인덱스 편출 종목을 제외한 현재 시점 유니버스로 과거를 백테스트하면 수익률이 체계적으로 과대평가된다. 특히 소형주 전략에서 영향이 크다.
4. **수수료·슬리피지 미반영**: 학술 논문은 대개 거래비용을 반영하지 않거나 과소 반영한다. 회전율이 높은 전략(모멘텀, 단기 평균회귀)일수록 실제 순수익률 하락 폭이 크다.
5. **유동성·체결가능성**: 소형주·저유동성 종목 위주 전략은 백테스트상 가격으로 실제 체결이 불가능한 경우가 많다(특히 한국 소형주 GP/A류 주장 케이스, 4번 항목 참고).

---

## 6. `quant-krx` 팩터 플랫폼과의 연결점

현재 팩터 카탈로그(32종: 가격·기술 7 + 밸류에이션 11 + 재무제표 14)를 기준으로 볼 때:

- **바로 적용 가능**: Golden/Death Cross(`sma`), MACD 크로스(`macd`), RSI 과매도 반등(`rsi`), 볼린저 밴드 평균회귀(`bollinger`) — 이미 builtin Template로 제공됨. 절대 모멘텀(`momentum`, lookback=252/skip=21 기본값이 정확히 12-1 모멘텀 정의와 일치)도 builtin Template 제공.
- **밸류에이션 팩터만으로 근사 가능**: 저PER+고ROE(Buffett/퀄리티-밸류 근사), 저PER+저PBR(Graham식 딥밸류), 고배당(Dogs-of-Dow류) — `per`/`pbr`/`roe_approx`/`dividend_yield`는 모두 `required_data=valuation`이라 PyKrx 로그인만으로 실데이터 사용 가능.
- **현재는 데이터 제약으로 실사용 불가**: Magic Formula의 진짜 순위결합, Piotroski F-Score, GP/A, QMJ, ROIC 퀄리티 전략은 대부분 `required_data=financials`(재무제표) 팩터에 의존하는데, `DartFundamentalAdapter`가 아직 Deferred라 실제 데이터가 NaN으로 반환된다(`FixtureFundamentalAdapter`로 테스트만 가능).
- **엔진 한계로 재현 불가**: 워크스페이스의 Rule 엔진은 종목별 시계열 위에서 동작하는 boolean 조건(비교/크로스)이며, Magic Formula·F-Score처럼 유니버스 전체를 대상으로 한 **순위화·포트폴리오 선택**은 지원하지 않는다. 임계값 기반 근사만 가능하다.
- **새 팩터가 필요**: 52주 신고가 근접도(현재 `momentum`은 근접도가 아닌 총수익 모멘텀), 저변동성 팩터(실현변동성/베타), Donchian 채널 브레이크아웃(Turtle Trading)은 카탈로그에 없어 신규 Factor 구현이 선행되어야 한다.

세부 적용 가능 목록과 CLI 실행 예제는 [APPLICABLE_STRATEGIES_CLI_GUIDE.md](APPLICABLE_STRATEGIES_CLI_GUIDE.md) 참고.

---

## Sources

- [Richard Dennis Turtle Trading Strategy](https://trendspider.com/learning-center/richard-dennis-turtle-trading-strategy/)
- [Turtle Trading Strategy — Quantified Strategies](https://www.quantifiedstrategies.com/turtle-trading-strategy/)
- [Golden Cross Trading Strategy 20-Year Backtest](https://tosindicators.com/research/golden-cross-trading-strategy-20-year-backtest-results)
- [Golden Cross Trading Strategy — Quantified Strategies](https://www.quantifiedstrategies.com/golden-cross-trading-strategy/)
- [Does the Death Cross Actually Work? — Quantified Strategies](https://www.quantifiedstrategies.com/death-cross-in-trading/)
- [Testing the Golden Cross and Death Cross on the SPY — Cabot Wealth](https://www.cabotwealth.com/daily/how-to-invest/testing-the-golden-cross-and-death-cross-on-the-spy)
- [Does Academic Research Destroy Stock Return Predictability? (SSRN, McLean & Pontiff)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623)
- [McLean & Pontiff 전문 PDF](https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf)
- [한국 대안 인덱스 투자전략 연구 (KCI)](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART001877159)
- [한국주식시장 8요인 전통/스마트베타 비교 (KCI)](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART002930025)
- [한국주식시장 8요인 전통/스마트베타 비교 (DBpia)](https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE11215210)
- [한국주식시장 규모효과와 투자자 거래행태 (KCI)](https://www.kci.go.kr/kciportal/landing/article.kci?arti_id=ART003130705)
- [한국 역베타(BAB) 전략 재평가 (DBpia)](https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12149126)
- [시장이상현상 팩터 투자전략 성과분석 (KCI)](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003056534)
- [한국 소형주 GP/A 퀀트 백테스트(방법론 검증 필요, 참고용)](https://simpleinvest.co.kr/%ED%95%9C%EA%B5%AD-%EC%86%8C%ED%98%95%EC%A3%BC-%ED%80%80%ED%8A%B8-%ED%88%AC%EC%9E%90-%EC%A0%84%EB%9E%B5/)
