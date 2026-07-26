from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from quant_krx.data.dart_account_mapping import extract_financial_fields
from quant_krx.data.dart_corp_code import DartCorpCodeResolver, _parse_corp_code_zip
from quant_krx.data.dart_fundamental import DartFundamentalAdapter
from quant_krx.data.pykrx_fundamental import PyKrxFundamentalAdapter


def _build_corp_code_zip(rows: list[dict]) -> bytes:
    xml_items = "".join(
        "<list>"
        f"<corp_code>{r['corp_code']}</corp_code>"
        f"<corp_name>{r.get('corp_name', '')}</corp_name>"
        f"<stock_code>{r.get('stock_code', '')}</stock_code>"
        f"<modify_date>{r['modify_date']}</modify_date>"
        "</list>"
        for r in rows
    )
    xml = f"<result>{xml_items}</result>".encode()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, *, content: bytes = b"", json_data: dict | None = None):
        self.content = content
        self._json = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json


class _RoutingFakeClient:
    """corp_code/fnltt 엔드포인트를 params로 구분해 응답하는 테스트 전용 더미 클라이언트."""

    def __init__(
        self,
        *,
        corp_code_zip: bytes = b"",
        fnltt_responses: dict[tuple[str, str], dict] | None = None,
    ):
        self._corp_code_zip = corp_code_zip
        self._fnltt_responses = fnltt_responses or {}
        self.corp_code_calls = 0
        self.fnltt_calls: list[tuple[str, str]] = []

    def get(self, url: str, params: dict | None = None) -> _FakeResponse:
        params = params or {}
        if url.endswith("corpCode.xml"):
            self.corp_code_calls += 1
            return _FakeResponse(content=self._corp_code_zip)
        key = (params["reprt_code"], params["fs_div"])
        self.fnltt_calls.append(key)
        payload = self._fnltt_responses.get(key, {"status": "013", "message": "데이터없음"})
        return _FakeResponse(json_data=payload)


