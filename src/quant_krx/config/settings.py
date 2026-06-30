from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WatchlistConfig(BaseSettings):
    symbols: list[str] = Field(default_factory=list)
    market: str = "KRX"


class ProviderConfig(BaseSettings):
    primary: str = "fdr"  # "fdr" | "pykrx"
    fallback: str = "pykrx"
    cache_days: int = 1  # 캐시 유효 기간 (거래일)


class EvaluationProfile(BaseSettings):
    name: str = "balanced"  # "balanced" | "aggressive" | "conservative" | "research"
    mdd_threshold: float = 0.30  # MDD > 30% → risk_flag
    sharpe_min: float = 0.5
    recent_months: int = 6


class SchedulerConfig(BaseSettings):
    timezone: str = "Asia/Seoul"
    run_hour: int = 16  # 오후 4시 (장 마감 후)
    run_minute: int = 0


class NotifyConfig(BaseSettings):
    channel: str = "telegram"
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")


class LLMConfig(BaseSettings):
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
