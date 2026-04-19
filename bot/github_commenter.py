"""
Posts or updates the Sentinel review comment on a GitHub PR.
Uses the gh CLI (pre-installed on all Actions runners, authenticated via GH_TOKEN).
Idempotent: finds an existing sentinel-bot comment by marker and updates it.

Env vars (set by GitHub Actions):
  REPO            — owner/repo
  PR_NUMBER       — pull request number
  GH_TOKEN        — auto-provided by Actions (GITHUB_TOKEN)
"""

import os
import subprocess

_MARKER = "<!-- sentinel-bot -->"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True)


def post_or_update_github_comment(body: str) -> None:
    repo = os.environ["REPO"]
    pr_number = os.environ["PR_NUMBER"]

    result = _gh(
        "api",
        f"/repos/{repo}/issues/{pr_number}/comments",
        "--jq",
        f'[.[] | select(.body | contains("{_MARKER}"))] | first | .id',
    )
    comment_id = result.stdout.strip()

    if comment_id and comment_id != "null":
        _gh(
            "api", "--method", "PATCH",
            f"/repos/{repo}/issues/comments/{comment_id}",
            "--field", f"body={body}",
        )
        print(f"Updated existing Sentinel comment #{comment_id}")
    else:
        _gh(
            "pr", "comment", pr_number,
            "--repo", repo,
            "--body", body,
        )
        print("Posted new Sentinel comment")
