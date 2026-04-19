"""
Entrypoint for the Sentinel GitHub PR review bot.
Called by .github/workflows/pr-review.yml.
"""

import os
import sys
from pathlib import Path

from agent.reviewer import review_target
from agent.parser import parse_review
from bot.formatter import format_comment
from bot.commenter import post_or_update_comment

# Provider → expected env var name for its API key
_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "groq":      "GROQ_API_KEY",
}

provider   = os.environ.get("SENTINEL_PROVIDER", "anthropic").lower()
base_ref   = os.environ.get("BASE_REF", "")
pr_number  = os.environ.get("PR_NUMBER", "")
repo       = os.environ.get("REPO", "")

# Validate required env vars
errors = []
if not base_ref:   errors.append("BASE_REF")
if not pr_number:  errors.append("PR_NUMBER")
if not repo:       errors.append("REPO")
if provider not in _PROVIDER_KEY_ENV:
    print(f"Unknown provider '{provider}'. Supported: {', '.join(_PROVIDER_KEY_ENV)}", file=sys.stderr)
    sys.exit(1)

key_env = _PROVIDER_KEY_ENV[provider]
api_key = os.environ.get(key_env, "")
if not api_key:
    errors.append(key_env)

if errors:
    print(f"Missing required environment variables: {', '.join(errors)}", file=sys.stderr)
    sys.exit(1)


def _post_status_comment(title: str, body: str) -> None:
    post_or_update_comment(
        repo, pr_number,
        f"{title}\n\n{body}\n\n<!-- sentinel-bot -->",
    )


try:
    review_text, _ = review_target(
        str(Path.cwd()),
        stream=False,
        provider_name=provider,
        api_key=api_key,
        save=False,
        diff_ref=base_ref,
    )
except Exception as exc:
    # Distinguish rate-limit / quota errors from real failures so a quota hit
    # doesn't look like a broken bot in the PR. Duck-type the exception by
    # class name + message so we don't need to import each provider's SDK.
    msg = str(exc)
    exc_name = type(exc).__name__
    is_rate_limit = (
        "RateLimitError" in exc_name
        or "rate_limit" in msg.lower()
        or "429" in msg
        or "quota" in msg.lower()
    )
    if is_rate_limit:
        print(f"Sentinel: rate limit hit on provider={provider}: {msg}", file=sys.stderr)
        _post_status_comment(
            "## ⏳ Sentinel Review — Rate Limited",
            f"The `{provider}` provider hit its token / request quota while reviewing this PR.\n\n"
            f"**Push another commit** or **re-run this workflow** once the quota resets to get a full review.\n\n"
            f"<details><summary>Raw error</summary>\n\n```\n{msg}\n```\n\n</details>",
        )
        sys.exit(0)
    # Unknown error → surface it in the PR AND fail the workflow (red X is correct here).
    print(f"Sentinel: unexpected error: {msg}", file=sys.stderr)
    _post_status_comment(
        "## ❌ Sentinel Review — Error",
        f"The review failed with an unexpected error on provider `{provider}`. "
        f"Check the Actions log for the full traceback.\n\n"
        f"<details><summary>Error</summary>\n\n```\n{exc_name}: {msg}\n```\n\n</details>",
    )
    raise

if not review_text or review_text.startswith("No reviewable files"):
    _post_status_comment(
        "## ⚪ Sentinel Review — Skipped",
        "No reviewable files found in this diff (only docs, configs, or test files changed).",
    )
    sys.exit(0)

result = parse_review(review_text)
comment = format_comment(result)
post_or_update_comment(repo, pr_number, comment)

print(f"Sentinel: done — verdict: {result.verdict}  provider: {provider}")
