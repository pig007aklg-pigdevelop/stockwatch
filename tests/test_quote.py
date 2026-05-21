import sys
from unittest.mock import MagicMock, patch

import pandas as pd

# akshare 可能未装在本地 pytest 环境
if "akshare" not in sys.modules:
    sys.modules["akshare"] = MagicMock()

from app.config import config
from app.services import quote as quote_mod


def _hk_df():
    return pd.DataFrame([
        {"代码": "00700", "名称": "腾讯", "最新价": 300.0, "涨跌幅": 1.2, "成交量": 1000000},
    ])


def _us_df():
    return pd.DataFrame([
        {"代码": "105.BABA", "名称": "阿里", "最新价": 110.5, "涨跌幅": -0.5, "成交量": 5000000},
    ])


def test_akshare_hk_and_us_paths(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "akshare")
    quote_mod.clear_cache()

    with patch("akshare.stock_hk_spot_em", return_value=_hk_df()) as hk_mock:
        with patch("akshare.stock_us_spot_em", return_value=_us_df()) as us_mock:
            import akshare  # noqa: F401 — ensure patch target exists
            result = quote_mod.snapshot(["HK.00700", "US.BABA"])

    assert hk_mock.called
    assert us_mock.called
    assert result["HK.00700"]["price"] == 300.0
    assert result["HK.00700"]["change_pct"] == 1.2
    assert result["US.BABA"]["price"] == 110.5
    assert "ts" in result["US.BABA"]


def test_cache_avoids_second_akshare_call(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "akshare")
    quote_mod.clear_cache()

    with patch("akshare.stock_hk_spot_em", return_value=_hk_df()) as hk_mock:
        with patch("akshare.stock_us_spot_em", return_value=_us_df()) as us_mock:
            quote_mod.snapshot(["HK.00700", "US.BABA"])
            quote_mod.snapshot(["HK.00700"])

    assert hk_mock.call_count == 1
    assert us_mock.call_count == 1


def test_single_symbol_missing_others_ok(monkeypatch):
    monkeypatch.setattr(config, "QUOTE_PROVIDER", "akshare")
    quote_mod.clear_cache()

    with patch("akshare.stock_hk_spot_em", return_value=_hk_df()):
        with patch("akshare.stock_us_spot_em", return_value=_us_df()):
            result = quote_mod.snapshot(["HK.00700", "US.NOTREAL"])

    assert "HK.00700" in result
    assert "US.NOTREAL" not in result


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
    assert "ts" in result["US.NVDA"]
