from __future__ import annotations

# catalog import 시점에 32종 register_factor 호출이 트리거된다.
from . import catalog  # noqa: E402, F401
from .base import Factor, FactorInput
from .dispatch import compute_factor
from .errors import (
    DuplicateFactorError,
    FactorError,
    FactorMetadataMismatchError,
    ParamValidationError,
    UnknownFactorError,
)
from .metadata import FactorCategory, FactorMetadata, ParamSpec
from .notes import FactorNote, get_factor_notes
from .registry import get_factor, list_factors, register_factor

__all__ = [
    "Factor",
    "FactorInput",
    "compute_factor",
    "DuplicateFactorError",
    "FactorError",
    "FactorMetadataMismatchError",
    "ParamValidationError",
    "UnknownFactorError",
    "FactorCategory",
    "FactorMetadata",
    "ParamSpec",
    "FactorNote",
    "get_factor_notes",
    "get_factor",
    "list_factors",
    "register_factor",
]
