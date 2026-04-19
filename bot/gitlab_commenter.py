"""
Posts or updates the Sentinel review note on a GitLab Merge Request.
Uses stdlib urllib so no new dependencies are required.
Idempotent: finds an existing sentinel-bot note by marker and updates it.

Env vars (auto-set by GitLab CI unless noted):
  CI_API_V4_URL              — e.g. https://gitlab.company.com/api/v4
  CI_PROJECT_ID              — numeric project id
  CI_MERGE_REQUEST_IID       — MR IID (NOT the global id)
  GITLAB_TOKEN               — Project Access Token with "api" scope
                               (must be set manually as a masked CI variable;
                               CI_JOB_TOKEN cannot post MR notes by default).
  HTTPS_PROXY / HTTP_PROXY   — honoured by urllib for the GitLab API call
                               and for LLM API calls.
"""

import json
import os
import urllib.error
import urllib.request

_MARKER = "<!-- sentinel-bot -->"
_TIMEOUT = 30


def _request(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url=url, data=data, method=method)
    req.add_header("PRIVATE-TOKEN", token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitLab API {method} {url} → {e.code}: {body}") from e


def _list_notes(api_base: str, project_id: str, mr_iid: str, token: str) -> list[dict]:
    # Paginate — a noisy MR can exceed the default page size.
    notes: list[dict] = []
    page = 1
    while True:
        url = (
            f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}"
            f"/notes?per_page=100&page={page}"
        )
        page_notes = _request("GET", url, token)
        if not page_notes:
            break
        notes.extend(page_notes)
        if len(page_notes) < 100:
            break
        page += 1
    return notes


def post_or_update_gitlab_note(body: str) -> None:
    api_base = os.environ["CI_API_V4_URL"].rstrip("/")
    project_id = os.environ["CI_PROJECT_ID"]
    mr_iid = os.environ["CI_MERGE_REQUEST_IID"]
    token = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN")
    if not token:
        raise RuntimeError(
            "Neither GITLAB_TOKEN nor CI_JOB_TOKEN is set — cannot post MR note."
        )

    existing = next(
        (n for n in _list_notes(api_base, project_id, mr_iid, token)
         if _MARKER in (n.get("body") or "")),
        None,
    )

    if existing:
        note_id = existing["id"]
        url = (
            f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}"
            f"/notes/{note_id}"
        )
        _request("PUT", url, token, {"body": body})
        print(f"Updated existing Sentinel note #{note_id}")
    else:
        url = (
            f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}/notes"
        )
        _request("POST", url, token, {"body": body})
        print("Posted new Sentinel note")
