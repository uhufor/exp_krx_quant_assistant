from __future__ import annotations

import pandas as pd

from quant_krx.factors.base import FactorInput
from quant_krx.factors.kernels import eps_growth_kernel, per_kernel, safe_divide_positive
from quant_krx.factors.metadata import FactorCategory, FactorMetadata
from quant_krx.factors.notes import FactorNote, attach_note, mark_if_nan, missing_input_frame
from quant_krx.factors.registry import register_factor


def _degrade_if_no_valuation(data: FactorInput, columns: tuple[str, ...]) -> pd.DataFrame | None:
    if data.valuation is None:
        return missing_input_frame(data.ohlcv.index, columns)
    return None


class PERFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="per", display_name="PER", category=FactorCategory.VALUE,
            description="주가수익비율 close/eps", output=("per",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame({"per": per_kernel(v["close"], v["eps"])}, index=v.index)
        return mark_if_nan(result, "per", FactorNote.NON_POSITIVE_DENOMINATOR)


class PBRFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="pbr", display_name="PBR", category=FactorCategory.VALUE,
            description="주가순자산비율 close/bps", output=("pbr",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame(
            {"pbr": safe_divide_positive(v["close"], v["bps"])}, index=v.index
        )
        return mark_if_nan(result, "pbr", FactorNote.NON_POSITIVE_DENOMINATOR)


class EarningsYieldFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="earnings_yield", display_name="이익수익률", category=FactorCategory.VALUE,
            description="eps/close", output=("earnings_yield",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame(
            {"earnings_yield": safe_divide_positive(v["eps"], v["close"])}, index=v.index
        )
        return mark_if_nan(result, "earnings_yield", FactorNote.NON_POSITIVE_DENOMINATOR)


class DividendYieldFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="dividend_yield", display_name="배당수익률", category=FactorCategory.VALUE,
            description="dps/close", output=("dividend_yield",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame(
            {"dividend_yield": safe_divide_positive(v["dps"], v["close"])}, index=v.index
        )
        return mark_if_nan(result, "dividend_yield", FactorNote.NON_POSITIVE_DENOMINATOR)


class EPSFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="eps", display_name="EPS", category=FactorCategory.QUALITY,
            description="주당순이익 패스스루", output=("eps",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame({"eps": v["eps"]}, index=v.index)
        return mark_if_nan(result, "eps", FactorNote.MISSING_INPUT)


class BPSFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="bps", display_name="BPS", category=FactorCategory.QUALITY,
            description="주당순자산 패스스루", output=("bps",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame({"bps": v["bps"]}, index=v.index)
        return mark_if_nan(result, "bps", FactorNote.MISSING_INPUT)


class ROEApproxFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="roe_approx", display_name="ROE(근사)", category=FactorCategory.QUALITY,
            description="eps/bps", output=("roe_approx",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame(
            {"roe_approx": safe_divide_positive(v["eps"], v["bps"])}, index=v.index
        )
        return mark_if_nan(result, "roe_approx", FactorNote.NON_POSITIVE_DENOMINATOR)


class PayoutRatioFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="payout_ratio", display_name="배당성향", category=FactorCategory.QUALITY,
            description="dps/eps", output=("payout_ratio",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame(
            {"payout_ratio": safe_divide_positive(v["dps"], v["eps"])}, index=v.index
        )
        return mark_if_nan(result, "payout_ratio", FactorNote.NON_POSITIVE_DENOMINATOR)


def _eps_growth_note(eps: pd.Series, growth: pd.Series) -> FactorNote:
    """NaN 사유 판별: 실제 비교 시도(직전 스텝 존재하는 변경점)가 한 번도 없었으면
    INSUFFICIENT_HISTORY(최초 스텝 이전과 동치), 시도가 있었는데도 결과가 NaN이면
    직전 스텝<=0으로 인한 NON_POSITIVE_DENOMINATOR로 판정한다.
    """
    prev_step = eps.shift(1)
    is_change = eps.ne(prev_step) & eps.notna()
    attempted_comparisons = int((is_change & prev_step.notna()).sum())
    if attempted_comparisons == 0:
        return FactorNote.INSUFFICIENT_HISTORY

    first_valid = growth.first_valid_index()
    if first_valid is None:
        return FactorNote.NON_POSITIVE_DENOMINATOR
    leading_nan_count = growth.index.get_loc(first_valid)
    return (
        FactorNote.INSUFFICIENT_HISTORY
        if growth.isna().sum() == leading_nan_count
        else FactorNote.NON_POSITIVE_DENOMINATOR
    )


class EPSGrowthFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="eps_growth", display_name="EPS 성장률", category=FactorCategory.GROWTH,
            description="직전 상이한 EPS 스텝 값 대비 증가율", output=("eps_growth",),
            required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        growth = eps_growth_kernel(v["eps"])
        result = pd.DataFrame({"eps_growth": growth}, index=v.index)
        if growth.isna().any():
            attach_note(result, "eps_growth", _eps_growth_note(v["eps"], growth))
        return result


class PEGFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="peg", display_name="PEG", category=FactorCategory.GROWTH,
            description="per / (eps_growth * 100)", output=("peg",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        per = per_kernel(v["close"], v["eps"])
        growth = eps_growth_kernel(v["eps"])
        peg = safe_divide_positive(per, growth * 100)
        result = pd.DataFrame({"peg": peg}, index=v.index)
        return mark_if_nan(result, "peg", FactorNote.NON_POSITIVE_DENOMINATOR)


class MarketCapFactor:
    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="market_cap", display_name="시가총액", category=FactorCategory.SIZE,
            description="시가총액 패스스루", output=("market_cap",), required_data=("valuation",),
        )

    def compute(self, data: FactorInput) -> pd.DataFrame:
        degraded = _degrade_if_no_valuation(data, self.metadata.output)
        if degraded is not None:
            return degraded
        v = data.valuation
        result = pd.DataFrame({"market_cap": v["market_cap"]}, index=v.index)
        return mark_if_nan(result, "market_cap", FactorNote.MISSING_INPUT)


def register() -> None:
    register_factor("per", PERFactor)
    register_factor("pbr", PBRFactor)
    register_factor("earnings_yield", EarningsYieldFactor)
    register_factor("dividend_yield", DividendYieldFactor)
    register_factor("eps", EPSFactor)
    register_factor("bps", BPSFactor)
    register_factor("roe_approx", ROEApproxFactor)
    register_factor("payout_ratio", PayoutRatioFactor)
    register_factor("eps_growth", EPSGrowthFactor)
    register_factor("peg", PEGFactor)
    register_factor("market_cap", MarketCapFactor)
