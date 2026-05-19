import sys
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services import data_sources


def test_fetch_hsgt_returns_none_on_error():
    fake_ak = MagicMock()
    fake_ak.stock_hsgt_individual_em.side_effect = Exception("api down")
    with patch.dict(sys.modules, {"akshare": fake_ak}):
        assert data_sources.fetch_hsgt_holdings("HK", "00700") is None


def test_fetch_fund_flow_parses_columns():
    df = pd.DataFrame({
        "日期": ["2024-01-01"],
        "主力净流入-净额": [1e8],
        "主力净流入-净占比": [5.0],
    })
    fake_ak = MagicMock()
    fake_ak.stock_individual_fund_flow.return_value = df
    with patch.dict(sys.modules, {"akshare": fake_ak}):
        snap = data_sources.fetch_fund_flow("HK", "00700")
    assert snap is not None
    assert snap.net_inflow_5d == 1e8