def test_pykrx_merge_valuation_shapes_columns_correctly():
    fundamental = pd.DataFrame(
        {"BPS": [46000.0], "PER": [10.0], "PBR": [1.5], "EPS": [7000.0],
         "DIV": [0.02], "DPS": [1400.0]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    cap = pd.DataFrame(
        {"시가총액": [1e12], "거래량": [1000], "거래대금": [1e8], "상장주식수": [1e7]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    ohlcv = pd.DataFrame(
        {"시가": [69000.0], "고가": [70000.0], "저가": [68500.0], "종가": [70000.0],
         "거래량": [1000]},
        index=pd.to_datetime(["2024-01-02"]),
    )

    merged = PyKrxFundamentalAdapter._merge_valuation("005930", fundamental, cap, ohlcv)

    assert set(merged.columns) == {
        "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps",
        "market_cap", "shares",
    }
    assert merged["symbol"].iloc[0] == "005930"
    assert merged["close"].iloc[0] == 70000.0
    assert merged["market_cap"].iloc[0] == 1e12


def test_pykrx_fetch_financials_raises_not_implemented():
    adapter = PyKrxFundamentalAdapter()
    with pytest.raises(NotImplementedError, match="재무제표"):
        adapter.fetch_financials(["005930"], date(2024, 1, 1), date(2024, 1, 31))


def test_dart_adapter_requires_api_key(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DART_API_KEY"):
        DartFundamentalAdapter()


def test_dart_fetch_valuation_raises_not_implemented(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "dummy")
    adapter = DartFundamentalAdapter(client=_RoutingFakeClient())
    with pytest.raises(NotImplementedError, match="밸류에이션"):
        adapter.fetch_valuation(["005930"], date(2024, 1, 1), date(2024, 1, 31))


def test_dart_account_mapping_extracts_and_derives_invested_capital():
    rows = [
        ("BS", "ifrs-full_Assets", "자산총계", "1000"),
        ("BS", "ifrs-full_Liabilities", "부채총계", "400"),
        ("BS", "ifrs-full_Equity", "자본총계", "600"),
        ("IS", "ifrs-full_Revenue", "매출액", "500"),
        ("IS", "dart_OperatingIncomeLoss", "영업이익", "50"),
        ("CF", "", "감가상각비", "10"),
        ("CF", "", "무형자산상각비", "5"),
    ]
    records = pd.DataFrame(rows, columns=["sj_div", "account_id", "account_nm", "thstrm_amount"])

    values = extract_financial_fields(records)

    assert values["total_assets"] == 1000.0
    assert values["total_debt"] == 400.0
    assert values["total_equity"] == 600.0
    assert values["revenue"] == 500.0
    assert values["operating_income"] == 50.0
    assert values["depreciation_amortization"] == 15.0  # 감가상각비+무형자산상각비 합산
    assert values["invested_capital"] == 1000.0  # 파생: total_assets 그대로 대입
    assert "interest_expense" not in values  # 미매칭 필드는 결과에서 제외(NaN 처리는 호출부)


def test_parse_corp_code_zip_filters_unlisted_companies():
    zip_bytes = _build_corp_code_zip(
        [
            {
                "corp_code": "00126380", "corp_name": "삼성전자",
                "stock_code": "005930", "modify_date": "20260101",
            },
            {
                "corp_code": "00164779", "corp_name": "비상장법인",
                "stock_code": "", "modify_date": "20260101",
            },
        ]
    )

    df = _parse_corp_code_zip(zip_bytes)

    assert list(df["stock_code"]) == ["005930"]
    assert df.iloc[0]["corp_code"] == "00126380"


def test_corp_code_resolver_caches_and_skips_refetch_when_fresh(tmp_path):
    zip_bytes = _build_corp_code_zip(
        [{"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930",
          "modify_date": date.today().strftime("%Y%m%d")}]
    )
    client = _RoutingFakeClient(corp_code_zip=zip_bytes)
    resolver = DartCorpCodeResolver("dummy", cache_path=tmp_path / "corp.parquet", client=client)

    first = resolver.resolve(["005930"])
    second = resolver.resolve(["005930"])

    assert first == {"005930": "00126380"}
    assert second == {"005930": "00126380"}
    assert client.corp_code_calls == 1  # 신선한 캐시는 재다운로드하지 않는다


def test_corp_code_resolver_excludes_unresolvable_symbol_after_retry(tmp_path):
    zip_bytes = _build_corp_code_zip(
        [{"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930",
          "modify_date": date.today().strftime("%Y%m%d")}]
    )
    client = _RoutingFakeClient(corp_code_zip=zip_bytes)
    resolver = DartCorpCodeResolver("dummy", cache_path=tmp_path / "corp.parquet", client=client)

    result = resolver.resolve(["005930", "999999"])

    assert result == {"005930": "00126380"}
    assert client.corp_code_calls == 2  # 최초 조회 + 미해결 종목 강제 1회 재조회


def test_dart_fetch_financials_falls_back_to_ofs_when_cfs_has_no_data(monkeypatch, tmp_path):
    monkeypatch.setenv("DART_API_KEY", "dummy")
    corp_zip = _build_corp_code_zip(
        [{"corp_code": "00126380", "corp_name": "테스트", "stock_code": "005930",
          "modify_date": date.today().strftime("%Y%m%d")}]
    )
    fnltt_success = {
        "status": "000",
        "message": "정상",
        "list": [
            {"rcept_no": "20230815000123", "sj_div": "BS", "account_id": "ifrs-full_Assets",
             "account_nm": "자산총계", "thstrm_amount": "1000000"},
            {"rcept_no": "20230815000123", "sj_div": "IS", "account_id": "ifrs-full_Revenue",
             "account_nm": "매출액", "thstrm_amount": "500000"},
        ],
    }
    client = _RoutingFakeClient(
        corp_code_zip=corp_zip,
        fnltt_responses={("11011", "OFS"): fnltt_success},
    )
    resolver = DartCorpCodeResolver("dummy", cache_path=tmp_path / "corp.parquet", client=client)
    adapter = DartFundamentalAdapter(client=client, corp_code_resolver=resolver)

    frame = adapter.fetch_financials(["005930"], date(2023, 1, 1), date(2023, 12, 31))

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["statement_scope"] == "separate"  # CFS 무데이터 → OFS 폴백 채택
    assert row["fiscal_year"] == 2023
    assert row["fiscal_quarter"] == 4
    assert row["period_end"] == date(2023, 12, 31)
    assert row["disclosure_date"] == date(2023, 8, 15)  # rcept_no 앞 8자리
    assert row["total_assets"] == 1000000.0
    assert row["revenue"] == 500000.0
    assert row["invested_capital"] == 1000000.0
    assert pd.isna(row["interest_expense"])
    # CFS 없음 확인 후 OFS로 폴백했는지 호출 순서 검증
    assert ("11011", "CFS") in client.fnltt_calls
    assert ("11011", "OFS") in client.fnltt_calls


def test_fetch_valuation_raises_without_krx_credentials(monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    adapter = PyKrxFundamentalAdapter()
    with pytest.raises(RuntimeError, match="KRX"):
        adapter.fetch_valuation(["005930"], date(2024, 1, 1), date(2024, 1, 31))


def test_fetch_valuation_skips_empty_response_when_credentials_present(monkeypatch):
    """자격증명은 있는데 특정 구간(예: 당일 미발표)이 빈 응답이면 하드 실패하지 않는다."""
    monkeypatch.setenv("KRX_ID", "dummy")
    monkeypatch.setenv("KRX_PW", "dummy")

    class _EmptyStock:
        def get_market_fundamental_by_date(self, start, end, symbol):
            return pd.DataFrame()

        def get_market_cap_by_date(self, start, end, symbol):
            return pd.DataFrame()

        def get_market_ohlcv_by_date(self, start, end, symbol):
            return pd.DataFrame()

    monkeypatch.setattr(
        "quant_krx.data.pykrx_fundamental._krx_stock", lambda: _EmptyStock()
    )
    adapter = PyKrxFundamentalAdapter()
    result = adapter.fetch_valuation(["005930"], date(2026, 7, 16), date(2026, 7, 16))

    assert result.empty
    assert set(result.columns) == {
        "symbol", "date", "close", "per", "pbr", "eps", "bps", "div", "dps",
        "market_cap", "shares",
    }
