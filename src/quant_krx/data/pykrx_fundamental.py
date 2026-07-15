from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import date

import pandas as pd


def _krx_stock():
    """pykrx.stock의 lazy import. 모듈 레벨 임포트 시 setuptools 82와 pkg_resources 충돌 회피
    (기존 pykrx_adapter.py 관례 계승)."""
    from pykrx import stock as _stock  # noqa: PLC0415

    return _stock


class PyKrxFundamentalAdapter:
    """PyKrx 기반 밸류에이션 어댑터. 재무제표(fetch_financials)는 지원하지 않는다
    (DartFundamentalAdapter 사용, Deferred)."""

    @property
    def source_name(self) -> str:
        return "PyKrx"

    def fetch_valuation(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        # KRX_ID/KRX_PW 미설정은 확정적 설정 오류이므로 즉시 명확하게 실패시킨다. 반면
        # 자격증명이 있는데도 특정 구간(예: 당일 — KRX가 장마감 후 배치로 발행)이 빈
        # 응답이면 그건 로그인 문제가 아니라 "아직 미발표"이므로 하드 실패시키지 않고
        # 건너뛴다 — 결측은 NaN으로 자연 처리하는 이 프로젝트의 기존 원칙과 동일하다.
        if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
            raise RuntimeError(
                "PyKrx 밸류에이션/시가총액 조회에는 KRX(data.krx.co.kr) 로그인이 필요합니다. "
                "환경변수 KRX_ID/KRX_PW를 설정하세요."
            )
        s = _krx_stock()
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        frames = []
        for symbol in symbols:
            try:
                fundamental = s.get_market_fundamental_by_date(start_str, end_str, symbol)
                cap = s.get_market_cap_by_date(start_str, end_str, symbol)
                ohlcv = s.get_market_ohlcv_by_date(start_str, end_str, symbol)
            except Exception:
                continue
            if fundamental.empty or cap.empty:
                continue
            merged = self._merge_valuation(symbol, fundamental, cap, ohlcv)
            if not merged.empty:
                frames.append(merged)
        if not frames:
            return pd.DataFrame(
                columns=[
                    "symbol", "date", "close", "per", "pbr", "eps", "bps", "div",
                    "dps", "market_cap", "shares",
                ]
            )
        return pd.concat(frames, ignore_index=True)

    def fetch_financials(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError(
            "PyKrxFundamentalAdapter는 재무제표를 지원하지 않습니다. "
            "재무제표 수집은 DartFundamentalAdapter를 사용하십시오(현재 Deferred 상태)."
        )

    @staticmethod
    def _merge_valuation(
        symbol: str, fundamental: pd.DataFrame, cap: pd.DataFrame, ohlcv: pd.DataFrame
    ) -> pd.DataFrame:
        fundamental = fundamental.rename(
            columns={"BPS": "bps", "PER": "per", "PBR": "pbr", "EPS": "eps",
                     "DIV": "div", "DPS": "dps"}
        )
        cap = cap.rename(columns={"시가총액": "market_cap", "상장주식수": "shares"})
        ohlcv = ohlcv.rename(columns={"종가": "close", "Close": "close"})

        merged = fundamental.join(cap[["market_cap", "shares"]], how="inner")
        merged = merged.join(ohlcv[["close"]], how="inner")
        merged.index = pd.to_datetime(merged.index)
        merged = merged.reset_index(names="date")
        merged["symbol"] = symbol
        cols = [
            "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps",
            "market_cap", "shares",
        ]
        return merged[cols]
