import pandas as pd
import pytest

from app.services import index_constituents as ic

try:
    from futu import RET_OK
except ImportError:
    RET_OK = 0


def _plate_df(n: int, prefix: str) -> pd.DataFrame:
    return pd.DataFrame({"code": [f"{prefix}.{i:05d}" for i in range(n)]})


def test_get_hk_tech_constituents_30_from_get_plate_stock(monkeypatch):
    """Mock get_plate_stock(HK.800700) → 30 rows."""
    plate = "HK.800700"
    df = _plate_df(30, "HK")

    class Ctx:
        def get_plate_stock(self, code):
            assert code == plate
            return RET_OK, df

    monkeypatch.setattr(ic.futu, "ctx", Ctx())
    monkeypatch.setattr(ic.futu, "connect", lambda: None)

    codes = ic.get_hk_tech_constituents()
    assert len(codes) == 30
    assert codes[0] == "HK.00000"
    assert all(c.startswith("HK.") for c in codes)


def test_get_us_nasdaq100_from_plate_stock(monkeypatch):
    plate = "US..NDX"
    df = _plate_df(101, "US")

    class Ctx:
        def get_plate_stock(self, code):
            assert code == plate
            return RET_OK, df

    monkeypatch.setattr(ic.futu, "ctx", Ctx())
    monkeypatch.setattr(ic.futu, "connect", lambda: None)

    codes = ic.get_us_nasdaq100_constituents()
    assert len(codes) == 101
    assert all(c.startswith("US.") for c in codes)


def test_hk_fallback_when_plate_fails(monkeypatch):
    monkeypatch.setattr(ic, "_fetch_plate_codes", lambda _: [])
    assert ic.get_hk_tech_constituents() == ic.HK_TECH_FALLBACK
