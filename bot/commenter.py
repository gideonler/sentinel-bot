"""
Platform-agnostic dispatcher for posting/updating the Sentinel review comment.
Detects GitHub Actions vs GitLab CI from environment variables and calls
the right commenter. Each commenter reads its own env vars.
"""

import os


def _detect_platform() -> str:
    """
    Returns 'github', 'gitlab', or raises RuntimeError.
    Honours explicit SENTINEL_PLATFORM override first, then auto-detects from
    the CI-provided env vars.
    """
    override = os.environ.get("SENTINEL_PLATFORM", "").lower().strip()
    if override in ("github", "gitlab"):
        return override

    if os.environ.get("GITLAB_CI"):
        return "gitlab"
    if os.environ.get("GITHUB_ACTIONS"):
        return "github"

    raise RuntimeError(
        "Cannot detect CI platform. Set SENTINEL_PLATFORM=github|gitlab "
        "or run from GitHub Actions / GitLab CI."
    )


def post_or_update_comment(body: str) -> None:
    platform = _detect_platform()
    if platform == "gitlab":
        from bot.gitlab_commenter import post_or_update_gitlab_note
        post_or_update_gitlab_note(body)
    else:
        from bot.github_commenter import post_or_update_github_comment
        post_or_update_github_comment(body)
