import pandas as pd
from unittest.mock import MagicMock, patch

from app.services.futu_client import FutuClient, RET_OK


def test_connect_uses_sync_open_context():
    mock_ctx = MagicMock()
    with patch("app.services.futu_client.OpenQuoteContext", return_value=mock_ctx) as factory:
        client = FutuClient()
        client.connect()
        factory.assert_called_once()
        _, kwargs = factory.call_args
        assert kwargs["is_async_connect"] is False
        assert client.ctx is mock_ctx


def test_get_snapshot_retries_after_ret_error():
    df = pd.DataFrame(
        [
            {
                "code": "HK.00700",
                "last_price": 400.0,
                "change_rate": 1.5,
                "volume": 1000,
                "name": "腾讯",
                "prev_close_price": 395.0,
            }
        ]
    )
    mock_ctx = MagicMock()
    mock_ctx.get_market_snapshot.side_effect = [
        (-1, "timeout"),
        (RET_OK, df),
    ]

    client = FutuClient()
    client.ctx = mock_ctx

    with patch.object(client, "reconnect") as reconnect:
        result = client.get_snapshot(["HK.00700"])

    reconnect.assert_called_once()
    assert mock_ctx.get_market_snapshot.call_count == 2
    assert result["HK.00700"]["price"] == 400.0
    assert result["HK.00700"]["name"] == "腾讯"


def test_get_snapshot_returns_empty_after_retry_still_fails():
    mock_ctx = MagicMock()
    mock_ctx.get_market_snapshot.return_value = (-1, "fail")

    client = FutuClient()
    client.ctx = mock_ctx

    with patch.object(client, "reconnect"):
        result = client.get_snapshot(["HK.00700"])

    assert result == {}
    assert mock_ctx.get_market_snapshot.call_count == 2
