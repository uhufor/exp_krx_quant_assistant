from __future__ import annotations

from datetime import datetime, timedelta

from quant_krx.data.dart_missing_period_cache import DartMissingPeriodCache


def test_not_checked_yet_is_not_recently_checked(tmp_path):
    cache = DartMissingPeriodCache(cache_path=tmp_path / "missing.parquet")
    assert cache.is_recently_checked("005930", 2026, 2, now=datetime(2026, 7, 27, 12, 0)) is False


def test_recorded_missing_is_recently_checked_within_ttl(tmp_path):
    cache = DartMissingPeriodCache(cache_path=tmp_path / "missing.parquet", ttl=timedelta(hours=1))
    checked_at = datetime(2026, 7, 27, 12, 0)
    cache.record_missing("005930", 2026, 2, now=checked_at)

    assert cache.is_recently_checked("005930", 2026, 2, now=checked_at + timedelta(minutes=30))


def test_recorded_missing_expires_after_ttl(tmp_path):
    cache = DartMissingPeriodCache(cache_path=tmp_path / "missing.parquet", ttl=timedelta(hours=1))
    checked_at = datetime(2026, 7, 27, 12, 0)
    cache.record_missing("005930", 2026, 2, now=checked_at)

    after_ttl = checked_at + timedelta(hours=1, seconds=1)
    assert not cache.is_recently_checked("005930", 2026, 2, now=after_ttl)


def test_different_symbol_or_quarter_is_unaffected(tmp_path):
    cache = DartMissingPeriodCache(cache_path=tmp_path / "missing.parquet")
    checked_at = datetime(2026, 7, 27, 12, 0)
    cache.record_missing("005930", 2026, 2, now=checked_at)

    assert not cache.is_recently_checked("000660", 2026, 2, now=checked_at)
    assert not cache.is_recently_checked("005930", 2026, 1, now=checked_at)


def test_flush_persists_across_instances(tmp_path):
    path = tmp_path / "missing.parquet"
    checked_at = datetime(2026, 7, 27, 12, 0)

    first = DartMissingPeriodCache(cache_path=path)
    first.record_missing("005930", 2026, 2, now=checked_at)
    first.flush()

    second = DartMissingPeriodCache(cache_path=path)
    assert second.is_recently_checked("005930", 2026, 2, now=checked_at + timedelta(minutes=1))


def test_flush_without_changes_does_not_create_file(tmp_path):
    path = tmp_path / "missing.parquet"
    cache = DartMissingPeriodCache(cache_path=path)
    cache.flush()
    assert not path.exists()


def test_record_missing_twice_keeps_latest_checked_at(tmp_path):
    cache = DartMissingPeriodCache(cache_path=tmp_path / "missing.parquet", ttl=timedelta(hours=1))
    first_check = datetime(2026, 7, 27, 10, 0)
    second_check = datetime(2026, 7, 27, 11, 30)
    cache.record_missing("005930", 2026, 2, now=first_check)
    cache.record_missing("005930", 2026, 2, now=second_check)

    # 첫 확인 기준으로는 이미 TTL 만료지만, 갱신된(두 번째) 확인 기준으로는 아직 유효해야 함.
    assert cache.is_recently_checked("005930", 2026, 2, now=second_check + timedelta(minutes=30))
