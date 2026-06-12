# Architecture

`banking-commons` is a small shared library for the banking-policy projects. It
exists to kill copy-paste plumbing, **not** to merge those projects — each keeps
its own repo, deployment, and data lifecycle. This package holds only the parts
that were genuinely duplicated.

## Why a package, not a monorepo

The consumers deploy very differently (Azure Functions, macOS `launchd`, local
cron) and have wildly different dependency weight (the transcripts project pulls
torch/whisper; the legislation tracker is ~1k LOC). A monorepo would couple
those lifecycles. A pip-installable package shares code without coupling deploys.
Consumers pin a tag (`@v0.1.0`) so an upstream change can't silently break a
daily run.

## Layout

```
src/banking_commons/
  email/            # ACS digest delivery  (shipped)
    config.py       #   EmailConfig + env-alias resolution
    markdown.py     #   markdown_to_html (extra + sane_lists)
    client.py       #   send_email -> SendResult
  llm/              # provider-agnostic LLM client       (planned)
  storage/          # Azure Tables state/dedup helpers    (planned)
```

## email

The four original implementations diverged on three axes; the shared module
absorbs each:

| Axis              | Variation across projects                              | How it's handled                                   |
| ----------------- | ------------------------------------------------------ | -------------------------------------------------- |
| Env var names     | `ACS_*` vs `AZURE_COMMUNICATION_*` / `EMAIL_*`          | `EmailConfig.from_env` tries all aliases           |
| Body input        | markdown-only vs pre-built html+text                   | `send_email` accepts `markdown=` or `html=`/`text=` |
| Failure policy    | best-effort (local) vs fail-fast (Functions)           | `on_config_error` / `on_send_error` knobs          |
| Return value      | `bool` vs status string vs `None`                      | uniform `SendResult` (`__bool__` == sent)          |

Per-project email *content* (subject lines, the HTML table of dockets/bills)
stays in each project — only the render+send mechanism is shared.

## Planned modules

- **llm** — lift `ai_news_feed`'s `LLMClient` (already abstracts
  Anthropic/OpenAI/Google + tool use). Lets the OpenAI-only and Anthropic-only
  projects switch providers and share retry/backoff.
- **storage** — Azure Tables client init + upsert + watermark/dedup primitives
  (currently hand-rolled in three projects as `PaperTracker`, `FilingsManifest`,
  `StateStore`). Each project keeps its own row schema on top.

## Migration order

1. **email** into one consumer as a proof of concept (`comment_summarization`).
2. Roll email out to the other three email senders.
3. Extract `llm`, then `storage`, the same way: superset module, one consumer,
   then roll out.
