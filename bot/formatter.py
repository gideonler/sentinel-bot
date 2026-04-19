"""
Converts a ReviewResult into a GitHub PR comment (markdown).
Uses <details> blocks for collapsible finding groups.
"""

from agent.parser import ReviewResult, Severity, Verdict

_VERDICT_BANNER = {
    Verdict.BLOCK: (
        "## 🔴 Sentinel Review — BLOCKED\n"
        "> **Hard stop:** One or more BLOCKER findings must be resolved before this PR can merge."
    ),
    Verdict.REQUEST_CHANGES: (
        "## 🟠 Sentinel Review — REQUEST CHANGES\n"
        "> HIGH severity findings require attention before merging."
    ),
    Verdict.APPROVE_WITH_NOTES: (
        "## 🟡 Sentinel Review — APPROVED WITH MINOR NOTES\n"
        "> Safe to merge. MEDIUM/LOW findings should be tracked for follow-up."
    ),
    Verdict.APPROVE: (
        "## 🟢 Sentinel Review — APPROVED\n"
        "> No blocking issues found. Safe to merge."
    ),
}

_SEV_EMOJI = {
    Severity.BLOCKER: "🔴",
    Severity.HIGH:    "🟠",
    Severity.MEDIUM:  "🟡",
    Severity.LOW:     "🟢",
    Severity.INFO:    "🔵",
}

_MAX_CODE_CHARS = 500
_BOT_MARKER = "<!-- sentinel-bot -->"


def _truncate(text: str, limit: int = _MAX_CODE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"


def format_comment(result: ReviewResult) -> str:
    parts: list[str] = []

    # Verdict banner
    verdict_val = result.verdict
    banner = _VERDICT_BANNER.get(verdict_val, "## Sentinel Review")
    parts.append(banner)

    # Summary
    if result.summary:
        parts.append(f"\n{result.summary}")

    # Stats table
    parts.append("\n| Severity | Count |")
    parts.append("|----------|-------|")
    for sev in Severity:
        count = sum(1 for f in result.findings if f.severity == sev)
        if count > 0:
            parts.append(f"| {_SEV_EMOJI[sev]} {sev.value} | {count} |")

    if not result.findings:
        parts.append("\n_No findings._")
    else:
        parts.append("\n---\n\n### Findings\n")
        for sev in Severity:
            group = [f for f in result.findings if f.severity == sev]
            if not group:
                continue

            count_label = f"{len(group)} finding{'s' if len(group) > 1 else ''}"
            summary_label = f"{_SEV_EMOJI[sev]} {sev.value} ({count_label})"

            inner_parts: list[str] = []
            for f in group:
                loc = f"`{f.file}`" if f.file else ""
                if f.file and f.line:
                    loc += f" · line {f.line}"

                lines: list[str] = []

                # Header line
                header = f"**[{f.category}]"
                if loc:
                    header += f" {loc}"
                header += "**"
                lines.append(header)

                if f.owasp or f.cwe:
                    tags = "  ".join(filter(None, [
                        f"`OWASP {f.owasp}`" if f.owasp else "",
                        f"`{f.cwe}`" if f.cwe else "",
                    ]))
                    lines.append(f"_{tags}_")

                if getattr(f, "cve_id", ""):
                    cvss_str = f" · CVSS {f.cvss_score}" if f.cvss_score else ""
                    sev_str  = f" · {f.cvss_severity}" if getattr(f, "cvss_severity", "") else ""
                    lines.append(f"_🔗 `{f.cve_id}`{cvss_str}{sev_str}_")

                if f.problem:
                    lines.append(f"\n**Problem:** {f.problem}")
                if f.impact:
                    lines.append(f"**Impact:** {f.impact}")

                if f.current_code or f.fix:
                    code_parts: list[str] = []
                    if f.current_code:
                        code_parts.append(
                            "<details>\n<summary>❌ Current code</summary>\n\n"
                            f"```\n{_truncate(f.current_code)}\n```\n\n</details>"
                        )
                    if f.fix:
                        code_parts.append(
                            "<details>\n<summary>✅ Suggested fix</summary>\n\n"
                            f"```\n{_truncate(f.fix)}\n```\n\n</details>"
                        )
                    lines.append("\n" + "\n".join(code_parts))

                inner_parts.append("\n".join(lines))

            block = (
                f"<details>\n<summary>{summary_label}</summary>\n\n"
                + "\n\n---\n\n".join(inner_parts)
                + "\n\n</details>\n"
            )
            parts.append(block)

    # Positive notes
    if result.positive_notes:
        parts.append("\n---\n\n### What was done well\n")
        parts.append(result.positive_notes)

    # Bot marker for idempotent updates
    parts.append(f"\n---\n<sub>🛡️ Sentinel AI Review · powered by Claude</sub>\n{_BOT_MARKER}")

    return "\n".join(parts)
