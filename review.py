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


review_text, _ = review_target(
    str(Path.cwd()),
    stream=False,
    provider_name=provider,
    api_key=api_key,
    save=False,
    diff_ref=base_ref,
)

if not review_text or review_text.startswith("No reviewable files"):
    body = (
        "## ⚪ Sentinel Review — SKIPPED\n\n"
        "No reviewable files found in this diff (only docs, configs, or test files changed).\n\n"
        "<!-- sentinel-bot -->"
    )
    post_or_update_comment(repo, pr_number, body)
    sys.exit(0)

result = parse_review(review_text)
comment = format_comment(result)
post_or_update_comment(repo, pr_number, comment)

print(f"Sentinel: done — verdict: {result.verdict}  provider: {provider}")
