# 🛡️ Sentinel Bot

An AI-powered pull request reviewer for GitHub. Sentinel runs on every PR, analyses the diff with a dual data-engineer + application-security persona, and posts a single, structured review comment explaining **what's wrong, why it matters, and how to fix it**.

Sentinel is the delivery layer — the actual review logic lives in [`code-review-agent`](https://github.com/gideonler/code-review-agent).

---

## What it catches

| Category | Examples |
|---|---|
| **🔒 Security** | SQL / command injection, hardcoded secrets, weak crypto (MD5/SHA1), missing auth, unsafe deserialisation |
| **📊 Data integrity** | Missing schema validation, silent type coercion, unchecked null handling |
| **⚙️ Reliability** | No retries, missing timeouts, unbounded loops, no DLQ, goroutine leaks, `defer` in loops |
| **🔥 PySpark anti-patterns** | `crossJoin` without filter, `collect()` on large dataframes, UDFs where native functions exist |
| **☁️ AWS misconfig** | Default 3s Lambda timeout, unencrypted S3, overly permissive IAM, missing SQS DLQ |

Every finding is tagged with an **OWASP Top 10 2021** ID and a **CWE** reference, so the review doubles as an audit artefact.

---

## How it works

```
┌──────────────┐   pull_request event   ┌────────────────────┐
│  Your repo   │ ─────────────────────▶ │ .github/workflows/ │
└──────────────┘                        │   pr-review.yml    │
                                        └─────────┬──────────┘
                                                  │
                                                  ▼
┌──────────────────────────────────────────────────────────┐
│  1. Checkout PR branch (full history) + agent + bot     │
│  2. pip install -e ./code-review-agent                  │
│  3. git diff origin/<base> → per-file chunks            │
│  4. Send chunks to LLM (Anthropic / Gemini / Groq)      │
│  5. Parse structured findings (severity, OWASP, CWE)    │
│  6. Render GitHub markdown                              │
│  7. Post/update PR comment via gh CLI                   │
└──────────────────────────────────────────────────────────┘
```

Only changed files are reviewed. The comment is updated in place on every push (no spam).

---

## Setup — adding Sentinel to a repo

Copy `.github/workflows/pr-review.yml` into any repo you want reviewed. Then configure these on the repo:

### Required secrets
`Settings → Secrets and variables → Actions → New repository secret`

Add **one** provider key (whichever you'll use):

| Secret | Provider |
|---|---|
| `ANTHROPIC_API_KEY` | Claude (recommended — most reliable structured output) |
| `GEMINI_API_KEY` | Google Gemini |
| `GROQ_API_KEY` | Groq (fast, free tier available) |

`GITHUB_TOKEN` is auto-provided by Actions — no setup needed.

### Optional variable
`Settings → Secrets and variables → Actions → Variables tab`

| Variable | Default | Values |
|---|---|---|
| `SENTINEL_PROVIDER` | `anthropic` | `anthropic` / `gemini` / `groq` |

That's it. Open a PR — the bot runs automatically.

---

## Verdicts

| Banner | Meaning |
|---|---|
| 🔴 **BLOCKED** | One or more BLOCKER findings — do not merge |
| 🟠 **REQUEST CHANGES** | HIGH findings need attention before merge |
| 🟡 **APPROVED WITH MINOR NOTES** | Safe to merge; MEDIUM/LOW to track |
| 🟢 **APPROVED** | No blocking issues found |

---

## What Sentinel does NOT do (today)

- **Reviews only the diff** — existing bugs in untouched files are invisible
- **No inline review comments** — posts one consolidated comment, not line-anchored suggestions
- **No merge gate** — verdicts are advisory; the workflow never fails
- **No dependency / CVE scanning** — flagged in prompt for manual check; no `pip-audit` or `govulncheck` integration yet
- **No cross-file reasoning** — each file chunk is reviewed mostly in isolation

---

## Project layout

```
sentinel-bot/
├── .github/workflows/pr-review.yml  # GitHub Actions trigger
├── review.py                        # Entrypoint — orchestrates the review
├── bot/
│   ├── formatter.py                 # ReviewResult → GitHub markdown
│   └── commenter.py                 # Idempotent post/update via gh CLI
└── requirements.txt                 # Near-empty — agent brings its own deps
```

The review engine, LLM providers, diff chunker, and persona prompt all live in [`code-review-agent`](https://github.com/gideonler/code-review-agent). Sentinel imports from there; updating the agent updates every repo using Sentinel.

---

## Powered by

[Claude](https://www.anthropic.com/claude) · [Gemini](https://ai.google.dev/) · [Groq](https://groq.com/) · GitHub Actions · the [code-review-agent](https://github.com/gideonler/code-review-agent) engine
