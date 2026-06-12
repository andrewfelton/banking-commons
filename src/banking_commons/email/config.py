"""Resolve ACS email configuration from the environment.

The existing projects use different env-var names for the same three settings.
This module accepts every spelling seen in the wild so a single shared sender
works whether the consumer's `.env` says `ACS_CONNECTION_STRING` (comment
summarization) or `AZURE_COMMUNICATION_CONNECTION_STRING` (ai_news_feed,
bank-filings). First match wins, in the order listed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

# Aliases in priority order. Add new spellings here, not in calling code.
_CONNECTION_VARS = ("ACS_CONNECTION_STRING", "AZURE_COMMUNICATION_CONNECTION_STRING")
_SENDER_VARS = ("ACS_SENDER_ADDRESS", "EMAIL_SENDER")
_RECIPIENT_VARS = ("DIGEST_RECIPIENT", "DIGEST_RECIPIENTS", "EMAIL_TO")


def parse_recipients(raw: str | Iterable[str] | None) -> list[str]:
    """Normalize a recipient spec into a clean list of addresses.

    Accepts a single string (comma- or semicolon-separated), an iterable of
    strings (each of which may itself be separated), or None. Whitespace and
    empty entries are dropped.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]
    out: list[str] = []
    for chunk in raw:
        out.extend(parse_recipients(chunk))
    return out


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


@dataclass
class EmailConfig:
    """Everything needed to send via Azure Communication Services Email."""

    connection_string: str
    sender: str
    recipients: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, *, recipients: str | Iterable[str] | None = None) -> "EmailConfig":
        """Build from environment variables (see the alias lists above).

        `recipients`, if given, overrides whatever the env would supply — useful
        when the recipient list is computed rather than configured.
        """
        return cls(
            connection_string=_first_env(_CONNECTION_VARS) or "",
            sender=_first_env(_SENDER_VARS) or "",
            recipients=(
                parse_recipients(recipients)
                if recipients is not None
                else parse_recipients(_first_env(_RECIPIENT_VARS))
            ),
        )

    def missing(self) -> list[str]:
        """Names of the required fields that are unset. Empty list == ready."""
        gaps = []
        if not self.connection_string:
            gaps.append("connection_string")
        if not self.sender:
            gaps.append("sender")
        if not self.recipients:
            gaps.append("recipients")
        return gaps
