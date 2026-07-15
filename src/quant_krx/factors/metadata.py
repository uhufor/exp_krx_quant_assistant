from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FactorCategory(str, Enum):
    PRICE = "price"
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    MEAN_REVERSION = "mean_reversion"
    VOLUME = "volume"
    VALUE = "value"
    QUALITY = "quality"
    GROWTH = "growth"
    STABILITY = "stability"
    SIZE = "size"


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: type[int] | type[float]
    default: int | float
    description: str
    min: int | float | None = None
    max: int | float | None = None
    choices: tuple[int | float, ...] | None = None


@dataclass(frozen=True)
class FactorMetadata:
    id: str
    display_name: str
    category: FactorCategory
    description: str
    params: tuple[ParamSpec, ...] = ()
    output: tuple[str, ...] = ()
    required_data: tuple[str, ...] = ("ohlcv",)
