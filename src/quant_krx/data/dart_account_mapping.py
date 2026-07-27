from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AccountSpec:
    """`financial_statements` 값 컬럼 1개 ↔ DART 계정 매칭 규약 (TR-R01-D02, TRD-R01-D §3).

    account_id가 있으면 최우선 매칭키로 사용하고, 미매칭 시 account_nm_fallback 후보들과
    일치하는 행의 금액을 합산한다(감가상각비+무형자산상각비처럼 복수 계정이 한 컬럼에
    대응하는 경우를 자연스럽게 포괄). account_id가 빈 문자열이면 DART 표준 태그가 없다는
    뜻이며 account_nm 매칭만 수행한다.
    """

    column: str
    sj_div: str
    account_id: str
    account_nm_fallback: tuple[str, ...]


ACCOUNT_SPECS: tuple[AccountSpec, ...] = (
    AccountSpec("revenue", "IS", "ifrs-full_Revenue", ("매출액", "수익(매출액)")),
    AccountSpec("gross_profit", "IS", "ifrs-full_GrossProfit", ("매출총이익",)),
    AccountSpec(
        "operating_income", "IS", "dart_OperatingIncomeLoss", ("영업이익(손실)", "영업이익")
    ),
    AccountSpec("net_income", "IS", "ifrs-full_ProfitLoss", ("당기순이익(손실)", "당기순이익")),
    AccountSpec(
        "pretax_income",
        "IS",
        "ifrs-full_ProfitLossBeforeTax",
        ("법인세비용차감전순이익(손실)", "법인세비용차감전순이익"),
    ),
    AccountSpec(
        "income_tax", "IS", "ifrs-full_IncomeTaxExpenseContinuingOperations", ("법인세비용",)
    ),
    AccountSpec("total_assets", "BS", "ifrs-full_Assets", ("자산총계",)),
    AccountSpec("total_debt", "BS", "ifrs-full_Liabilities", ("부채총계",)),
    AccountSpec("total_equity", "BS", "ifrs-full_Equity", ("자본총계",)),
    AccountSpec("current_assets", "BS", "ifrs-full_CurrentAssets", ("유동자산",)),
    AccountSpec("current_liabilities", "BS", "ifrs-full_CurrentLiabilities", ("유동부채",)),
    AccountSpec(
        "operating_cash_flow",
        "CF",
        "ifrs-full_CashFlowsFromUsedInOperatingActivities",
        ("영업활동으로 인한 현금흐름", "영업활동현금흐름"),
    ),
    AccountSpec("interest_expense", "IS", "ifrs-full_InterestExpense", ("이자비용",)),
    AccountSpec(
        "depreciation_amortization", "CF", "", ("감가상각비", "무형자산상각비")
    ),
    AccountSpec(
        "cash_and_equivalents", "BS", "ifrs-full_CashAndCashEquivalents", ("현금및현금성자산",)
    ),
)

# fnlttSinglAcntAll 원본 레코드에서 반드시 필요한 컬럼
REQUIRED_RAW_COLUMNS = ("sj_div", "account_id", "account_nm", "thstrm_amount")


def extract_financial_fields(records: pd.DataFrame) -> dict[str, float]:
    """DART `fnlttSinglAcntAll` 응답(단일 corp_code·bsns_year·reprt_code·fs_div)에서
    `financial_statements`의 16개 값 컬럼을 추출한다.

    매칭 실패 필드는 결과 dict에 포함되지 않는다(호출부가 NaN으로 채움 — 기존
    "결측은 NaN이 진실 원천" 원칙과 동일). `invested_capital`은 DART 원천 태그가 없는
    파생 컬럼으로, `total_assets`를 그대로 대입한다(`tests/fixtures/sample_financials.csv`
    관례 확인, `factors/catalog/financial.py::roic` 분모 정의와 정합).
    """
    values: dict[str, float] = {}
    for spec in ACCOUNT_SPECS:
        subset = records[records["sj_div"] == spec.sj_div]
        matched = (
            subset[subset["account_id"] == spec.account_id] if spec.account_id else subset[0:0]
        )
        if matched.empty and spec.account_nm_fallback:
            matched = subset[subset["account_nm"].isin(spec.account_nm_fallback)]
        if matched.empty:
            continue
        amounts = pd.to_numeric(matched["thstrm_amount"], errors="coerce").dropna()
        if amounts.empty:
            continue
        values[spec.column] = float(amounts.sum())

    if "total_assets" in values:
        values["invested_capital"] = values["total_assets"]

    return values
