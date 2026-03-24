"""
Cerasus Hub — DA Generator: CEIS Discipline Engine v5.6 Prompt Templates
Builds system prompts and user messages for each step of the DA generation pipeline.
"""

import json
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_intake(intake_data: dict) -> str:
    """Format intake_data dict into a readable block for the user message."""
    lines = []

    # Employee info
    if intake_data.get("employee_name"):
        lines.append(f"Employee: {intake_data['employee_name']}")
    if intake_data.get("employee_id"):
        lines.append(f"Employee ID: {intake_data['employee_id']}")
    if intake_data.get("job_title"):
        lines.append(f"Title: {intake_data['job_title']}")
    if intake_data.get("department"):
        lines.append(f"Department: {intake_data['department']}")
    if intake_data.get("hire_date"):
        lines.append(f"Hire Date: {intake_data['hire_date']}")
    if intake_data.get("supervisor"):
        lines.append(f"Supervisor: {intake_data['supervisor']}")

    # Incident details
    lines.append("")
    if intake_data.get("incident_date"):
        lines.append(f"Incident Date: {intake_data['incident_date']}")
    if intake_data.get("incident_time"):
        lines.append(f"Incident Time: {intake_data['incident_time']}")
    if intake_data.get("incident_location"):
        lines.append(f"Location: {intake_data['incident_location']}")
    if intake_data.get("incident_type"):
        lines.append(f"Incident Type: {intake_data['incident_type']}")

    # Narrative / description
    if intake_data.get("incident_description"):
        lines.append("")
        lines.append("--- Incident Description ---")
        lines.append(intake_data["incident_description"])

    # Witnesses
    if intake_data.get("witnesses"):
        lines.append("")
        lines.append("--- Witnesses ---")
        if isinstance(intake_data["witnesses"], list):
            for w in intake_data["witnesses"]:
                lines.append(f"  - {w}")
        else:
            lines.append(str(intake_data["witnesses"]))

    # Prior disciplinary record
    if intake_data.get("prior_record"):
        lines.append("")
        lines.append("--- Prior Disciplinary Record ---")
        if isinstance(intake_data["prior_record"], list):
            for rec in intake_data["prior_record"]:
                if isinstance(rec, dict):
                    parts = []
                    if rec.get("date"):
                        parts.append(rec["date"])
                    if rec.get("level"):
                        parts.append(rec["level"])
                    if rec.get("reason"):
                        parts.append(rec["reason"])
                    lines.append(f"  - {' | '.join(parts)}")
                else:
                    lines.append(f"  - {rec}")
        else:
            lines.append(str(intake_data["prior_record"]))

    # Attendance record (Type A violations)
    if intake_data.get("attendance_record"):
        lines.append("")
        lines.append("--- Attendance Record ---")
        att = intake_data["attendance_record"]
        if isinstance(att, dict):
            if att.get("occurrences"):
                lines.append(f"  Total Occurrences: {att['occurrences']}")
            if att.get("period"):
                lines.append(f"  Period: {att['period']}")
            if att.get("unexcused_absences"):
                lines.append(f"  Unexcused Absences: {att['unexcused_absences']}")
            if att.get("tardies"):
                lines.append(f"  Tardies: {att['tardies']}")
            if att.get("ncns"):
                lines.append(f"  No-Call/No-Show: {att['ncns']}")
            if att.get("details"):
                lines.append("  Details:")
                if isinstance(att["details"], list):
                    for d in att["details"]:
                        lines.append(f"    - {d}")
                else:
                    lines.append(f"    {att['details']}")
        elif isinstance(att, list):
            for entry in att:
                lines.append(f"  - {entry}")
        else:
            lines.append(str(att))

    # Policies cited by intake author
    if intake_data.get("policies_cited"):
        lines.append("")
        lines.append("--- Policies Cited by Intake Author ---")
        if isinstance(intake_data["policies_cited"], list):
            for p in intake_data["policies_cited"]:
                lines.append(f"  - {p}")
        else:
            lines.append(str(intake_data["policies_cited"]))

    # Supporting documents
    if intake_data.get("supporting_docs"):
        lines.append("")
        lines.append("--- Supporting Documents ---")
        if isinstance(intake_data["supporting_docs"], list):
            for doc in intake_data["supporting_docs"]:
                lines.append(f"  - {doc}")
        else:
            lines.append(str(intake_data["supporting_docs"]))

    # Any additional notes
    if intake_data.get("additional_notes"):
        lines.append("")
        lines.append("--- Additional Notes ---")
        lines.append(str(intake_data["additional_notes"]))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1. Clarifying Questions (Step 2)
# ---------------------------------------------------------------------------

