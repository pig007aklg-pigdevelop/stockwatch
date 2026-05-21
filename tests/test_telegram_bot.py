from unittest.mock import MagicMock, patch

from app.services import telegram_bot


def _mock_response(status_code: int):
    r = MagicMock()
    r.status_code = status_code
    r.text = "bad request" if status_code != 200 else "ok"
    return r


@patch("app.services.telegram_bot.config")
@patch("app.services.telegram_bot.httpx.post")
def test_send_default_plain_text_no_parse_mode(mock_post, mock_config):
    mock_config.TG_TOKEN = "token"
    mock_config.TG_CHAT_ID = "chat"
    mock_post.return_value = _mock_response(200)

    assert telegram_bot.send("hello *world*") is True
    payload = mock_post.call_args.kwargs["json"]
    assert "parse_mode" not in payload
    assert payload["text"] == "hello *world*"


@patch("app.services.telegram_bot.config")
@patch("app.services.telegram_bot.httpx.post")
def test_send_markdown_400_falls_back_to_plain_text(mock_post, mock_config):
    mock_config.TG_TOKEN = "token"
    mock_config.TG_CHAT_ID = "chat"
    mock_post.side_effect = [
        _mock_response(400),
        _mock_response(200),
    ]

    text = "reason with unclosed _ bracket ["
    assert telegram_bot.send(text, parse_mode="Markdown") is True
    assert mock_post.call_count == 2
    first = mock_post.call_args_list[0].kwargs["json"]
    second = mock_post.call_args_list[1].kwargs["json"]
    assert first["parse_mode"] == "Markdown"
    assert "parse_mode" not in second
    assert second["text"] == text
