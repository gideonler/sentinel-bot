# 🛡️ Sentinel Bot

An AI-powered pull/merge request reviewer for **GitHub and GitLab** (including on-prem GitLab). Sentinel runs on every PR/MR, analyses the diff with a dual data-engineer + application-security persona, and posts a single, structured review comment explaining **what's wrong, why it matters, and how to fix it**.

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

## Setup — GitHub

Copy `.github/workflows/pr-review.yml` into any repo you want reviewed. Then configure:

### Required secret (Settings → Secrets and variables → Actions)

Add **one** provider key (whichever you'll use):

| Secret | Provider |
|---|---|
| `ANTHROPIC_API_KEY` | Claude (recommended — most reliable structured output) |
| `GEMINI_API_KEY` | Google Gemini |
| `GROQ_API_KEY` | Groq (fast, free tier available) |

`GITHUB_TOKEN` is auto-provided — no setup needed.

### Optional variable (Variables tab)

| Variable | Default | Values |
|---|---|---|
| `SENTINEL_PROVIDER` | `anthropic` | `anthropic` / `gemini` / `groq` |

That's it. Open a PR — the bot runs automatically.

---

## Setup — GitLab (incl. on-prem / air-gapped-with-proxy)

Copy `.gitlab-ci.yml` from this repo into the target project (or include it in your existing pipeline). Then configure under **Settings → CI/CD → Variables**:

### Required

| Variable | Purpose | Notes |
|---|---|---|
| `GITLAB_TOKEN` | Posts MR notes | **Project Access Token** with `api` scope. Mark as *Masked*. `CI_JOB_TOKEN` cannot post MR notes by default, so this is required. |
| *One* of `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` | LLM auth | Mark as *Masked*. |

### Optional

| Variable | Default | Notes |
|---|---|---|
| `SENTINEL_PROVIDER` | `anthropic` | `anthropic` / `gemini` / `groq` |
| `SENTINEL_BOT_REPO` | `https://github.com/gideonler/sentinel-bot.git` | Override to your internal mirror if air-gapped from github.com |
| `SENTINEL_AGENT_REPO` | `https://github.com/gideonler/code-review-agent.git` | Same |

### Behind an HTTP proxy (HPC / corporate networks)

If your runners reach LLM APIs through a corporate proxy, set the proxy env vars **at the runner level** (`/etc/gitlab-runner/config.toml`) OR as CI/CD variables:

```
HTTPS_PROXY   http://proxy.internal:8080
HTTP_PROXY    http://proxy.internal:8080
NO_PROXY      gitlab.company.com,localhost,127.0.0.1
```

`NO_PROXY` **must** include your GitLab hostname — otherwise MR-note POSTs back to GitLab route through the external proxy and fail. Both the LLM SDK and the bot's `urllib` GitLab calls honour these vars automatically.

### Air-gapped runners

If the runners can't reach github.com (where sentinel-bot + code-review-agent are hosted), mirror both repos to your on-prem GitLab and set `SENTINEL_BOT_REPO` / `SENTINEL_AGENT_REPO` to point at the mirrors. No code changes needed.

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
├── .gitlab-ci.yml                   # GitLab CI trigger
├── review.py                        # Entrypoint — detects CI platform
├── bot/
│   ├── formatter.py                 # ReviewResult → markdown comment
│   ├── commenter.py                 # Dispatcher (GitHub vs GitLab)
│   ├── github_commenter.py          # Posts via `gh` CLI
│   └── gitlab_commenter.py          # Posts via REST v4 (urllib, no deps)
└── requirements.txt                 # Near-empty — agent brings its own deps
```

The review engine, LLM providers, diff chunker, and persona prompt all live in [`code-review-agent`](https://github.com/gideonler/code-review-agent). Sentinel imports from there; updating the agent updates every repo using Sentinel.

---

## Powered by

[Claude](https://www.anthropic.com/claude) · [Gemini](https://ai.google.dev/) · [Groq](https://groq.com/) · GitHub Actions · the [code-review-agent](https://github.com/gideonler/code-review-agent) engine
