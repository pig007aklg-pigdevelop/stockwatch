import sys
from unittest.mock import MagicMock, patch

# yfinance 可能未装在本地 pytest 环境
if "yfinance" not in sys.modules:
    sys.modules["yfinance"] = MagicMock()

from app.config import config
from app.services import quote as quote_mod


def _mock_fast_info(price=131.45, prev=130.0, volume=1_000_000):
    return {
        "lastPrice": price,
        "regularMarketPreviousClose": prev,
        "lastVolume": volume,
    }


def _mock_ticker(fast_info):
    t = MagicMock()
    t.fast_info = fast_info
    return t


def _mock_tickers(mapping: dict[str, dict]):
    tickers = MagicMock()
    tickers.tickers = {
        yf: _mock_ticker(fi) for yf, fi in mapping.items()
    }
    return tickers


def test_to_yf_symbol_hk_conversion():
    assert quote_mod._to_yf_symbol("HK.00700") == "0700.HK"
    assert quote_mod._to_yf_symbol("HK.01810") == "1810.HK"
    assert quote_mod._to_yf_symbol("US.BABA") == "BABA"


def test_yfinance_hk_and_us_paths(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "yfinance")
    quote_mod.clear_cache()

    mock = _mock_tickers({
        "0700.HK": _mock_fast_info(300.0, 295.0, 1_000_000),
        "BABA": _mock_fast_info(110.5, 111.0, 5_000_000),
    })
    with patch("yfinance.Tickers", return_value=mock) as yf_mock:
        result = quote_mod.snapshot(["HK.00700", "US.BABA"])

    yf_mock.assert_called_once()
    assert "0700.HK" in yf_mock.call_args[0][0]
    assert "BABA" in yf_mock.call_args[0][0]
    assert result["HK.00700"]["price"] == 300.0
    assert abs(result["HK.00700"]["change_pct"] - (300 - 295) / 295 * 100) < 0.01
    assert result["US.BABA"]["price"] == 110.5
    assert "ts" in result["US.BABA"]


def test_cache_avoids_second_yfinance_call(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "yfinance")
    quote_mod.clear_cache()

    mock = _mock_tickers({"0700.HK": _mock_fast_info(300.0, 290.0)})
    with patch("yfinance.Tickers", return_value=mock) as yf_mock:
        quote_mod.snapshot(["HK.00700", "US.BABA"])
        quote_mod.snapshot(["US.BABA", "HK.00700"])

    assert yf_mock.call_count == 1


def test_single_symbol_failure_others_ok(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "yfinance")
    quote_mod.clear_cache()

    mock = _mock_tickers({
        "0700.HK": _mock_fast_info(300.0, 290.0),
        "BABA": _mock_fast_info(0, 0),  # invalid price → skip
    })
    with patch("yfinance.Tickers", return_value=mock):
        result = quote_mod.snapshot(["HK.00700", "US.BAD"])

    assert "HK.00700" in result
    assert "US.BAD" not in result


def test_routes_to_futu_when_configured(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "futu")
    futu_mock = MagicMock()
    futu_mock.get_snapshot.return_value = {
        "US.NVDA": {"price": 500.0, "change_pct": 2.0, "volume": 1},
    }

    with patch("app.services.futu_client.futu", futu_mock):
        result = quote_mod.snapshot(["US.NVDA"])

    futu_mock.get_snapshot.assert_called_once_with(["US.NVDA"])
    assert result["US.NVDA"]["price"] == 500.0
