import json
import lzma
from datetime import date

import numpy as np
import pandas as pd
import pytest

from bots.intraday.research import dukascopy as dk


def _bi5(minutes, base=4_000_000, vol=1.0):
    rec = np.zeros(len(minutes), dtype=dk.RECORD)
    rec["t"] = np.asarray(minutes) * 60
    rec["o"] = base + np.arange(len(minutes))
    rec["c"] = rec["o"] + 1
    rec["l"] = rec["o"] - 2
    rec["h"] = rec["o"] + 3
    rec["v"] = vol
    return lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)


def test_decode_bi5_times_fields_and_closed_minutes():
    raw = _bi5(range(0, 10))
    df = dk.decode_bi5(raw, date(2024, 1, 15))
    assert len(df) == 10 and str(df.index[0]) == "2024-01-15 00:00:00+00:00"
    assert df["high"].iloc[0] == 4_000_003 and df["low"].iloc[0] == 3_999_998
    assert df["close"].iloc[0] == 4_000_001
    assert dk.decode_bi5(_bi5(range(5), vol=0.0), date(2024, 1, 15)).empty
    assert dk.decode_bi5(b"", date(2024, 1, 15)).empty


def test_to_m5_aggregates():
    df = dk.decode_bi5(_bi5(range(10)), date(2024, 1, 15))
    m5 = dk.to_m5(df)
    assert len(m5) == 2
    first = m5.iloc[0]
    assert first["open"] == 4_000_000 and first["close"] == 4_000_005
    assert first["high"] == 4_000_007 and first["volume"] == 5


def test_price_scale_power_of_ten():
    assert dk.price_scale(pd.Series([4_000_000.0]), pd.Series([4012.5])) == pytest.approx(1e-3)
    assert dk.price_scale(pd.Series([108_500.0]), pd.Series([1.0851])) == pytest.approx(1e-5)


def test_spread_profile_by_utc_hour_of_week():
    idx = pd.date_range("2024-01-15", periods=24 * 7 * 12, freq="5min", tz="UTC")
    b = pd.DataFrame({"spread_price": np.where(idx.hour == 14, 0.5, 0.1)}, index=idx)
    prof = dk.spread_profile(b, 0.01)
    assert prof[0 * 24 + 14] == pytest.approx(50) and prof[0 * 24 + 3] == pytest.approx(10)
    assert len(prof) == 168 and prof.notna().all()


def test_build_symbol_offline(tmp_path, monkeypatch):
    broker_dir, out = tmp_path / "b", tmp_path / "o"
    broker_dir.mkdir()
    idx = pd.date_range("2024-01-16", periods=288 * 3, freq="5min", tz="UTC")
    px = 4000.0 + np.arange(len(idx)) * 0.005
    pd.DataFrame({"datetime": idx, "open": px, "high": px, "low": px, "close": px + 0.001,
                  "volume": 1, "spread": 40}).to_csv(broker_dir / "US500_M5.csv.gz", index=False)
    (broker_dir / "US500_spec.json").write_text(json.dumps({"point": 0.01}))

    def fake_fetch(inst, day, cache):
        return dk.decode_bi5(_bi5(range(1440), base=4_000_000 + (day.day - 15) * 1440), day)

    monkeypatch.setattr(dk, "fetch_day", fake_fetch)
    msg = dk.build_symbol("US500", "USA500IDXUSD", date(2024, 1, 15), date(2024, 1, 19),
                          broker_dir, out, workers=2)
    assert "US500" in msg
    df = pd.read_csv(out / "US500_M5.csv.gz")
    spec = json.loads((out / "US500_spec.json").read_text())
    assert spec["price_scale"] == pytest.approx(1e-3) and spec["source"].startswith("dukascopy")
    assert df["spread"].median() == pytest.approx(40)
    assert 3990 < df["close"].median() < 4010


# ---- rate limiting, partial failures, --check (urlopen faked, no network)
import io
import urllib.error


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(script):
    """script: list of int (HTTP error code) or bytes (body), consumed per call."""
    calls = []

    def urlopen(req, timeout=30):
        calls.append(req.full_url)
        item = script.pop(0) if script else b""
        if isinstance(item, int):
            raise urllib.error.HTTPError(req.full_url, item, "err", {}, None)
        return _Resp(item)
    return urlopen, calls


@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(dk, "_sleep", waits.append)
    return waits


def test_download_backs_off_on_503_then_succeeds(monkeypatch, no_sleep):
    body = _bi5(range(3))
    urlopen, calls = _fake_urlopen([503, 503, body])
    monkeypatch.setattr(dk.urllib.request, "urlopen", urlopen)
    assert dk.download("http://x") == body
    assert len(calls) == 3
    backoffs = [w for w in no_sleep if w > dk.PAUSE]
    assert len(backoffs) == 2 and 2 <= backoffs[0] < 3 and 4 <= backoffs[1] < 5
    assert calls[0] == "http://x"


def test_download_gives_up_and_404_is_empty(monkeypatch, no_sleep):
    urlopen, _ = _fake_urlopen([503] * 10)
    monkeypatch.setattr(dk.urllib.request, "urlopen", urlopen)
    with pytest.raises(dk.DownloadError, match="503"):
        dk.download("http://x", retries=3)
    urlopen, _ = _fake_urlopen([404])
    monkeypatch.setattr(dk.urllib.request, "urlopen", urlopen)
    assert dk.download("http://x") == b""
    urlopen, calls = _fake_urlopen([403, 403])
    monkeypatch.setattr(dk.urllib.request, "urlopen", urlopen)
    with pytest.raises(dk.DownloadError, match="403"):
        dk.download("http://x")
    assert len(calls) == 1                         # 403 is not retried


def _days(n):
    return [date(2024, 1, 1) + __import__("datetime").timedelta(days=i) for i in range(n)]


def test_fetch_days_tolerates_a_few_failed_days(monkeypatch, tmp_path, capsys):
    bad = {date(2024, 1, 3)}

    def fake(inst, day, cache):
        if day in bad:
            raise dk.DownloadError("503")
        return dk.decode_bi5(_bi5(range(2)), day)
    monkeypatch.setattr(dk, "fetch_day", fake)
    parts = dk.fetch_days("X", _days(100), tmp_path, workers=2)
    assert len(parts) == 99
    assert "1 day(s) missing" in capsys.readouterr().out
    bad.update(_days(100)[50:60])
    with pytest.raises(dk.DownloadError, match="could not be downloaded"):
        dk.fetch_days("X", _days(100), tmp_path, workers=2)


def test_failed_day_not_cached(monkeypatch, tmp_path, no_sleep):
    urlopen, _ = _fake_urlopen([503] * 10)
    monkeypatch.setattr(dk.urllib.request, "urlopen", urlopen)
    with pytest.raises(dk.DownloadError):
        dk.fetch_day("X", date(2024, 1, 17), tmp_path, retries=2)
    assert not (tmp_path / "X" / "20240117.bi5").exists()


def test_check_reports_each_symbol(monkeypatch, no_sleep, capsys):
    urlopen, calls = _fake_urlopen([_bi5(range(5)), 404, 503, 503, 503])
    monkeypatch.setattr(dk.urllib.request, "urlopen", urlopen)
    dk.check(["US500", "BADNAME", "XAUUSD"])
    out = capsys.readouterr().out.splitlines()
    assert "OK" in out[0] and "5 minutes" in out[0] and "USA500IDXUSD" in out[0]
    assert "404" in out[1]
    assert "FAILED" in out[2] and "503" in out[2]
    assert calls[0].endswith("/USA500IDXUSD/2024/00/17/BID_candles_min_1.bi5")
