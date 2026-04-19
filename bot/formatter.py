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

# Plain-English one-liners shown next to OWASP tags so reviewers don't have
# to remember what A01-A10 mean.
_OWASP_EXPLAINER = {
    "A01": "Broken access control — someone can reach things they shouldn't",
    "A02": "Cryptographic failure — weak or missing encryption of sensitive data",
    "A03": "Injection — untrusted input mixed into code, queries, or commands",
    "A04": "Insecure design — flaw in the security model, not a bug on one line",
    "A05": "Security misconfiguration — unsafe defaults or missing hardening",
    "A06": "Vulnerable / outdated component — known-bad dependency",
    "A07": "Authentication failure — broken login, session, or identity check",
    "A08": "Integrity failure — unverified update path or supply chain gap",
    "A09": "Logging & monitoring gap — can't detect or investigate attacks",
    "A10": "Server-side request forgery — server tricked into making requests",
}

# Plain-English framing per category — sets the reader's expectation before
# they dive into Problem / Why it matters.
_CATEGORY_EXPLAINER = {
    "SECURITY":       "🔒 Security vulnerability — attacker-exploitable weakness",
    "DATA_INTEGRITY": "📊 Data integrity risk — silent corruption or loss",
    "RELIABILITY":    "⚙️ Reliability risk — will cause production incidents",
    "PERFORMANCE":    "🐢 Performance issue — slow or resource-hungry code",
    "PYSPARK":        "🔥 PySpark anti-pattern — inefficient or unsafe Spark",
    "GOLANG":         "🐹 Go bug — idiomatic or concurrency issue",
    "AWS":            "☁️ AWS misconfiguration — cloud resource set up unsafely",
    "STYLE":          "✨ Code style — readability or convention",
}

_SEVERITY_EXPLAINER = {
    Severity.BLOCKER: "must fix before merge — security or data-loss risk",
    Severity.HIGH:    "should fix before merge — production reliability risk",
    Severity.MEDIUM:  "fix in follow-up — quality or minor security hygiene",
    Severity.LOW:     "suggestion — better practice worth adopting",
    Severity.INFO:    "observation — no action required",
}

_MAX_CODE_CHARS = 500
_BOT_MARKER = "<!-- sentinel-bot -->"


def _truncate(text: str, limit: int = _MAX_CODE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"


def _owasp_explainer(owasp: str) -> str:
    """For an OWASP tag like 'A03: Injection', return the plain-English meaning."""
    if not owasp:
        return ""
    code = owasp.split(":", 1)[0].strip().upper()
    return _OWASP_EXPLAINER.get(code, "")


def _render_finding(f) -> str:
    lines: list[str] = []

    # Location header — file · line
    loc = f"`{f.file}`" if f.file else ""
    if f.file and f.line:
        loc += f" · line {f.line}"
    if loc:
        lines.append(f"📄 {loc}")

    # Plain-English category framing — tells the reader what *kind* of problem this is
    explainer = _CATEGORY_EXPLAINER.get(f.category.upper(), f"[{f.category}]")
    lines.append(f"**{explainer}**")

    # OWASP / CWE framework tags, with an inline translation so non-security-folk
    # don't have to look up what A03 means.
    if f.owasp:
        owasp_text = _owasp_explainer(f.owasp)
        if owasp_text:
            lines.append(f"> 🏷️ **OWASP {f.owasp}** — {owasp_text}")
        else:
            lines.append(f"> 🏷️ **OWASP {f.owasp}**")
    if f.cwe:
        lines.append(f"> 🏷️ **{f.cwe}**")

    if getattr(f, "cve_id", ""):
        cvss_str = f" · CVSS {f.cvss_score}" if f.cvss_score else ""
        sev_str  = f" · {f.cvss_severity}" if getattr(f, "cvss_severity", "") else ""
        lines.append(f"> 🔗 **{f.cve_id}**{cvss_str}{sev_str}")

    # What's wrong — direct, grounded in the code
    if f.problem:
        lines.append(f"\n**❌ What's wrong**")
        lines.append(f"{f.problem}")

    # Why it matters — blockquoted so the *reason* stands out. This is the part
    # a hurried reviewer reads if they read nothing else.
    if f.impact:
        lines.append(f"\n**💥 Why it matters**")
        lines.append(f"> {f.impact}")

    # Current code + proposed fix, collapsed to keep the comment scannable
    if f.current_code or f.fix:
        code_blocks: list[str] = []
        if f.current_code:
            code_blocks.append(
                "<details>\n<summary>🔍 Current code</summary>\n\n"
                f"```\n{_truncate(f.current_code)}\n```\n\n</details>"
            )
        if f.fix:
            code_blocks.append(
                "<details>\n<summary>✅ Suggested fix</summary>\n\n"
                f"```\n{_truncate(f.fix)}\n```\n\n</details>"
            )
        lines.append("\n" + "\n".join(code_blocks))

    return "\n".join(lines)


def format_comment(result: ReviewResult) -> str:
    parts: list[str] = []

    banner = _VERDICT_BANNER.get(result.verdict, "## Sentinel Review")
    parts.append(banner)

    if result.summary:
        parts.append(f"\n{result.summary}")

    # Stats table
    parts.append("\n| Severity | Count | Meaning |")
    parts.append("|----------|------:|---------|")
    for sev in Severity:
        count = sum(1 for f in result.findings if f.severity == sev)
        if count > 0:
            parts.append(
                f"| {_SEV_EMOJI[sev]} **{sev.value}** | {count} | {_SEVERITY_EXPLAINER[sev]} |"
            )

    if not result.findings:
        parts.append("\n_No findings._")
    else:
        parts.append("\n---\n\n### 🔎 Findings\n")
        parts.append(
            "_Each finding explains **what's wrong**, **why it matters** (the attack path "
            "or failure mode), and a **suggested fix**._\n"
        )
        for sev in Severity:
            group = [f for f in result.findings if f.severity == sev]
            if not group:
                continue

            count_label = f"{len(group)} finding{'s' if len(group) > 1 else ''}"
            summary_label = f"{_SEV_EMOJI[sev]} <b>{sev.value}</b> — {count_label}"

            block = (
                f"<details open>\n<summary>{summary_label}</summary>\n\n"
                + "\n\n---\n\n".join(_render_finding(f) for f in group)
                + "\n\n</details>\n"
            )
            parts.append(block)

    if result.positive_notes:
        parts.append("\n---\n\n### 👍 What was done well\n")
        parts.append(result.positive_notes)

    parts.append(
        f"\n---\n"
        f"<sub>🛡️ <b>Sentinel AI Review</b> · reviews the diff against OWASP Top 10, "
        f"CWE, and internal data-engineering rules · "
        f"<a href='https://github.com/gideonler/code-review-agent'>how it works</a></sub>\n"
        f"{_BOT_MARKER}"
    )

    return "\n".join(parts)
