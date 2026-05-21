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


def test_to_yfinance_hk_four_digit_padded():
    assert to_yfinance_symbol("HK", "00700") == "0700.HK"
    assert to_yfinance_symbol("HK", "03690") == "3690.HK"
    assert to_yfinance_symbol("HK", "09999") == "9999.HK"
    assert to_yfinance_symbol("HK", "01299") == "1299.HK"
    assert to_yfinance_symbol("HK", "00005") == "0005.HK"
    assert to_yfinance_symbol("HK", "01810") == "1810.HK"


def test_to_yfinance_hk_truncates_long_codes_to_four_digits():
    assert to_yfinance_symbol("HK", "0001234") == "1234.HK"


def test_to_yfinance_us():
    assert to_yfinance_symbol("US", "nvda") == "NVDA"


def test_is_us():
    assert is_us_market("US") is True
    assert is_us_market("HK") is False
