from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ALL_STRATEGIES = [
    "ma_crossover",
    "rsi_breakout",
    "bollinger_band",
    "macd",
    "momentum",
]

# 네스티드 BaseSettings 공통 설정 — env_file을 지정해야 .env를 읽을 수 있음
_NESTED_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
    populate_by_name=True,
)


class StrategyConfig(BaseSettings):
    model_config = _NESTED_CONFIG
    enabled: list[str] = Field(default_factory=lambda: list(ALL_STRATEGIES))


class WatchlistConfig(BaseSettings):
    model_config = _NESTED_CONFIG
    symbols: list[str] = Field(default_factory=list)
    market: str = "KRX"


class ProviderConfig(BaseSettings):
    model_config = _NESTED_CONFIG
    primary: str = "fdr"  # "fdr" | "pykrx"
    fallback: str = "pykrx"
    cache_days: int = 1  # 캐시 유효 기간 (거래일)


class EvaluationProfile(BaseSettings):
    model_config = _NESTED_CONFIG
    name: str = "balanced"  # "balanced" | "aggressive" | "conservative" | "research"
    mdd_threshold: float = 0.30  # MDD > 30% → risk_flag
    sharpe_min: float = 0.5
    recent_months: int = 6


class SchedulerConfig(BaseSettings):
    model_config = _NESTED_CONFIG
    timezone: str = "Asia/Seoul"
    run_hour: int = 16  # 오후 4시 (장 마감 후)
    run_minute: int = 0


class NotifyConfig(BaseSettings):
    model_config = _NESTED_CONFIG
    channel: str = "telegram"
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")


class LLMConfig(BaseSettings):
    model_config = _NESTED_CONFIG
    provider: str = "anthropic"  # "anthropic" | "openai"
    model: str = "claude-sonnet-4-6"
    mock: bool = Field(default=False, alias="LLM_MOCK")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    duckdb_path: str = Field(default="data/quant_krx.duckdb", alias="DUCKDB_PATH")
    watchlist_path: str = Field(default="config/watchlist.yaml", alias="WATCHLIST_PATH")
    report_dir: str = Field(default="reports", alias="REPORT_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    evaluation: EvaluationProfile = Field(default_factory=EvaluationProfile)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

    def load_watchlist(self) -> list[str]:
        path = Path(self.watchlist_path)
        if not path.exists():
            return []
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("symbols", []) if isinstance(data, dict) else []

    def validate_watchlist(self) -> tuple[bool, str]:
        symbols = self.load_watchlist()
        if not symbols:
            return False, f"Watchlist is empty or not found at: {self.watchlist_path}"
        return True, f"Watchlist OK: {len(symbols)} symbols"


def get_settings() -> Settings:
    return Settings()
