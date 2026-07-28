"""데이터 신선도 점검(D3).

"값이 비어 있는데 그걸 모르고 결과를 신뢰하는" 상황을 막기 위한 조회 전용 점검이다.
백테스트·스크리닝은 결측을 NaN으로 자연 degrade시키는데(프로젝트 전반의 원칙), 그 덕에
**조용히 잘못된 결론**이 나올 수 있다 — 예를 들어 DART 재무제표가 두 분기 밀려 있으면
저PER 스크리닝이 낡은 실적으로 종목을 고르고도 아무 경고를 내지 않는다.

이 모듈은 **판정만 하고 아무것도 고치지 않는다.** 수집·재시도는 각 수집 경로의 몫이고,
여기서 문제를 발견해도 실행을 중단시키지 않는다(매일 돌아야 하는 잡이 데이터 지연으로
멈추면 안 된다).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from quant_krx.data.coverage import (
    date_range_gaps,
    existing_valuation_coverage,
    is_financials_stale,
    latest_financials_period,
)
from quant_krx.storage.db import Database

# 점검 심각도. warn만 존재하는 이유는 위 docstring 참고 — 신선도 문제로 실행을 막지 않는다.
SEVERITY_OK = "ok"
SEVERITY_WARN = "warn"


@dataclass(frozen=True)
class FreshnessIssue:
    """한 가지 이상 징후."""

    kind: str        # valuation | financials | credentials | ohlcv
    message: str     # 사람이 읽는 한 줄
    affected: int = 0  # 영향받는 종목 수(자격증명 등 종목과 무관하면 0)


@dataclass(frozen=True)
class FreshnessReport:
    as_of: date
    checked_symbols: int = 0
    issues: tuple[FreshnessIssue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def severity(self) -> str:
        return SEVERITY_OK if self.ok else SEVERITY_WARN

    def summary(self) -> str:
        """리포트 상단에 넣을 한 줄. 정상이면 빈 문자열(호출부가 아예 생략하도록)."""
        if self.ok:
            return ""
        return " · ".join(i.message for i in self.issues)


def _check_credentials(needs_valuation: bool, needs_financials: bool) -> list[FreshnessIssue]:
    """자격증명 부재는 데이터가 **앞으로도** 안 들어온다는 뜻이라 별도로 짚는다."""
    issues: list[FreshnessIssue] = []
    if needs_valuation and not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        issues.append(
            FreshnessIssue("credentials", "KRX 자격증명 없음(밸류에이션 갱신 불가)")
        )
    if needs_financials and not os.getenv("DART_API_KEY"):
        issues.append(
            FreshnessIssue("credentials", "DART_API_KEY 없음(재무제표 갱신 불가)")
        )
    return issues


def check_freshness(
    db: Database,
    symbols: list[str],
    *,
    as_of: date,
    check_valuation: bool = True,
    check_financials: bool = True,
    missing_ohlcv: int = 0,
) -> FreshnessReport:
    """대상 종목의 데이터 신선도를 점검한다.

    `missing_ohlcv`는 호출부가 이미 알고 있는 "시세 수집 실패 종목 수"다 — OHLCV는 DB가
    아니라 provider에서 바로 조립되므로(백테스트 경로) 여기서 다시 조회하지 않고 받는다.
    """
    issues: list[FreshnessIssue] = []

    if missing_ohlcv > 0:
        issues.append(
            FreshnessIssue("ohlcv", f"시세 수집 실패 {missing_ohlcv}종목", missing_ohlcv)
        )

    if symbols:
        with db.cursor() as conn:
            if check_valuation:
                coverage = existing_valuation_coverage(conn, symbols)
                stale = [s for s in symbols if date_range_gaps(coverage.get(s), as_of, as_of)]
                if stale:
                    issues.append(
                        FreshnessIssue(
                            "valuation",
                            f"밸류에이션 {as_of} 기준 미확보 {len(stale)}종목",
                            len(stale),
                        )
                    )
            if check_financials:
                latest = latest_financials_period(conn, symbols)
                stale_fin = [s for s in symbols if is_financials_stale(latest.get(s), as_of)]
                if stale_fin:
                    issues.append(
                        FreshnessIssue(
                            "financials",
                            f"재무제표 최신 분기 지연 {len(stale_fin)}종목",
                            len(stale_fin),
                        )
                    )

    issues.extend(_check_credentials(check_valuation, check_financials))

    return FreshnessReport(
        as_of=as_of, checked_symbols=len(symbols), issues=tuple(issues)
    )
