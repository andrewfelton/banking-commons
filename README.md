# banking-commons

Shared utilities for the banking-policy projects
([comment_summarization](https://github.com/andrewfelton/comment_summarization),
[ai_news_feed](https://github.com/andrewfelton/ai_news_feed),
[bank-filings-pipeline](https://github.com/andrewfelton/bank-filings-pipeline),
[banking-legislation-tracker](https://github.com/andrewfelton/banking-legislation-tracker),
[congressional-transcripts](https://github.com/andrewfelton/congressional-transcripts)).

These projects each re-implemented the same plumbing. This package is the one
shared copy. First module shipped: **ACS email** (the daily-digest sender that
was copy-pasted into four repos). LLM-client and Azure-storage helpers are
planned next — see [docs/architecture.md](docs/architecture.md).

Docs:
- [docs/architecture.md](docs/architecture.md) — package design, modules, consumers.
- [docs/azure-architecture.md](docs/azure-architecture.md) — cross-project map of
  the deployed Azure resources, what's cruft, the target layout, and the P1
  cleanup runbook.

## Install

From another project's virtualenv:

```bash
pip install "banking-commons[email] @ git+https://github.com/andrewfelton/banking-commons@v0.1.0"
```

Or, for local development across sibling repos:

```bash
pip install -e "../banking-commons[email]"
```

The base install only needs `markdown`. The `[email]` extra adds
`azure-communication-email` for actual delivery.

## Email

```python
from banking_commons.email import send_email

# Markdown body — rendered to HTML, raw markdown used as the plain-text part.
send_email(
    "Banking digest — 3 updates",
    markdown="## New\n\n- HR 1234 — ...",
    recipients="me@example.com",       # or a list; falls back to env if omitted
)

# Explicit HTML + text (e.g. when you build both yourself).
send_email("Subject", html="<h2>…</h2>", text="…")
```

### Configuration

Settings resolve from the environment, accepting every spelling used across the
projects (first match wins):

| Setting           | Env vars (in priority order)                                      |
| ----------------- | ----------------------------------------------------------------- |
| Connection string | `ACS_CONNECTION_STRING`, `AZURE_COMMUNICATION_CONNECTION_STRING`   |
| Sender address    | `ACS_SENDER_ADDRESS`, `EMAIL_SENDER`                              |
| Recipients        | `DIGEST_RECIPIENT`, `DIGEST_RECIPIENTS`, `EMAIL_TO`               |

Recipients may be comma- or semicolon-separated. You can also build an
`EmailConfig` explicitly and pass it as `config=`.

### Error handling

`send_email` returns a `SendResult` (`bool(result)` is True only on a real send)
and takes two policy knobs:

- `on_config_error` — `"raise"` (default; good for Azure Functions where a
  missing setting is a deploy bug) or `"swallow"` (returns a skipped result).
- `on_send_error` — `"swallow"` (default; a mail hiccup won't break a daily
  run) or `"raise"`.

## Develop

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[email,dev]"
pytest
```