def build_clarifying_questions_prompt(intake_data: dict) -> tuple[str, str]:
    """
    Build prompts for Step 2: identify factual gaps in the intake.
    Returns (system_prompt, user_message).
    """
    system_prompt = (
        "You are a labor relations analyst reviewing a disciplinary action intake form. "
        "Your task is to identify factual gaps or missing information that would weaken "
        "the disciplinary action if left unaddressed.\n\n"
        "Rules:\n"
        "- Ask targeted clarifying questions ONLY about information that is genuinely missing.\n"
        "- Do NOT ask generic or boilerplate questions.\n"
        "- Do NOT ask about information already provided in the intake.\n"
        "- Focus on facts needed for policy citation accuracy, progressive discipline "
        "sequencing, and evidentiary completeness.\n"
        "- Consider whether the intake supports the claimed violation type "
        "(Type A Attendance / Type B Performance-Conduct / Type C Employment Review).\n"
        "- If attendance data is referenced but specific dates or occurrence counts are "
        "missing, ask for them.\n"
        "- If prior discipline is mentioned but details are vague, ask for specifics.\n\n"
        "Response format:\n"
        "- Return questions as a numbered list (1. 2. 3. etc.).\n"
        "- Each question should be one concise sentence.\n"
        "- If the intake is complete and no factual gaps exist, respond with exactly: "
        "NO_GAPS_FOUND"
    )

    formatted = _format_intake(intake_data)
    user_message = (
        "Review the following disciplinary action intake and identify any factual gaps.\n\n"
        f"{formatted}"
    )

    return system_prompt, user_message


# ---------------------------------------------------------------------------
# 2. CEIS Engine (Step 3)
# ---------------------------------------------------------------------------

_CEIS_SYSTEM_PROMPT = (
    "You are the CEIS Discipline Engine v5.6. You produce a six-section disciplinary "
    "analysis based on the intake data provided.\n\n"

    "=== OUTPUT FORMAT ===\n"
    "Produce exactly six sections with these headers (use triple equals):\n"
    "  === SECTION 1: INCIDENT NARRATIVE ===\n"
    "  === SECTION 2: POLICY CITATIONS ===\n"
    "  === SECTION 3: VIOLATION ANALYSIS ===\n"
    "  === SECTION 4: DISCIPLINE DETERMINATION ===\n"
    "  === SECTION 5: RISK ASSESSMENT ===\n"
    "  === SECTION 6: FINAL RECOMMENDATION ===\n\n"

    "=== SECTION RULES ===\n\n"

    "SECTION 1 — INCIDENT NARRATIVE:\n"
    "- State facts only. Write in third person, past tense.\n"
    "- Do NOT embed policy language in the narrative body.\n"
    "- At the end of each relevant paragraph, include an inline policy citation in "
    "parentheses using this exact format: (Violation Section X.X — Title)\n"
    "- Multiple citations may appear at the end of a single paragraph.\n\n"

    "SECTION 2 — POLICY CITATIONS:\n"
    "- List each cited policy using this format:\n"
    "    Section X.X — [Title]\n"
    "    \"[Exact policy quote — no paraphrasing]\"\n"
    "- Do NOT paraphrase. Use the exact text from the policy.\n"
    "- Only cite policies that are actually violated based on the facts.\n\n"

    "SECTION 3 — VIOLATION ANALYSIS:\n"
    "- For each violation, explain how the specific facts satisfy each element of the "
    "cited policy.\n"
    "- Reference concrete evidence (dates, times, witness statements, records).\n"
    "- If facts do not fully satisfy a policy element, state that explicitly.\n\n"

    "SECTION 4 — DISCIPLINE DETERMINATION:\n"
    "- Classify the violation into one category:\n"
    "    Type A — Attendance (thresholds per Section 3.5)\n"
    "    Type B — Performance-Conduct (standards per Section 4.1)\n"
    "    Type C — Employment Review (serious/egregious misconduct)\n"
    "- State the progressive discipline level based on prior record.\n"
    "- Reference cumulative prior record when building toward termination.\n\n"

    "SECTION 5 — RISK ASSESSMENT:\n"
    "- Identify legal or procedural risks (due process gaps, inconsistent enforcement, "
    "mitigation factors, union grievance exposure).\n"
    "- Flag any missing documentation that could be challenged.\n\n"

    "SECTION 6 — FINAL RECOMMENDATION:\n"
    "- State the recommended disciplinary action clearly.\n"
    "- Include any conditions (training, PIP, probation period).\n"
    "- Note follow-up requirements.\n\n"

    "=== ENGINE RULES (MANDATORY) ===\n"
    "1. No inferred facts — only use information explicitly provided in the intake.\n"
    "2. No policy language in the narrative body — citations go in parentheses at "
    "paragraph ends only.\n"
    "3. No mixing policy families — Attendance (Type A) and Conduct (Type B) must be "
    "analyzed separately if both apply.\n"
    "4. No Harassment Policy citation unless the factual threshold for harassment is "
    "clearly met.\n"
    "5. Cumulative prior record must be referenced when discipline level approaches "
    "termination.\n\n"

    "=== POLICY HIERARCHY ===\n"
    "When policies conflict, apply this precedence order:\n"
    "  1. Employee Handbook v2.2\n"
    "  2. Use of Force Policy\n"
    "  3. Operations Manual\n"
    "  4. Post Orders\n\n"

    "=== KEY POLICY SECTIONS ===\n"
    "- Section 4.1 — Standards of Conduct\n"
    "- Section 3.5 — Attendance Thresholds\n"
)


