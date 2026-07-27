"""백테스트 재실행 캐시 키 계산(P3).

캐시 키는 세 축의 합성이다. 하나라도 달라지면 다른 실행이므로 재계산한다.

1. **정의 지문**(`definition_fingerprint`) — 전략 + 전이 참조 Rule/Formula 폐포. 전략 본문을
   그대로 두고 참조하는 Rule만 고쳐도 결과가 달라지므로 폐포 전체를 해시한다.
2. **파라미터 지문**(`params_fingerprint`) — 종목·기간·수수료·슬리피지·데이터소스·벤치마크.
3. **커버리지 지문**(`coverage_fingerprint`) — 실제로 조립된 입력 데이터(`FactorInput`) 전체.

3번을 DB 커버리지 쿼리가 아니라 조립된 데이터에서 계산하는 이유: OHLCV는 DuckDB를 거치지
않고 `DataProvider`에서 직접 조립되므로(`workspace/data_loading.py::build_factor_input`)
DB만 보면 OHLCV 변화를 놓친다. 조립 결과를 해시하면 어떤 경로로 데이터가 바뀌든 지문이
따라 바뀌므로 낡은 결과를 캐시로 돌려줄 수 없다.

그 결과 캐시 조회는 **데이터 준비 이후**에 일어나고, 절감되는 비용은 팩터 계산과 vectorbt
실행분이다(데이터 수집 자체의 절감은 R04의 커버리지 바이패스가 이미 담당한다).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import pandas as pd

from quant_krx.factors import FactorInput


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    """키 정렬 + 공백 제거 정규 직렬화 — 딕셔너리 순서가 지문을 바꾸지 않게 한다."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def definition_fingerprint(bundle_dict: dict[str, Any]) -> str:
    """전략 + 전이 참조 Rule/Formula 폐포(StrategyBundle.to_dict())의 해시.

    `WorkspaceService._collect_bundle`이 Export/Template용으로 이미 폐포를 수집하므로 그
    산출물을 그대로 쓴다 — 폐포 수집 로직을 두 벌 두면 드리프트가 생긴다.
    """
    return _sha256(_canonical_json(bundle_dict))


def params_fingerprint(
    *,
    symbols: list[str],
    start: date | None,
    end: date | None,
    fees: float,
    slippage: float,
    data_source: str,
    benchmark: str | None,
) -> str:
    """실행 파라미터 해시. symbols는 정렬하지 않는다 — 순서가 대표 종목 선정에 영향을 준다."""
    return _sha256(
        _canonical_json(
            {
                "symbols": list(symbols),
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "fees": fees,
                "slippage": slippage,
                "data_source": data_source,
                "benchmark": benchmark,
            }
        )
    )


def _frame_digest(df: pd.DataFrame | None) -> str:
    """DataFrame 내용 전체의 해시. 행 하나만 바뀌어도 값이 달라진다.

    요약 통계(행 수·마지막 날짜)가 아니라 전체 해시를 쓰는 이유: 증분 수집이 과거 구간의
    값을 정정하는 경우(DART 정정공시 등) 요약만으로는 변화를 감지하지 못해 낡은 결과를
    캐시 히트로 돌려주게 된다. `hash_pandas_object`는 C 구현이라 이 크기에서는 저렴하다.
    """
    if df is None or df.empty:
        return "empty"
    ordered = df.sort_index()
    ordered = ordered[sorted(ordered.columns)]
    index_hash = pd.util.hash_pandas_object(ordered.index, index=False)
    value_hash = pd.util.hash_pandas_object(ordered, index=True)
    combined = pd.concat([index_hash, value_hash], ignore_index=True)
    return hashlib.sha256(combined.values.tobytes()).hexdigest()


def coverage_fingerprint(
    data: dict[str, FactorInput], benchmark_df: pd.DataFrame | None = None
) -> str:
    """조립된 백테스트 입력 데이터 전체의 해시(종목별 ohlcv/valuation/financials + 벤치마크).

    벤치마크 시계열도 포함한다 — 심볼명(params 지문)이 같아도 수집된 벤치마크 데이터가
    달라지면 초과수익률이 달라지기 때문이다.
    """
    per_symbol = {
        symbol: {
            "ohlcv": _frame_digest(factor_input.ohlcv),
            "valuation": _frame_digest(factor_input.valuation),
            "financials": _frame_digest(factor_input.financials),
        }
        for symbol, factor_input in sorted(data.items())
    }
    return _sha256(
        _canonical_json({"symbols": per_symbol, "benchmark": _frame_digest(benchmark_df)})
    )


def cache_key(definition: str, params: str, coverage: str) -> str:
    """세 지문의 합성 키 — 이 값이 같으면 결과가 같음이 보장된다(결정론 불변식 전제)."""
    return _sha256(_canonical_json([definition, params, coverage]))
