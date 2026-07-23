import yaml


def test_settings_load_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    watchlist_path = tmp_path / "config" / "watchlist.yaml"
    watchlist_path.parent.mkdir(parents=True)
    watchlist_path.write_text(yaml.dump({"symbols": ["005930", "000660"]}))

    monkeypatch.setenv("WATCHLIST_PATH", str(watchlist_path))
    # __main__.py의 load_dotenv() 호출(pykrx 자격증명이 os.getenv()로 직접 읽히도록 필요)이
    # CLI 통합 테스트(test_backtest_cli.py 등, __main__ import 시 트리거)를 통해 실제
    # os.environ에 프로젝트 .env 내용을 주입해둘 수 있다 — monkeypatch.chdir은 이 실제
    # 프로세스 환경 오염까지는 되돌리지 못하므로, 이 테스트가 검증하는 키는 명시적으로 비운다.
    monkeypatch.delenv("PROVIDER__PRIMARY", raising=False)

    from quant_krx.config.settings import get_settings

    settings = get_settings()

    assert settings.evaluation.name == "balanced"
    assert settings.provider.primary == "fdr"
    assert settings.scheduler.timezone == "Asia/Seoul"


def test_validate_watchlist_ok(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    watchlist_path = tmp_path / "config" / "watchlist.yaml"
    watchlist_path.parent.mkdir(parents=True)
    watchlist_path.write_text(yaml.dump({"symbols": ["005930"]}))
    monkeypatch.setenv("WATCHLIST_PATH", str(watchlist_path))

    from quant_krx.config.settings import get_settings

    settings = get_settings()
    ok, msg = settings.validate_watchlist()
    assert ok
    assert "1 symbols" in msg


def test_validate_watchlist_empty(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WATCHLIST_PATH", str(tmp_path / "nonexistent.yaml"))

    from quant_krx.config.settings import get_settings

    settings = get_settings()
    ok, msg = settings.validate_watchlist()
    assert not ok


def test_get_profile():
    from quant_krx.config.profiles import get_profile

    balanced = get_profile("balanced")
    assert balanced.mdd_threshold == 0.30
    assert balanced.sharpe_min == 0.5


def test_get_profile_invalid():
    import pytest

    from quant_krx.config.profiles import get_profile

    with pytest.raises(ValueError, match="Unknown profile"):
        get_profile("nonexistent")
