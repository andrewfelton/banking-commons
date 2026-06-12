"""ACS email delivery shared across the banking-policy projects.

    from banking_commons.email import send_email
    send_email("Subject", markdown="# Hello", recipients="me@example.com")
"""
from .client import EmailConfigError, SendResult, send_email
from .config import EmailConfig, parse_recipients
from .markdown import markdown_to_html

__all__ = [
    "send_email",
    "SendResult",
    "EmailConfigError",
    "EmailConfig",
    "parse_recipients",
    "markdown_to_html",
]
