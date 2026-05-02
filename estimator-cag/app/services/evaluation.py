import re

from app.schemas.estimation import StructureCheck

_OK_FINISH_REASONS = {"stop", "end_turn"}

_TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<task>[^|]+?)\s*\|\s*(?P<hours>[\d.,]+)\s*\|\s*(?P<cost>[\d.,\sEURer]+)\s*\|\s*$",
    re.MULTILINE,
)
_HEADER_ROW_RE = re.compile(r"\|\s*Task\s*\|\s*Hours\s*\|\s*Cost", re.IGNORECASE)
_SEPARATOR_ROW_RE = re.compile(r"^\|\s*[-: ]+\|", re.MULTILINE)
_TOTAL_HOURS_RE = re.compile(r"Total\s+hours[:\*\s]*([\d.,]+)", re.IGNORECASE)
_TOTAL_COST_RE = re.compile(r"Total\s+cost[:\*\s]*([\d.,]+)", re.IGNORECASE)


def _to_int(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else None


def evaluate_estimation_structure(text: str, finish_reason: str) -> StructureCheck:
    """Run Level-1 structural checks against a generated estimation.

    Pure regex/parsing — no LLM call. Provides a quick, automatable signal
    on whether the model produced a well-formed estimation.
    """
    has_title = bool(re.search(r"^##\s+\S", text, re.MULTILINE))
    has_breakdown_table = bool(_HEADER_ROW_RE.search(text))
    has_totals_section = bool(_TOTAL_HOURS_RE.search(text)) and bool(_TOTAL_COST_RE.search(text))
    has_team_section = bool(
        re.search(
            r"(Recommended\s+Team|Team(\s+composition)?|^\s*-\s+\d+\s+\w+\s+(Developer|Designer|Engineer))",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
    )
    has_duration_section = bool(
        re.search(r"(Estimated\s+Duration|Duration:|\bweeks?\b)", text, re.IGNORECASE)
    )

    sum_hours, sum_cost = None, None
    if has_breakdown_table:
        running_h = running_c = 0
        found = False
        for m in _TABLE_ROW_RE.finditer(text):
            if m.group("task").strip().lower() in {"task", ""} or _SEPARATOR_ROW_RE.match(m.group(0)):
                continue
            h, c = _to_int(m.group("hours")), _to_int(m.group("cost"))
            if h is not None and c is not None:
                running_h += h
                running_c += c
                found = True
        if found:
            sum_hours, sum_cost = running_h, running_c

    m_h = _TOTAL_HOURS_RE.search(text)
    m_c = _TOTAL_COST_RE.search(text)
    declared_total_hours = _to_int(m_h.group(1)) if m_h else None
    declared_total_cost = _to_int(m_c.group(1)) if m_c else None

    hours_match: bool | None = (
        abs(sum_hours - declared_total_hours) <= 1
        if sum_hours is not None and declared_total_hours is not None
        else None
    )
    cost_match: bool | None = (
        abs(sum_cost - declared_total_cost) / declared_total_cost <= 0.02
        if sum_cost is not None and declared_total_cost
        else None
    )
    finish_reason_ok = finish_reason in _OK_FINISH_REASONS

    flag_checks: list[tuple[bool, str]] = [
        (has_title,            "Missing H2 project title"),
        (has_breakdown_table,  "Missing breakdown table with 'Task | Hours | Cost' header"),
        (has_totals_section,   "Missing totals section ('Total hours' / 'Total cost')"),
        (has_team_section,     "Missing recommended team section"),
        (has_duration_section, "Missing estimated duration in weeks"),
        (bool(hours_match),    f"Total hours mismatch: declared {declared_total_hours} vs sum of rows {sum_hours}"),
        (bool(cost_match),     f"Total cost mismatch: declared {declared_total_cost} vs sum of rows {sum_cost}"),
        (finish_reason_ok,     f"Response truncated or unexpected finish_reason='{finish_reason}'"),
    ]
    score = round(sum(ok for ok, _ in flag_checks) / len(flag_checks), 3)
    issues = [msg for ok, msg in flag_checks if not ok]

    return StructureCheck(
        has_title=has_title,
        has_breakdown_table=has_breakdown_table,
        has_totals_section=has_totals_section,
        has_team_section=has_team_section,
        has_duration_section=has_duration_section,
        declared_total_hours=declared_total_hours,
        sum_row_hours=sum_hours,
        hours_match=hours_match,
        declared_total_cost=float(declared_total_cost) if declared_total_cost is not None else None,
        sum_row_cost=float(sum_cost) if sum_cost is not None else None,
        cost_match=cost_match,
        finish_reason_ok=finish_reason_ok,
        score=score,
        issues=issues,
    )
