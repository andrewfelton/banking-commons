"""Send transactional/digest email via Azure Communication Services.

This is the superset of the four near-identical `send_email` / `notify` helpers
that were copy-pasted across the banking-policy projects. It absorbs the points
where they diverged:

  * env-var names         -> handled by EmailConfig (multiple aliases)
  * markdown vs explicit  -> pass `markdown=`, or `html=`/`text=` directly
    html+text bodies
  * error philosophy      -> `on_config_error` and `on_send_error` let each
                             caller pick fail-fast (Functions apps, where a
                             missing setting is a deploy bug) or best-effort
                             (daily local runs, where a mail hiccup must not
                             break the pipeline)

Returns a SendResult instead of a bare status string/bool so callers can branch
on sent / skipped / failed without re-deriving it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Literal

from .config import EmailConfig, parse_recipients
from .markdown import markdown_to_html

log = logging.getLogger(__name__)

OnError = Literal["raise", "swallow"]


class EmailConfigError(RuntimeError):
    """Raised when required email configuration is missing and the caller asked
    to fail fast (`on_config_error="raise"`)."""


@dataclass
class SendResult:
    """Outcome of a send attempt.

    `bool(result)` is True only when the message was actually handed to ACS.
    """

    sent: bool
    status: str | None = None
    message_id: str | None = None
    skipped_reason: str | None = None
    error: str | None = None

    def __bool__(self) -> bool:
        return self.sent


def send_email(
    subject: str,
    *,
    text: str | None = None,
    html: str | None = None,
    markdown: str | None = None,
    recipients: str | Iterable[str] | None = None,
    config: EmailConfig | None = None,
    on_config_error: OnError = "raise",
    on_send_error: OnError = "swallow",
) -> SendResult:
    """Send one email via Azure Communication Services.

    Body: supply any of `markdown`, `html`, `text`. If `markdown` is given and
    `html` is not, the markdown is rendered to HTML; if `text` is not given, the
    raw markdown becomes the plain-text part. At least one body should be set.

    Config: pass an `EmailConfig`, or let it resolve from the environment.
    `recipients` (string or iterable) overrides the configured recipient list.

    Errors:
      * `on_config_error` — missing connection string / sender / recipients, or
        the Azure SDK not installed. "raise" (default) surfaces a clear error;
        "swallow" returns a skipped SendResult.
      * `on_send_error` — a delivery failure from ACS. "swallow" (default)
        returns a failed SendResult; "raise" re-raises.
    """
    if config is None:
        config = EmailConfig.from_env(recipients=recipients)
    elif recipients is not None:
        config = EmailConfig(
            connection_string=config.connection_string,
            sender=config.sender,
            recipients=parse_recipients(recipients),
        )

    # Body resolution.
    if html is None and markdown is not None:
        html = markdown_to_html(markdown)
    if text is None and markdown is not None:
        text = markdown

    missing = config.missing()
    if missing:
        reason = "email config incomplete: missing " + ", ".join(missing)
        if on_config_error == "raise":
            raise EmailConfigError(reason)
        log.warning("send_email skipped: %s", reason)
        return SendResult(sent=False, skipped_reason=reason)

    try:
        from azure.communication.email import EmailClient
    except ImportError as exc:
        reason = "azure-communication-email not installed (pip install banking-commons[email])"
        if on_config_error == "raise":
            raise EmailConfigError(reason) from exc
        log.warning("send_email skipped: %s", reason)
        return SendResult(sent=False, skipped_reason=reason)

    content: dict[str, str] = {"subject": subject}
    if text is not None:
        content["plainText"] = text
    if html is not None:
        content["html"] = html
    # ACS requires at least one body part.
    if "plainText" not in content and "html" not in content:
        content["plainText"] = ""

    message = {
        "senderAddress": config.sender,
        "recipients": {"to": [{"address": addr} for addr in config.recipients]},
        "content": content,
    }

    try:
        client = EmailClient.from_connection_string(config.connection_string)
        poller = client.begin_send(message)
        result = poller.result(timeout=120)
        # azure-communication-email >=1.0 returns a dict; older returned an
        # object with attributes. Support both.
        if isinstance(result, dict):
            status = result.get("status")
            message_id = result.get("id")
        else:
            status = getattr(result, "status", None)
            message_id = getattr(result, "message_id", None)
        log.info(
            "send_email: status=%s message_id=%s recipients=%d",
            status, message_id, len(config.recipients),
        )
        if status and status != "Succeeded":
            log.warning("send_email: non-success status %r", status)
        return SendResult(sent=True, status=status, message_id=message_id)
    except Exception as exc:  # noqa: BLE001 — fire-and-forget by default
        log.exception("send_email: delivery failed")
        if on_send_error == "raise":
            raise
        return SendResult(sent=False, error=f"{type(exc).__name__}: {exc}")
