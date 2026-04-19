"""
Entrypoint for the Sentinel PR / MR review bot.
Works on GitHub Actions and GitLab CI — the commenter module auto-detects
which one it's running under.
"""

import os
import sys
from pathlib import Path

from agent.reviewer import review_target
from agent.parser import parse_review
from bot.formatter import format_comment
from bot.commenter import post_or_update_comment

_PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "groq":      "GROQ_API_KEY",
}


def _resolve_base_ref() -> str:
    """
    Resolve the git ref to diff against. Honours an explicit BASE_REF env var
    (used by the GitHub workflow) and otherwise derives from GitLab CI vars.
    """
    explicit = os.environ.get("BASE_REF", "").strip()
    if explicit:
        return explicit

    gitlab_target = os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "").strip()
    if gitlab_target:
        return f"origin/{gitlab_target}"

    return ""


provider = os.environ.get("SENTINEL_PROVIDER", "anthropic").lower()
base_ref = _resolve_base_ref()

if provider not in _PROVIDER_KEY_ENV:
    print(
        f"Unknown provider '{provider}'. Supported: {', '.join(_PROVIDER_KEY_ENV)}",
        file=sys.stderr,
    )
    sys.exit(1)

key_env = _PROVIDER_KEY_ENV[provider]
api_key = os.environ.get(key_env, "")

missing = []
if not base_ref:
    missing.append("BASE_REF (or CI_MERGE_REQUEST_TARGET_BRANCH_NAME)")
if not api_key:
    missing.append(key_env)
if missing:
    print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)


def _post_status(title: str, body: str) -> None:
    post_or_update_comment(f"{title}\n\n{body}\n\n<!-- sentinel-bot -->")


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
        _post_status(
            "## ⏳ Sentinel Review — Rate Limited",
            f"The `{provider}` provider hit its token / request quota while reviewing this PR.\n\n"
            f"**Push another commit** or **re-run this job** once the quota resets to get a full review.\n\n"
            f"<details><summary>Raw error</summary>\n\n```\n{msg}\n```\n\n</details>",
        )
        sys.exit(0)
    # Unknown error → surface it in the PR AND fail the workflow (red X is correct here).
    print(f"Sentinel: unexpected error: {msg}", file=sys.stderr)
    _post_status(
        "## ❌ Sentinel Review — Error",
        f"The review failed with an unexpected error on provider `{provider}`. "
        f"Check the CI log for the full traceback.\n\n"
        f"<details><summary>Error</summary>\n\n```\n{exc_name}: {msg}\n```\n\n</details>",
    )
    raise

if not review_text or review_text.startswith("No reviewable files"):
    _post_status(
        "## ⚪ Sentinel Review — Skipped",
        "No reviewable files found in this diff (only docs, configs, or test files changed).",
    )
    sys.exit(0)

result = parse_review(review_text)
post_or_update_comment(format_comment(result))
print(f"Sentinel: done — verdict: {result.verdict}  provider: {provider}")
