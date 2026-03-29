from __future__ import annotations

import requests
import pytest

from dca_signal_bot.feishu_sender import FeishuError, maybe_send_feishu, send_feishu_text


class _DummyResponse:
    def __init__(self, *, status_code: int, text: str, payload: object | None = None, json_error: Exception | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_sender_raises_when_webhook_missing():
    with pytest.raises(FeishuError, match="missing or blank"):
        maybe_send_feishu(enabled=True, webhook_url="   ", summary_text="hello")


def test_sender_raises_on_non_200_response(monkeypatch):
    def fake_post(*args, **kwargs):
        _ = (args, kwargs)
        return _DummyResponse(status_code=500, text="server exploded", payload={"code": 0})

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(FeishuError, match="HTTP error: 500"):
        send_feishu_text("https://example.invalid", "hello")


def test_sender_raises_on_business_error_response(monkeypatch):
    def fake_post(*args, **kwargs):
        _ = (args, kwargs)
        return _DummyResponse(status_code=200, text='{"code":19000,"msg":"bad"}', payload={"code": 19000, "msg": "bad"})

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(FeishuError, match="error payload"):
        send_feishu_text("https://example.invalid", "hello")


def test_sender_succeeds_on_valid_success_response(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _DummyResponse(status_code=200, text='{"code":0,"msg":"success"}', payload={"code": 0, "msg": "success"})

    monkeypatch.setenv("FEISHU_KEYWORD", "")
    monkeypatch.setattr(requests, "post", fake_post)

    send_feishu_text("https://example.invalid", "hello world", timeout=7)

    assert captured["url"] == "https://example.invalid"
    assert captured["timeout"] == 7
    assert captured["json"]["msg_type"] == "text"
    assert captured["json"]["content"]["text"] == "hello world"


def test_sender_prefixes_keyword_when_configured(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _DummyResponse(status_code=200, text='{"code":0,"msg":"success"}', payload={"code": 0, "msg": "success"})

    monkeypatch.setenv("FEISHU_KEYWORD", "DCA-BOT")
    monkeypatch.setattr(requests, "post", fake_post)

    send_feishu_text("https://example.invalid", "monthly summary")

    assert captured["json"]["content"]["text"].startswith("DCA-BOT\n")
