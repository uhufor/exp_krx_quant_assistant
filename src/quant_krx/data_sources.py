"""`--data-source` 화이트리스트의 단일 원천.

CLI(`__main__.py`)·API(`api/routers/*`)·데이터 조립(`workspace/data_loading.py`)이 모두 이
목록을 봐야 소스를 추가할 때 한쪽만 고쳐지는 드리프트가 생기지 않는다.

**의존성이 없는 최상위 모듈인 것이 요점이다.** `workspace/data_loading`이나 `data/` 패키지에
두면 CLI가 화이트리스트 하나 읽으려고 pandas·duckdb·pykrx를 끌고 와 `--help`조차 1.3초가
느려진다(`__main__.py`가 무거운 것을 전부 lazy import하는 이유와 같다).
"""

from __future__ import annotations

DATA_SOURCES = ("fixture", "fixture_10y", "krx_dart")

# 오프라인(네트워크·자격증명 불필요) 소스 — OHLCV와 펀더멘털 모두 픽스처 어댑터를 쓴다.
OFFLINE_DATA_SOURCES = frozenset({"fixture", "fixture_10y"})

DATA_SOURCE_HELP = (
    "데이터 소스: fixture(합성 1년치) | fixture_10y(실제 KRX 수정주가 10년치, 오프라인)"
    " | krx_dart(KRX+DART 실데이터)"
)
