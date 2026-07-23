from __future__ import annotations

import re

from quant_krx.data.base import DataProvider
from quant_krx.screening import definition as _definition
from quant_krx.screening.errors import EmptyUniverseError, UnsupportedFilterError

_SUPPORTED_FILTERS = frozenset({"etf", "etn", "preferred", "spac"})

# 한국 우선주 명명 관례: "삼성전자우"(1우선주), "삼성전자우B"(2우선주 계열),
# "현대차2우B"/"삼성전기1우"(발행 순번 숫자 포함), 드물게 "OO우선주"로 끝나는 표기까지
# 포괄한다. 종목명 끝부분 매칭이므로 "미래에셋대우"처럼 우연히 "우"로 끝나는 보통주는
# 오탐 가능성이 있으나(명명 관례상 감수 가능한 범위), 이는 이 함수의 알려진 한계다.
_PREFERRED_STOCK_SUFFIX_RE = re.compile(r"(?:\d*우B?|우선주)$")

_SPAC_NAME_MARKER = "기업인수목적"


def _is_preferred_stock(name: str) -> bool:
    """종목명이 한국 우선주 명명 관례(우/우B/숫자+우/우선주)로 끝나는지 판정하는 순수 함수."""
    return bool(_PREFERRED_STOCK_SUFFIX_RE.search(name))


def _is_spac(name: str) -> bool:
    """종목명에 기업인수목적회사(SPAC) 표기가 포함되는지 판정하는 순수 함수."""
    return _SPAC_NAME_MARKER in name


def _krx_stock():
    """Lazy import of pykrx.stock to avoid pkg_resources import at module load."""
    from pykrx import stock as _stock  # noqa: PLC0415

    return _stock


def resolve_scan_universe(
    provider: DataProvider, exclusion_filters: frozenset[str]
) -> list[str]:
    """스캔 유니버스를 해석한다: 전체 종목에서 exclusion_filters 4종을 차감한다.

    ScanUniverse가 이미 생성 시점에 미지원 필터 6종을 거부하지만(definition.py),
    이 함수는 ScanUniverse를 거치지 않고 직접 호출될 가능성에 대비해 동일 체크를
    한 번 더 수행한다(이중 방어).
    """
    rejected = frozenset(exclusion_filters) & _definition._UNSUPPORTED_FILTERS
    if rejected:
        raise UnsupportedFilterError(
            f"미지원 제외 필터가 포함되었습니다: {sorted(rejected)}"
            f"(예약 미지원: {sorted(_definition._UNSUPPORTED_FILTERS)})"
        )

    symbols = set(provider.list_symbols(market="KRX"))
    raw_symbol_count = len(symbols)

    if "etf" in exclusion_filters:
        stock = _krx_stock()
        symbols -= set(stock.get_etf_ticker_list())

    if "etn" in exclusion_filters:
        stock = _krx_stock()
        symbols -= set(stock.get_etn_ticker_list())

    if exclusion_filters & {"preferred", "spac"}:
        metadata = provider.fetch_metadata(sorted(symbols))
        if "preferred" in exclusion_filters:
            symbols = {
                s for s in symbols if not _is_preferred_stock(metadata.get(s, {}).get("name", ""))
            }
        if "spac" in exclusion_filters:
            symbols = {
                s for s in symbols if not _is_spac(metadata.get(s, {}).get("name", ""))
            }

    if not symbols:
        if raw_symbol_count == 0:
            raise EmptyUniverseError(
                "provider.list_symbols()가 종목을 하나도 반환하지 않았습니다"
                "(휴장일/공휴일이거나 데이터 소스 연결에 실패했을 수 있습니다 —"
                " --data-source pykrx 사용 시 네트워크·KRX 서버 상태를,"
                " fixture 사용 시 fixture 데이터를 확인하세요)"
            )
        raise EmptyUniverseError(
            f"제외 필터 적용 후 유니버스가 비었습니다(필터 전 {raw_symbol_count}종목,"
            f" 적용된 필터: {sorted(exclusion_filters)})"
        )

    return sorted(symbols)
