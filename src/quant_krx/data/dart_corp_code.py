from __future__ import annotations

import zipfile
from collections.abc import Sequence
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pandas as pd

_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
_DEFAULT_CACHE_PATH = Path.home() / ".cache" / "quant_krx" / "dart_corp_code.parquet"
_DEFAULT_MAX_CACHE_AGE_DAYS = 7
_CACHE_COLUMNS = ("corp_code", "corp_name", "stock_code", "modify_date")


class DartCorpCodeResolver:
    """종목코드(6자리) → DART corp_code(8자리) 해결 (TR-R01-D01, TRD-R01-D §2).

    corpCode.xml 전체 목록을 로컬 parquet 캐시에 저장한다. 캐시가 없거나 캐시에
    기록된 최대 modify_date가 max_cache_age_days일 이상 경과하면 재다운로드한다.
    """

    def __init__(
        self,
        api_key: str,
        *,
        cache_path: Path | None = None,
        client: httpx.Client | None = None,
        max_cache_age_days: int = _DEFAULT_MAX_CACHE_AGE_DAYS,
    ) -> None:
        self._api_key = api_key
        self._cache_path = cache_path or _DEFAULT_CACHE_PATH
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None
        self._max_cache_age_days = max_cache_age_days

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def resolve(self, symbols: Sequence[str]) -> dict[str, str]:
        """종목코드 → corp_code 매핑을 반환한다. 해결 불가 종목은 결과에서 제외된다."""
        wanted = {s.zfill(6) for s in symbols}
        df = self._load_cache()
        if df is None or self._is_stale(df):
            df = self._fetch_and_cache()

        mapping = dict(zip(df["stock_code"], df["corp_code"], strict=True))
        missing = wanted - mapping.keys()
        if missing:
            # 캐시는 신선하지만(최근 갱신) 특정 종목이 없는 경우 — 당일 신규상장 등
            # 드문 케이스 대비 1회 강제 재다운로드 후에도 없으면 결측으로 수용한다.
            df = self._fetch_and_cache()
            mapping = dict(zip(df["stock_code"], df["corp_code"], strict=True))

        return {s: mapping[s] for s in wanted if s in mapping}

    def _load_cache(self) -> pd.DataFrame | None:
        if not self._cache_path.exists():
            return None
        try:
            return pd.read_parquet(self._cache_path)
        except Exception:
            return None

    def _is_stale(self, df: pd.DataFrame) -> bool:
        if df.empty:
            return True
        max_modify = pd.to_datetime(df["modify_date"], format="%Y%m%d").max().date()
        return (date.today() - max_modify) > timedelta(days=self._max_cache_age_days)

    def _fetch_and_cache(self) -> pd.DataFrame:
        response = self._client.get(_CORP_CODE_URL, params={"crtfc_key": self._api_key})
        response.raise_for_status()
        df = _parse_corp_code_zip(response.content)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self._cache_path, index=False)
        return df


def _parse_corp_code_zip(content: bytes) -> pd.DataFrame:
    if not content.startswith(b"PK"):
        raise RuntimeError(_describe_error(content))
    with zipfile.ZipFile(BytesIO(content)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    root = ElementTree.fromstring(xml_bytes)
    rows = []
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if not stock_code:
            continue  # 비상장법인 — 종목코드 매핑 대상 아님
        rows.append(
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "stock_code": stock_code,
                "modify_date": (item.findtext("modify_date") or "").strip(),
            }
        )
    return pd.DataFrame(rows, columns=list(_CACHE_COLUMNS))


def _describe_error(content: bytes) -> str:
    try:
        root = ElementTree.fromstring(content)
        status = root.findtext("status", default="unknown")
        message = root.findtext("message", default="")
    except ElementTree.ParseError:
        return "DART corpCode.xml 응답을 파싱할 수 없습니다(예상 밖 형식)."
    return f"DART corpCode.xml 요청 실패 (status={status}): {message}"