def build_ceis_engine_prompt(intake_data: dict, clarifying_answers: list | None = None) -> tuple[str, str]:
    """
    Build prompts for Step 3: full CEIS six-section analysis.
    Returns (system_prompt, user_message).

    clarifying_answers: list of {"question": str, "answer": str} dicts from Step 2,
                        or None / empty if no clarification was needed.
    """
    formatted = _format_intake(intake_data)

    user_parts = [
        "Produce the full six-section CEIS disciplinary analysis for the following intake.\n",
        formatted,
    ]

    if clarifying_answers:
        user_parts.append("\n\n--- Clarifying Q&A ---")
        for i, qa in enumerate(clarifying_answers, 1):
            q = qa.get("question", "")
            a = qa.get("answer", "")
            user_parts.append(f"\nQ{i}: {q}")
            user_parts.append(f"A{i}: {a}")

    return _CEIS_SYSTEM_PROMPT, "\n".join(user_parts)


# ---------------------------------------------------------------------------
# 3. Additional Policy Re-run (Step 4)
# ---------------------------------------------------------------------------

def build_additional_policy_prompt(ceis_output: str, additional_context: dict) -> tuple[str, str]:
    """
    Build prompts for Step 4: incorporate additional policies into an existing analysis.
    Returns (system_prompt, user_message).

    additional_context may contain:
      - use_of_force: str  (Use of Force policy details or incident specifics)
      - post_orders: str   (relevant Post Order text)
      - additional_violations: list[str]  (extra violation descriptions)
      - notes: str         (free-form analyst notes)
    """
    system_prompt = (
        _CEIS_SYSTEM_PROMPT + "\n"
        "=== ADDITIONAL INSTRUCTION ===\n"
        "You are receiving a previous CEIS analysis along with additional policy context. "
        "Incorporate the additional policies and violations into the existing analysis. "
        "Re-produce all six sections with the new information integrated. Do not lose any "
        "content from the original analysis — only add, refine, or re-classify as needed "
        "based on the new information.\n"
    )

    user_parts = [
        "=== PREVIOUS CEIS OUTPUT ===\n",
        ceis_output,
        "\n\n=== ADDITIONAL CONTEXT ===\n",
    ]

    if additional_context.get("use_of_force"):
        user_parts.append(f"\n--- Use of Force ---\n{additional_context['use_of_force']}")

    if additional_context.get("post_orders"):
        user_parts.append(f"\n--- Post Orders ---\n{additional_context['post_orders']}")

    if additional_context.get("additional_violations"):
        user_parts.append("\n--- Additional Violations ---")
        for v in additional_context["additional_violations"]:
            user_parts.append(f"  - {v}")

    if additional_context.get("notes"):
        user_parts.append(f"\n--- Analyst Notes ---\n{additional_context['notes']}")

    return system_prompt, "\n".join(user_parts)


# ---------------------------------------------------------------------------
# 5. Output Parser
# ---------------------------------------------------------------------------

_SECTION_PATTERN = re.compile(
    r"===\s*SECTION\s*(\d)\s*:\s*(.*?)\s*===",
    re.IGNORECASE,
)

_SECTION_KEYS = {
    1: "narrative",
    2: "citations",
    3: "violation_analysis",
    4: "discipline_determination",
    5: "risk_assessment",
    6: "recommendation",
}


def parse_ceis_sections(raw_output: str) -> dict:
    """
    Parse raw CEIS engine output into a dict with keys:
        narrative, citations, violation_analysis,
        discipline_determination, risk_assessment, recommendation

    Splits on === SECTION N: ... === headers.
    Any content before the first header is stored under "preamble" (usually empty).
    Missing sections get an empty string value.
    """
    result = {v: "" for v in _SECTION_KEYS.values()}
    result["preamble"] = ""

    # Find all section header positions
    matches = list(_SECTION_PATTERN.finditer(raw_output))

    if not matches:
        # No headers found — return everything as preamble
        result["preamble"] = raw_output.strip()
        return result

    # Content before first header
    result["preamble"] = raw_output[:matches[0].start()].strip()

    for i, match in enumerate(matches):
        section_num = int(match.group(1))
        # Content runs from end of this header to start of next header (or end of string)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_output)
        content = raw_output[start:end].strip()

        key = _SECTION_KEYS.get(section_num)
        if key:
            result[key] = content

    return result
