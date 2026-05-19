from app.services.ticker import (
    normalize_symbol,
    to_akshare_symbol,
    to_yfinance_symbol,
    is_us_market,
)


def test_normalize_hk_pads_five_digits():
    assert normalize_symbol("HK", "700") == "00700"
    assert normalize_symbol("HK", "00700") == "00700"


def test_to_akshare_hk():
    assert to_akshare_symbol("HK", "700") == "00700"
    assert to_akshare_symbol("US", "NVDA") is None


def test_to_yfinance():
    assert to_yfinance_symbol("HK", "00700") == "700.HK"
    assert to_yfinance_symbol("US", "nvda") == "NVDA"


def test_is_us():
    assert is_us_market("US") is True
    assert is_us_market("HK") is False
