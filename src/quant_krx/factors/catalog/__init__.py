from __future__ import annotations

from . import financial, technical, valuation

technical.register()
valuation.register()
financial.register()
