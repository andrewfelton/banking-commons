"""Tests for banking_commons.email.

These cover the pure logic (recipient parsing, env-alias resolution, markdown
rendering, body resolution, and the skip/raise branches) without touching the
network — the actual ACS send is exercised only via its config/SDK guards.
"""
import pytest

from banking_commons.email import (
    EmailConfig,
    EmailConfigError,
    markdown_to_html,
    parse_recipients,
    send_email,
)


# --- parse_recipients -------------------------------------------------------

def test_parse_recipients_comma_and_semicolon():
    assert parse_recipients("a@x.com, b@y.com; c@z.com") == [
        "a@x.com", "b@y.com", "c@z.com",
    ]


def test_parse_recipients_iterable_and_blanks():
    assert parse_recipients(["a@x.com", "", " b@y.com ;"]) == ["a@x.com", "b@y.com"]


def test_parse_recipients_none():
    assert parse_recipients(None) == []


# --- EmailConfig.from_env ---------------------------------------------------

def test_from_env_acs_aliases(monkeypatch):
    monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=conn")
    monkeypatch.setenv("ACS_SENDER_ADDRESS", "from@x.net")
    monkeypatch.setenv("DIGEST_RECIPIENT", "a@x.com,b@y.com")
    cfg = EmailConfig.from_env()
    assert cfg.connection_string == "endpoint=conn"
    assert cfg.sender == "from@x.net"
    assert cfg.recipients == ["a@x.com", "b@y.com"]
    assert cfg.missing() == []


def test_from_env_azure_aliases(monkeypatch):
    # The ai_news_feed / bank-filings spelling.
    monkeypatch.delenv("ACS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("ACS_SENDER_ADDRESS", raising=False)
    monkeypatch.delenv("DIGEST_RECIPIENT", raising=False)
    monkeypatch.setenv("AZURE_COMMUNICATION_CONNECTION_STRING", "endpoint=conn2")
    monkeypatch.setenv("EMAIL_SENDER", "from2@x.net")
    monkeypatch.setenv("EMAIL_TO", "only@z.com")
    cfg = EmailConfig.from_env()
    assert cfg.connection_string == "endpoint=conn2"
    assert cfg.sender == "from2@x.net"
    assert cfg.recipients == ["only@z.com"]


def test_from_env_recipients_override(monkeypatch):
    monkeypatch.setenv("ACS_CONNECTION_STRING", "c")
    monkeypatch.setenv("ACS_SENDER_ADDRESS", "s")
    monkeypatch.delenv("DIGEST_RECIPIENT", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    cfg = EmailConfig.from_env(recipients=["computed@x.com"])
    assert cfg.recipients == ["computed@x.com"]


def test_missing_reports_gaps():
    assert set(EmailConfig("", "", []).missing()) == {
        "connection_string", "sender", "recipients",
    }


# --- markdown_to_html -------------------------------------------------------

def test_markdown_to_html_basic():
    out = markdown_to_html("# Title\n\n- one\n- two")
    assert "<h1>Title</h1>" in out
    assert "<li>one</li>" in out


def test_markdown_to_html_none():
    assert markdown_to_html(None) == ""


# --- send_email config guards ----------------------------------------------

def test_send_email_missing_config_raises_by_default():
    cfg = EmailConfig("", "", [])
    with pytest.raises(EmailConfigError):
        send_email("Hi", text="body", config=cfg)


def test_send_email_missing_config_swallow():
    cfg = EmailConfig("", "", [])
    result = send_email("Hi", text="body", config=cfg, on_config_error="swallow")
    assert not result
    assert result.sent is False
    assert "missing" in result.skipped_reason


def test_send_email_missing_sdk_swallow(monkeypatch):
    # Config is complete, but pretend the Azure SDK isn't installed. send_email
    # does a plain `from azure.communication.email import EmailClient`, so we
    # intercept that one import at the builtins level.
    import builtins

    cfg = EmailConfig("endpoint=c", "from@x.net", ["to@y.com"])
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "azure.communication.email":
            raise ImportError("no azure")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = send_email("Hi", text="body", config=cfg, on_config_error="swallow")
    assert not result
    assert "azure-communication-email" in result.skipped_reason
