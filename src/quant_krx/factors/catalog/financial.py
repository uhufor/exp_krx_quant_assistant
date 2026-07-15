from __future__ import annotations

import pandas as pd

from quant_krx.factors.asof import align_financials, merge_asof_daily, unify_financials_scope
from quant_krx.factors.base import FactorInput
from quant_krx.factors.kernels import (
    quarterly_yoy_growth,
    safe_divide_nonzero,
    safe_divide_positive,
)
from quant_krx.factors.metadata import FactorCategory, FactorMetadata
from quant_krx.factors.notes import FactorNote, attach_note, mark_if_nan, missing_input_frame
from quant_krx.factors.registry import register_factor


def _degrade_if_missing(
    data: FactorInput, columns: tuple[str, ...], *, needs_valuation: bool = False
) -> pd.DataFrame | None:
    if data.financials is None or (needs_valuation and data.valuation is None):
        return missing_input_frame(data.ohlcv.index, columns)
    return None


class PSRFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="psr", display_name="PSR", category=FactorCategory.VALUE,
            description="market_cap/revenue", output=("psr",),
            required_data=("valuation", "financials"),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output, needs_valuation=True)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        psr = safe_divide_positive(data.valuation["market_cap"], aligned["revenue"])
        result = pd.DataFrame({"psr": psr}, index=data.ohlcv.index)
        return mark_if_nan(result, "psr", FactorNote.NON_POSITIVE_DENOMINATOR)


class PCRFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="pcr", display_name="PCR", category=FactorCategory.VALUE,
            description="market_cap/operating_cash_flow", output=("pcr",),
            required_data=("valuation", "financials"),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output, needs_valuation=True)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        pcr = safe_divide_positive(data.valuation["market_cap"], aligned["operating_cash_flow"])
        result = pd.DataFrame({"pcr": pcr}, index=data.ohlcv.index)
        return mark_if_nan(result, "pcr", FactorNote.NON_POSITIVE_DENOMINATOR)


class EVEBITDAFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="ev_ebitda", display_name="EV/EBITDA", category=FactorCategory.VALUE,
            description="(market_cap+total_debt-cash)/(operating_income+D&A)",
            output=("ev_ebitda",), required_data=("valuation", "financials"),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output, needs_valuation=True)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        ev = (
            data.valuation["market_cap"]
            + aligned["total_debt"]
            - aligned["cash_and_equivalents"]
        )
        ebitda = aligned["operating_income"] + aligned["depreciation_amortization"]
        ev_ebitda = safe_divide_positive(ev, ebitda)
        result = pd.DataFrame({"ev_ebitda": ev_ebitda}, index=data.ohlcv.index)
        return mark_if_nan(result, "ev_ebitda", FactorNote.NON_POSITIVE_DENOMINATOR)


class ROAFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="roa", display_name="ROA", category=FactorCategory.QUALITY,
            description="net_income/total_assets", output=("roa",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        roa = safe_divide_positive(aligned["net_income"], aligned["total_assets"])
        result = pd.DataFrame({"roa": roa}, index=data.ohlcv.index)
        return mark_if_nan(result, "roa", FactorNote.NON_POSITIVE_DENOMINATOR)


class ROICFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="roic", display_name="ROIC", category=FactorCategory.QUALITY,
            description="operating_income*(1-tax_rate)/invested_capital", output=("roic",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        pretax = aligned["pretax_income"]
        raw_tax_rate = (aligned["income_tax"] / pretax).where(pretax != 0, 0.0)
        tax_rate = raw_tax_rate.clip(lower=0.0, upper=1.0)
        nopat = aligned["operating_income"] * (1 - tax_rate)
        roic = safe_divide_positive(nopat, aligned["invested_capital"])
        result = pd.DataFrame({"roic": roic}, index=data.ohlcv.index)
        return mark_if_nan(result, "roic", FactorNote.NON_POSITIVE_DENOMINATOR)


class GrossMarginFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="gross_margin", display_name="매출총이익률", category=FactorCategory.QUALITY,
            description="gross_profit/revenue", output=("gross_margin",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        margin = safe_divide_positive(aligned["gross_profit"], aligned["revenue"])
        result = pd.DataFrame({"gross_margin": margin}, index=data.ohlcv.index)
        return mark_if_nan(result, "gross_margin", FactorNote.NON_POSITIVE_DENOMINATOR)


class OperatingMarginFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="operating_margin", display_name="영업이익률", category=FactorCategory.QUALITY,
            description="operating_income/revenue", output=("operating_margin",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        margin = safe_divide_positive(aligned["operating_income"], aligned["revenue"])
        result = pd.DataFrame({"operating_margin": margin}, index=data.ohlcv.index)
        return mark_if_nan(result, "operating_margin", FactorNote.NON_POSITIVE_DENOMINATOR)


class NetMarginFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="net_margin", display_name="순이익률", category=FactorCategory.QUALITY,
            description="net_income/revenue", output=("net_margin",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        margin = safe_divide_positive(aligned["net_income"], aligned["revenue"])
        result = pd.DataFrame({"net_margin": margin}, index=data.ohlcv.index)
        return mark_if_nan(result, "net_margin", FactorNote.NON_POSITIVE_DENOMINATOR)


class GPToAssetsFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="gp_to_assets", display_name="총자산 대비 매출총이익",
            category=FactorCategory.QUALITY,
            description="gross_profit/total_assets", output=("gp_to_assets",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        ratio = safe_divide_positive(aligned["gross_profit"], aligned["total_assets"])
        result = pd.DataFrame({"gp_to_assets": ratio}, index=data.ohlcv.index)
        return mark_if_nan(result, "gp_to_assets", FactorNote.NON_POSITIVE_DENOMINATOR)


def _yoy_growth_aligned(data: FactorInput, column: str) -> pd.Series:
    unified = unify_financials_scope(data.financials)
    unified = unified.sort_values(["fiscal_year", "fiscal_quarter"]).reset_index(drop=True)
    growth_col = f"__{column}_growth"
    unified[growth_col] = quarterly_yoy_growth(unified, column)
    aligned = merge_asof_daily(unified, data.ohlcv.index)
    return aligned[growth_col]


def _growth_note(financials: pd.DataFrame, column: str, growth: pd.Series) -> FactorNote:
    """4분기 이력 미달(INSUFFICIENT_HISTORY) vs 4분기 전 값<=0(NON_POSITIVE_DENOMINATOR) 판별."""
    unified = unify_financials_scope(financials)
    unified = unified.sort_values(["fiscal_year", "fiscal_quarter"])
    has_4q_history = len(unified) > 4
    if not has_4q_history:
        return FactorNote.INSUFFICIENT_HISTORY
    prior = unified[column].shift(4)
    if (prior.dropna() <= 0).any():
        return FactorNote.NON_POSITIVE_DENOMINATOR
    return FactorNote.INSUFFICIENT_HISTORY


class RevenueGrowthFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="revenue_growth", display_name="매출 성장률(YoY)", category=FactorCategory.GROWTH,
            description="전년 동기 분기 대비 매출 증가율", output=("revenue_growth",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        growth = _yoy_growth_aligned(data, "revenue")
        result = pd.DataFrame({"revenue_growth": growth.values}, index=data.ohlcv.index)
        if growth.isna().any():
            attach_note(
                result, "revenue_growth", _growth_note(data.financials, "revenue", growth)
            )
        return result


class OpIncomeGrowthFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="op_income_growth", display_name="영업이익 성장률(YoY)",
            category=FactorCategory.GROWTH,
            description="전년 동기 분기 대비 영업이익 증가율", output=("op_income_growth",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        growth = _yoy_growth_aligned(data, "operating_income")
        result = pd.DataFrame({"op_income_growth": growth.values}, index=data.ohlcv.index)
        if growth.isna().any():
            attach_note(
                result, "op_income_growth",
                _growth_note(data.financials, "operating_income", growth),
            )
        return result


class DebtToEquityFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="debt_to_equity", display_name="부채비율", category=FactorCategory.STABILITY,
            description="total_debt/total_equity", output=("debt_to_equity",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        ratio = safe_divide_positive(aligned["total_debt"], aligned["total_equity"])
        result = pd.DataFrame({"debt_to_equity": ratio}, index=data.ohlcv.index)
        return mark_if_nan(result, "debt_to_equity", FactorNote.NON_POSITIVE_DENOMINATOR)


class CurrentRatioFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="current_ratio", display_name="유동비율", category=FactorCategory.STABILITY,
            description="current_assets/current_liabilities", output=("current_ratio",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        ratio = safe_divide_positive(aligned["current_assets"], aligned["current_liabilities"])
        result = pd.DataFrame({"current_ratio": ratio}, index=data.ohlcv.index)
        return mark_if_nan(result, "current_ratio", FactorNote.NON_POSITIVE_DENOMINATOR)


class InterestCoverageFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="interest_coverage", display_name="이자보상배율", category=FactorCategory.STABILITY,
            description="operating_income/interest_expense", output=("interest_coverage",),
            required_data=("financials",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_missing(data, self.metadata.output)
        if degraded is not None:
            return degraded
        aligned = align_financials(data.financials, data.ohlcv.index)
        ratio = safe_divide_nonzero(aligned["operating_income"], aligned["interest_expense"])
        result = pd.DataFrame({"interest_coverage": ratio}, index=data.ohlcv.index)
        return mark_if_nan(result, "interest_coverage", FactorNote.ZERO_DENOMINATOR)


def register() -> None:
    register_factor("psr", PSRFactor)
    register_factor("pcr", PCRFactor)
    register_factor("ev_ebitda", EVEBITDAFactor)
    register_factor("roa", ROAFactor)
    register_factor("roic", ROICFactor)
    register_factor("gross_margin", GrossMarginFactor)
    register_factor("operating_margin", OperatingMarginFactor)
    register_factor("net_margin", NetMarginFactor)
    register_factor("gp_to_assets", GPToAssetsFactor)
    register_factor("revenue_growth", RevenueGrowthFactor)
    register_factor("op_income_growth", OpIncomeGrowthFactor)
    register_factor("debt_to_equity", DebtToEquityFactor)
    register_factor("current_ratio", CurrentRatioFactor)
    register_factor("interest_coverage", InterestCoverageFactor)
