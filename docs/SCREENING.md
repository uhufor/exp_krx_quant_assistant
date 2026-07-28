# 전종목 스크리닝

KOSPI/KOSDAQ 전 종목에서 조건에 맞는 종목을 찾습니다. watchlist와 무관하며, 조건은
AND/OR/NOT으로 조합할 수 있습니다.

| 관련 문서 | 내용 |
|---|---|
| [포트폴리오](PORTFOLIO.md) | 스크리닝 결과를 전략의 동적 유니버스로 연결 |
| [전략 정의](STRATEGY.md) | 팩터 카탈로그 32종 |
| [GUI](GUI.md) | 트리 편집기로 조건 구성 |

> 스크리닝은 전략 워크스페이스와 **별개의 독립 기능**입니다. 조건 정의는 저장되지만
> 실행 결과는 기본적으로 저장되지 않습니다(동적 유니버스 반복 실행 비용을 줄이기 위한
> 내부 캐시는 별도로 존재하며, 조건을 수정하면 자동 무효화됩니다).

---

## CLI 사용법

팩터·순위(거래대금/거래량/종가 Top-N)·팩터 순위(재무제표/밸류에이션 팩터 기반 Top-N,
`krx_dart` 사용 시 DART 재무제표 자동 증분 동기화)·시간창(최근 N봉 내 골든크로스 등)
조건을 조합한 JSON 정의로 KRX 전 종목(watchlist 무관)을 스크리닝합니다. Daily
파이프라인과 독립적이며 실행 결과는 저장되지 않습니다(조회 전용).

```bash
# 조건 생성/전체교체 (JSON 파일 또는 '-'로 stdin)
uv run python -m quant_krx screen-create my_screen.json

# 조건 조회 (rich 표/패널)
uv run python -m quant_krx screen-show my_screen

# 저장된 조건 목록
uv run python -m quant_krx screen-list

# 참조 무결성 검증(팩터 id·RankPredicate 컬럼 등, 실행 없이)
uv run python -m quant_krx screen-validate my_screen

# 조건 실행 → 통과 종목(코드+이름) 표 출력
uv run python -m quant_krx screen-run my_screen --as-of 2024-12-18 --data-source fixture

# 조건 전체 교체(부분 패치 없음) / 삭제
uv run python -m quant_krx screen-edit my_screen my_screen_v2.json
uv run python -m quant_krx screen-delete my_screen
```

`--data-source`는 `fixture`(기본값) | `krx_dart`(KRX+DART 실데이터) 중 선택합니다. 조건 JSON 스키마와
연산자/노드 종류는 [roadmap/EPIC_R03/](../roadmap/EPIC_R03/)(PRD/TRD/DESIGN R03), 팩터 순위
조건(FactorRankPredicate)과 실행 시점 증분 동기화는 [roadmap/EPIC_R04/](../roadmap/EPIC_R04/) 참고.


---

## 조건 종류

| 노드 | 설명 |
|---|---|
| 조건(비교/크로스) | 팩터 값 비교(`>`, `<`, `crosses_above` 등) |
| AND / OR / NOT | 조건 조합 |
| 기간 조건 | 최근 N봉 이내에 조건이 성립했는가 |
| 순위 조건 | 거래대금·거래량·종가 기준 Top-N |
| 팩터 순위 조건 | 재무제표·밸류에이션 팩터 기준 Top-N |

## 제외 필터

ETF·ETN·우선주·SPAC 4종을 지원합니다. 관리종목·투자경고·거래정지·정리매매·환기종목·
불성실공시 6종은 **선택 자체가 차단**되어 있습니다 — 데이터 소스가 이를 제공하지 않는데
선택만 가능하게 두면 "필터를 걸었다고 믿었지만 실제로는 걸리지 않는" 상태가 되기 때문입니다.

## 생존 편향 방지

과거 시점을 조회하면 **그 시점의 상장 종목 목록**을 기준으로 삼습니다. 현재 상장 종목만
후보로 두면 그 사이 상장폐지된 종목이 빠져 성과가 부풀려집니다. 실데이터로 검증한 결과
2020-03-02 기준 2,326종목 중 234개가 현재 목록에 없으며, 그 종목들의 과거 시세도 정상
조회됩니다(검증 상세: [roadmap/BACKLOG.md](../roadmap/BACKLOG.md)).
