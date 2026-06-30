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

    MAX_STALE_DAYS = 5  # 최근 N 거래일 이내 데이터가 없으면 stale

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
