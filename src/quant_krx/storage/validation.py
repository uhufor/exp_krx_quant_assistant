from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class ValidationResult:
    symbol: str
    ok: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0

    def __str__(self) -> str:
        status = "OK" if self.ok else "FAIL"
        parts = [f"[{status}] {self.symbol} ({self.row_count} rows)"]
        parts.extend(f"  ERROR: {i}" for i in self.issues)
        parts.extend(f"  WARN:  {w}" for w in self.warnings)
        return "\n".join(parts)


class DataValidator:
    """OHLCV DataFrame 품질 검증."""

    MAX_STALE_DAYS = 5          # 최근 N 거래일 이내 데이터가 없으면 stale
    MIN_TRADING_DAYS = 60       # MA 교차(60일) 최소 요구치 — 미달 시 오류
    FULL_STRATEGY_DAYS = 273    # 12-1 모멘텀 워밍업(252+21) — 미달 시 경고

    def validate(
        self, symbol: str, df: pd.DataFrame, as_of: date | None = None
    ) -> ValidationResult:
        issues: list[str] = []
        warnings: list[str] = []

        if df.empty:
            return ValidationResult(symbol=symbol, ok=False, issues=["Empty DataFrame"])

        required = {"date", "close"}
        missing = required - set(df.columns)
        if missing:
            return ValidationResult(symbol=symbol, ok=False, issues=[f"Missing columns: {missing}"])

        # 음수/0 가격
        if (df["close"] <= 0).any():
            issues.append("Non-positive close price")

        # 중복 날짜
        if df["date"].duplicated().any():
            issues.append(f"Duplicate dates: {df['date'].duplicated().sum()} rows")

        # 오래된 데이터
        if as_of is not None:
            latest = pd.to_datetime(df["date"]).max().date()
            delta = (as_of - latest).days
            if delta > self.MAX_STALE_DAYS * 2:  # 주말/공휴일 고려
                warnings.append(f"Stale data: latest={latest}, as_of={as_of}, gap={delta}d")

        # NaN close
        nan_count = df["close"].isna().sum()
        if nan_count > 0:
            issues.append(f"NaN close prices: {nan_count} rows")

        # 히스토리 길이 검사
        row_count = len(df)
        if row_count < self.MIN_TRADING_DAYS:
            issues.append(
                f"히스토리 부족: {row_count}일 (최소 {self.MIN_TRADING_DAYS}일 필요). "
                "상장 기간이 너무 짧거나 데이터 수집 오류일 수 있음."
            )
        elif row_count < self.FULL_STRATEGY_DAYS:
            actual_start = pd.to_datetime(df["date"]).min().date()
            warnings.append(
                f"짧은 히스토리: {row_count}일 ({actual_start} 이후). "
                f"모멘텀 전략은 {self.FULL_STRATEGY_DAYS}일 이상 필요 — 신호가 제한될 수 있음."
            )

        ok = len(issues) == 0
        return ValidationResult(
            symbol=symbol,
            ok=ok,
            issues=issues,
            warnings=warnings,
            row_count=len(df),
        )

    def validate_batch(
        self, data: dict[str, pd.DataFrame], as_of: date | None = None
    ) -> dict[str, ValidationResult]:
        return {sym: self.validate(sym, df, as_of) for sym, df in data.items()}
