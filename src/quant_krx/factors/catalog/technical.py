from __future__ import annotations

import numpy as np
import pandas as pd

from quant_krx.factors.metadata import FactorCategory, FactorMetadata, ParamSpec
from quant_krx.factors.notes import FactorNote, attach_note
from quant_krx.factors.registry import register_factor


def _mark_warmup_nan(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].isna().any():
            attach_note(df, col, FactorNote.INSUFFICIENT_HISTORY)
    return df


class PriceFactor:
    """수정주가 종가 패스스루 (D2 — Rule/Formula가 가격 자체를 참조 가능)."""

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="price",
            display_name="가격(종가)",
            category=FactorCategory.PRICE,
            description="수정주가 종가 패스스루",
            params=(),
            output=("close",),
            required_data=("ohlcv",),
        )

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        result = pd.DataFrame({"close": data["close"]}, index=data.index)
        return result


class SMAFactor:
    def __init__(self, window: int = 20):
        self.window = window

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="sma",
            display_name="단순이동평균",
            category=FactorCategory.TREND,
            description="종가 단순이동평균",
            params=(ParamSpec("window", int, 20, "이동평균 기간(일)", min=1),),
            output=("sma",),
            required_data=("ohlcv",),
        )

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        result = pd.DataFrame({"sma": data["close"].rolling(self.window).mean()}, index=data.index)
        return _mark_warmup_nan(result)


class EMAFactor:
    def __init__(self, span: int = 20):
        self.span = span

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="ema",
            display_name="지수이동평균",
            category=FactorCategory.TREND,
            description="종가 지수이동평균",
            params=(ParamSpec("span", int, 20, "지수이동평균 기간(일)", min=1),),
            output=("ema",),
            required_data=("ohlcv",),
        )

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        ema = data["close"].ewm(span=self.span, adjust=False).mean()
        result = pd.DataFrame({"ema": ema}, index=data.index)
        return _mark_warmup_nan(result)


class RSIFactor:
    def __init__(self, window: int = 14):
        self.window = window

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="rsi",
            display_name="RSI",
            category=FactorCategory.MOMENTUM,
            description="상대강도지수(rolling 단순평균 변형)",
            params=(ParamSpec("window", int, 14, "RSI 계산 기간(일)", min=1),),
            output=("rsi",),
            required_data=("ohlcv",),
        )

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        delta = data["close"].diff()
        gain = delta.clip(lower=0).rolling(self.window).mean()
        loss = (-delta.clip(upper=0)).rolling(self.window).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        result = pd.DataFrame({"rsi": rsi}, index=data.index)
        return _mark_warmup_nan(result)


class MACDFactor:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="macd",
            display_name="MACD",
            category=FactorCategory.TREND,
            description="12/26 EMA 차이의 시그널선 교차(모멘텀)",
            params=(
                ParamSpec("fast", int, 12, "단기 EMA 기간", min=1),
                ParamSpec("slow", int, 26, "장기 EMA 기간", min=1),
                ParamSpec("signal", int, 9, "시그널선 EMA 기간", min=1),
            ),
            output=("macd", "signal"),
            required_data=("ohlcv",),
        )

    def validate_params(self, params: dict) -> tuple[str, ...]:
        if params["fast"] >= params["slow"]:
            return (f"fast({params['fast']})는 slow({params['slow']})보다 작아야 합니다.",)
        return ()

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        ema_fast = data["close"].ewm(span=self.fast, adjust=False).mean()
        ema_slow = data["close"].ewm(span=self.slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=self.signal, adjust=False).mean()
        result = pd.DataFrame({"macd": macd, "signal": signal}, index=data.index)
        return _mark_warmup_nan(result)


class BollingerFactor:
    def __init__(self, window: int = 20, num_std: float = 2.0):
        self.window = window
        self.num_std = num_std

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="bollinger",
            display_name="볼린저 밴드",
            category=FactorCategory.VOLATILITY,
            description="이동평균 ± num_std × 표준편차 밴드",
            params=(
                ParamSpec("window", int, 20, "이동평균 기간(일)", min=2),
                ParamSpec("num_std", float, 2.0, "표준편차 배수", min=0.0),
            ),
            output=("middle", "upper", "lower"),
            required_data=("ohlcv",),
        )

    def validate_params(self, params: dict) -> tuple[str, ...]:
        if params["num_std"] <= 0:
            return (f"num_std({params['num_std']})는 0보다 커야 합니다.",)
        return ()

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        middle = data["close"].rolling(self.window).mean()
        std = data["close"].rolling(self.window).std(ddof=1)
        upper = middle + self.num_std * std
        lower = middle - self.num_std * std
        result = pd.DataFrame({"middle": middle, "upper": upper, "lower": lower}, index=data.index)
        return _mark_warmup_nan(result)


class MomentumFactor:
    def __init__(self, lookback: int = 252, skip: int = 21):
        self.lookback = lookback
        self.skip = skip

    @property
    def metadata(self) -> FactorMetadata:
        return FactorMetadata(
            id="momentum",
            display_name="가격 모멘텀",
            category=FactorCategory.MOMENTUM,
            description="lookback-skip 가격 모멘텀 (Jegadeesh & Titman)",
            params=(
                ParamSpec("lookback", int, 252, "모멘텀 lookback 기간(일)", min=1),
                ParamSpec("skip", int, 21, "최근 skip 기간(일) 제외", min=0),
            ),
            output=("momentum",),
            required_data=("ohlcv",),
        )

    def validate_params(self, params: dict) -> tuple[str, ...]:
        if not (0 <= params["skip"] < params["lookback"]):
            return (
                f"skip({params['skip']})은 0 이상 "
                f"lookback({params['lookback']}) 미만이어야 합니다.",
            )
        return ()

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        momentum = data["close"].shift(self.skip) / data["close"].shift(self.lookback) - 1
        result = pd.DataFrame({"momentum": momentum}, index=data.index)
        return _mark_warmup_nan(result)


def register() -> None:
    register_factor("price", PriceFactor)
    register_factor("sma", SMAFactor)
    register_factor("ema", EMAFactor)
    register_factor("rsi", RSIFactor)
    register_factor("macd", MACDFactor)
    register_factor("bollinger", BollingerFactor)
    register_factor("momentum", MomentumFactor)
