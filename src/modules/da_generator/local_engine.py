"""
Cerasus Hub — DA Generator: Local CEIS Engine
Rule-based disciplinary action analysis that works without an API key.
Produces the same 6-section CEIS output format as the AI-powered engine.
Supports customizable templates loaded from the settings table.
"""

import re
from datetime import datetime, timedelta


def _load_custom_templates(violation_type: str) -> dict | None:
    """Try to load custom templates for the given violation type category."""
    try:
        from src.modules.da_generator.pages_templates import get_templates
        if "Type A" in violation_type:
            return get_templates("attendance")
        elif "Type C" in violation_type:
            return get_templates("employment")
        else:
            return get_templates("performance")
    except Exception:
        return None


def _fill_template(template: str, context: dict) -> str:
    """Safely fill a template string with context values."""
    try:
        return template.format(**context)
    except (KeyError, IndexError, ValueError):
        # Fallback: replace what we can, leave the rest
        result = template
        for key, val in context.items():
            result = result.replace("{" + key + "}", str(val))
        return result


# ═══════════════════════════════════════════════════════════════════════
#  Policy Reference Database
# ═══════════════════════════════════════════════════════════════════════

HANDBOOK_SECTIONS = {
    "4.1": {
        "title": "Standards of Conduct",
        "quote": (
            "All employees are expected to conduct themselves in a professional manner "
            "at all times while on duty. Failure to meet these standards may result in "
            "disciplinary action up to and including termination of employment."
        ),
    },
    "3.5": {
        "title": "Attendance and Punctuality",
        "quote": (
            "Regular and reliable attendance is an essential function of every position. "
            "Employees are expected to report to their assigned post on time and remain "
            "on duty for the duration of their scheduled shift. Excessive absenteeism, "
            "tardiness, or failure to report without proper notice will result in "
            "progressive disciplinary action."
        ),
    },
    "3.5.1": {
        "title": "Attendance Point System",
        "quote": (
            "Attendance infractions are tracked using a progressive point system. "
            "Points accumulate over a rolling 365-day window. Discipline thresholds: "
            "2 points — Verbal Warning; 4 points — Written Warning; "
            "6 points — Final Written Warning; 8 points — Employment Review; "
            "10 points — Termination Eligible."
        ),
    },
    "3.6": {
        "title": "Call-Off Procedures",
        "quote": (
            "Employees must notify their supervisor or the operations center at least "
            "four (4) hours prior to the start of their scheduled shift. Failure to "
            "provide adequate notice may result in additional disciplinary points."
        ),
    },
    "3.7": {
        "title": "No Call / No Show",
        "quote": (
            "Failure to report for a scheduled shift without notification constitutes "
            "a No Call / No Show (NCNS). A first NCNS offense carries 6 points and an "
            "automatic Written Warning. A second NCNS offense is grounds for immediate "
            "termination."
        ),
    },
    "4.2": {
        "title": "Workplace Conduct",
        "quote": (
            "Employees shall maintain a professional demeanor and treat all persons "
            "with courtesy and respect. Disruptive, insubordinate, threatening, or "
            "otherwise unprofessional behavior will not be tolerated."
        ),
    },
    "4.3": {
        "title": "Insubordination",
        "quote": (
            "Refusal to follow a lawful and reasonable directive from a supervisor "
            "or management representative constitutes insubordination and may result "
            "in disciplinary action up to and including termination."
        ),
    },
    "4.5": {
        "title": "Post Abandonment",
        "quote": (
            "Leaving an assigned post without proper authorization or relief constitutes "
            "post abandonment. Post abandonment carries 6 disciplinary points and an "
            "automatic Written Warning."
        ),
    },
    "5.1": {
        "title": "Use of Force",
        "quote": (
            "Employees shall use only the minimum force necessary to perform their "
            "duties. The use of excessive or unauthorized force is strictly prohibited "
            "and may result in immediate termination."
        ),
    },
    "6.1": {
        "title": "Uniform and Appearance Standards",
        "quote": (
            "Employees must report to duty in the prescribed uniform and maintain "
            "a professional appearance at all times while on post."
        ),
    },
}

# Map violation types to primary policy sections
TYPE_A_SECTIONS = ["3.5", "3.5.1", "3.6", "3.7"]
TYPE_B_SECTIONS = ["4.1", "4.2", "4.3"]
TYPE_C_SECTIONS = ["4.1"]

DISCIPLINE_PROGRESSION = {
    "Verbal Warning": "This constitutes a Verbal Warning in the progressive discipline process.",
    "Written Warning": "This constitutes a Written Warning in the progressive discipline process.",
    "Final Warning": "This constitutes a Final Written Warning. Any further violations may result in termination of employment.",
    "Termination": "Based on the severity and/or cumulative history, termination of employment is recommended.",
}


# ═══════════════════════════════════════════════════════════════════════
#  Clarifying Questions Generator
# ═══════════════════════════════════════════════════════════════════════

def generate_clarifying_questions(intake: dict) -> list:
    """
    Analyze intake data for factual gaps.
    Returns list of question strings, or empty list if intake is complete.
    """
    questions = []

    narrative = intake.get("incident_narrative", "").strip()
    employee = intake.get("employee_name", "").strip()
    dates = intake.get("incident_dates", "").strip()
    site = intake.get("site", "").strip()
    director = intake.get("security_director", "").strip()
    violation_type = intake.get("violation_type", "")

    # Missing critical fields
    if not employee:
        questions.append("The employee name is missing. Who is the subject of this disciplinary action?")
    if not dates:
        questions.append("No incident date(s) were provided. When did this incident occur?")
    if not site:
        questions.append("The job site is not specified. Where did this incident take place?")
    if not director:
        questions.append("The Security Director name is missing. Who oversees this site?")

    # Narrative analysis
    if not narrative:
        questions.append("No incident narrative was provided. Please describe what happened in factual terms.")
    elif len(narrative) < 50:
        questions.append(
            "The incident narrative is very brief. Can you provide more detail about "
            "what specifically occurred, including the sequence of events?"
        )
    else:
        # Check for common gaps in the narrative
        narrative_lower = narrative.lower()

        if "time" not in narrative_lower and "a.m." not in narrative_lower and "p.m." not in narrative_lower:
            questions.append(
                "The narrative does not mention a specific time. "
                "What time did the incident occur or what was the scheduled shift time?"
            )

        if "witness" not in narrative_lower and not intake.get("has_witness_statements"):
            if "Type B" in violation_type or "Type C" in violation_type:
                questions.append(
                    "Were there any witnesses to this incident? "
                    "If so, have written statements been obtained?"
                )

        if "supervisor" not in narrative_lower and "manager" not in narrative_lower:
            if "Type B" in violation_type:
                questions.append(
                    "Was a supervisor or manager present during or immediately after the incident? "
                    "Who first reported or observed the behavior?"
                )

    # Type-specific questions
    if "Type A" in violation_type:
        if "tardiness" in narrative.lower() and "minute" not in narrative.lower():
            questions.append(
                "For tardiness incidents, how many minutes late was the employee? "
                "What was the scheduled start time versus actual arrival time?"
            )
        if "call" in narrative.lower() and "notice" not in narrative.lower():
            questions.append(
                "How much advance notice did the employee provide for the call-off? "
                "Was it more or less than 4 hours before the shift?"
            )

    if "Type B" in violation_type:
        coaching = intake.get("coaching_occurred", 0)
        if not coaching:
            questions.append(
                "Has a management coaching session been conducted with this employee "
                "regarding this behavior prior to initiating the DA? "
                "If not, is there a reason coaching was skipped?"
            )

        if "insubordination" in narrative.lower():
            questions.append(
                "For the insubordination allegation: What specific directive was given, "
                "by whom, and what was the employee's exact response or refusal?"
            )

    # Prior discipline gaps
    has_any_prior = any([
        intake.get("prior_verbal_same"), intake.get("prior_written_same"),
        intake.get("prior_final_same"), intake.get("prior_verbal_other"),
        intake.get("prior_written_other"), intake.get("prior_final_other"),
    ])
    if has_any_prior:
        if not any(char.isdigit() for char in narrative):
            questions.append(
                "Prior discipline is indicated. Can you provide the approximate dates "
                "of previous disciplinary actions for reference in this DA?"
            )

    return questions


# ═══════════════════════════════════════════════════════════════════════
#  CEIS Engine — 6-Section Output Generator
# ═══════════════════════════════════════════════════════════════════════

def generate_ceis_output(intake: dict, clarifying_answers: list = None) -> dict:
    """
    Generate the full 6-section CEIS disciplinary analysis.
    Returns dict with keys: narrative, citations, violation_analysis,
    discipline_determination, risk_assessment, recommendation.

    First checks for custom templates in the settings table; falls back
    to hardcoded defaults if none are saved.
    """
    violation_type = intake.get("violation_type", "Type B — Performance/Conduct")
    employee = intake.get("employee_name", "Employee")
    position = intake.get("employee_position", "Security Officer")
    site = intake.get("site", "the assigned site")
    dates = intake.get("incident_dates", "the date(s) in question")
    narrative_text = intake.get("incident_narrative", "").strip()
    director = intake.get("security_director", "")

    # Determine applicable policy sections
    if "Type A" in violation_type:
        sections = TYPE_A_SECTIONS
        primary_section = "3.5"
    elif "Type C" in violation_type:
        sections = TYPE_C_SECTIONS
        primary_section = "4.1"
    else:
        sections = TYPE_B_SECTIONS
        primary_section = "4.1"

    # Build prior discipline summary
    prior_summary = _build_prior_summary(intake)

    # Build coaching summary
    coaching_summary = ""
    if intake.get("coaching_occurred"):
        coaching_summary = (
            f"A management coaching session was conducted on "
            f"{intake.get('coaching_date', 'a prior date')}. "
            f"Content: {intake.get('coaching_content', 'N/A')}. "
            f"Outcome: {intake.get('coaching_outcome', 'N/A')}."
        )

    # Determine discipline level
    discipline_level = _determine_discipline_level(intake)

    # Merge clarifying answers into context
    extra_context = ""
    if clarifying_answers:
        for qa in clarifying_answers:
            if isinstance(qa, dict) and qa.get("answer"):
                extra_context += f" {qa['answer']}"

    # ── Try custom templates first ──
    custom = _load_custom_templates(violation_type)
    template_context = {
        "employee": employee,
        "position": position,
        "site": site,
        "dates": dates,
        "narrative": narrative_text + (f"\n\n{extra_context.strip()}" if extra_context else ""),
        "supervisor": director,
        "points": intake.get("attendance_points_at_da", 0),
        "prior_summary": prior_summary,
        "coaching_summary": coaching_summary,
    }

    if custom and _has_custom_content(custom, discipline_level):
        # Use custom template-driven generation
        section1 = _fill_template(
            custom.get("narrative", {}).get(discipline_level, ""), template_context
        )
        section2 = custom.get("citations", "")
        # Violation analysis, risk, recommendation still use hardcoded logic
        # (they are analytical, not template-driven)
        section3 = _build_violation_analysis(
            employee, violation_type, narrative_text, prior_summary, intake
        )
        section4 = _build_discipline_determination_with_templates(
            employee, violation_type, discipline_level, prior_summary, intake, custom
        )
        section5 = _build_risk_assessment(
            employee, discipline_level, prior_summary, intake
        )
        section6 = _build_recommendation(
            employee, discipline_level, violation_type, prior_summary
        )
    else:
        # ── Fallback: hardcoded builders ──
        section1 = _build_narrative(
            employee, position, site, dates, narrative_text,
            violation_type, extra_context, primary_section
        )
        section2 = _build_citations(sections, violation_type, intake)
        section3 = _build_violation_analysis(
            employee, violation_type, narrative_text, prior_summary, intake
        )
        section4 = _build_discipline_determination(
            employee, violation_type, discipline_level, prior_summary, intake
        )
        section5 = _build_risk_assessment(
            employee, discipline_level, prior_summary, intake
        )
        section6 = _build_recommendation(
            employee, discipline_level, violation_type, prior_summary
        )

    return {
        "narrative": section1,
        "citations": section2,
        "violation_analysis": section3,
        "discipline_determination": section4,
        "risk_assessment": section5,
        "recommendation": section6,
    }


def _has_custom_content(custom: dict, level: str) -> bool:
    """Check if the custom templates actually have content (not just empty defaults)."""
    narr = custom.get("narrative", {}).get(level, "")
    return bool(narr and narr.strip())


def generate_additional_policy_output(
    existing_sections: dict, use_of_force: bool, post_orders: bool,
    post_order_details: str, additional_violations: str
) -> dict:
    """Re-generate CEIS output incorporating additional policy context."""
    updated = dict(existing_sections)

    additions_narrative = []
    additions_citations = []
    additions_analysis = []

    if use_of_force:
        uof = HANDBOOK_SECTIONS["5.1"]
        additions_narrative.append(
            "\n\nAdditionally, this incident involves the application of force. "
            "The employee's actions must be evaluated under the Use of Force Policy "
            "to determine whether the force used was reasonable, necessary, and "
            "proportional to the circumstances. (Violation Section 5.1 — Use of Force)"
        )
        additions_citations.append(
            f"\nSection 5.1 — {uof['title']}\n\"{uof['quote']}\""
        )
        additions_analysis.append(
            "\n\nUse of Force Analysis: The incident requires evaluation under the "
            "Use of Force continuum. Any force applied must meet the standard of "
            "minimum necessary force. Deviation from this standard constitutes a "
            "separate and distinct policy violation that may independently warrant "
            "disciplinary action."
        )

    if post_orders and post_order_details:
        additions_narrative.append(
            f"\n\nThe employee was also in violation of site-specific Post Orders. "
            f"Post Order details: {post_order_details.strip()} "
            f"(Violation — Post Orders)"
        )
        additions_citations.append(
            f"\nPost Orders — Site-Specific Directives\n"
            f"\"{post_order_details.strip()}\""
        )
        additions_analysis.append(
            "\n\nPost Order Violation Analysis: Site-specific Post Orders carry "
            "the same weight as company policy and are considered binding directives. "
            "Violation of Post Orders demonstrates a failure to follow established "
            "operational procedures specific to the assigned location."
        )

    if additional_violations:
        additions_narrative.append(
            f"\n\nAdditional violations identified: {additional_violations.strip()} "
            f"(Violation Section 4.1 — Standards of Conduct)"
        )
        additions_analysis.append(
            f"\n\nAdditional Violation Analysis: {additional_violations.strip()}. "
            f"These additional violations compound the severity of the primary incident "
            f"and are factored into the overall discipline determination."
        )

    if additions_narrative:
        updated["narrative"] += "".join(additions_narrative)
    if additions_citations:
        updated["citations"] += "".join(additions_citations)
    if additions_analysis:
        updated["violation_analysis"] += "".join(additions_analysis)

    # Update risk assessment if Use of Force is involved
    if use_of_force:
        updated["risk_assessment"] += (
            "\n\nElevated Risk Factor: Use of Force involvement increases the overall "
            "risk profile of this action. The company faces potential liability exposure "
            "if the force used is later determined to have been excessive or unauthorized. "
            "Thorough documentation and witness statements are critical."
        )

    return updated


# ═══════════════════════════════════════════════════════════════════════
#  Internal Builders
# ═══════════════════════════════════════════════════════════════════════

def _build_prior_summary(intake: dict) -> str:
    """Build a human-readable prior discipline summary."""
    lines = []

    if intake.get("prior_verbal_same"):
        lines.append("Verbal Warning (same issue)")
    if intake.get("prior_written_same"):
        lines.append("Written Warning (same issue)")
    if intake.get("prior_final_same"):
        lines.append("Final Warning (same issue)")
    if intake.get("prior_verbal_other"):
        lines.append("Verbal Warning (other issue)")
    if intake.get("prior_written_other"):
        lines.append("Written Warning (other issue)")
    if intake.get("prior_final_other"):
        lines.append("Final Warning (other issue)")

    if not lines:
        return "No prior disciplinary record on file."
    return "Prior discipline on record: " + "; ".join(lines) + "."


def _determine_discipline_level(intake: dict) -> str:
    """Determine appropriate discipline level based on intake data."""
    violation_type = intake.get("violation_type", "")

    # Check attendance points for Type A
    if "Type A" in violation_type:
        points = intake.get("attendance_points_at_da", 0)
        if isinstance(points, str):
            try:
                points = float(points)
            except ValueError:
                points = 0

        if points >= 10:
            return "Termination"
        elif points >= 8:
            return "Final Warning"
        elif points >= 6:
            return "Written Warning"
        elif points >= 2:
            return "Verbal Warning"

    # Progressive discipline for Type B/C
    if intake.get("prior_final_same"):
        return "Termination"
    elif intake.get("prior_written_same"):
        return "Final Warning"
    elif intake.get("prior_verbal_same"):
        return "Written Warning"
    else:
        return "Verbal Warning"


def _build_narrative(employee, position, site, dates, narrative_text,
                     violation_type, extra_context, primary_section):
    """Build Section 1: Incident Narrative — CEIS v5.6 professional format."""
    section_info = HANDBOOK_SECTIONS.get(primary_section, {})
    section_title = section_info.get("title", "Standards of Conduct")

    # Combine raw narrative with any clarifying answers
    full_narrative = narrative_text or ""
    if extra_context:
        full_narrative = (full_narrative + " " + extra_context.strip()).strip()

    parts = []

    # ── Opening paragraph: formal identification and context ──
    if "Type A" in violation_type:
        parts.append(
            f"This disciplinary action is being issued to {employee}, currently "
            f"employed as a {position} assigned to {site}. On {dates}, the "
            f"employee incurred an attendance infraction that, in conjunction with "
            f"the employee's cumulative attendance record, has triggered the next "
            f"level of progressive discipline under the Company's Attendance and "
            f"Punctuality Policy."
        )
    elif "Type C" in violation_type:
        parts.append(
            f"This Employment Review is being initiated for {employee}, currently "
            f"employed as a {position} assigned to {site}. This review is based "
            f"on the totality of the employee's disciplinary record and the nature "
            f"of the incident(s) occurring on or about {dates}, which collectively "
            f"warrant a formal evaluation of continued employment."
        )
    else:
        parts.append(
            f"This disciplinary action is being issued to {employee}, currently "
            f"employed as a {position} assigned to {site}. On {dates}, the "
            f"employee engaged in conduct that falls below the professional "
            f"standards required of all Cerasus Security personnel."
        )

    # ── Incident details paragraph: restate narrative in formal third-person ──
    if full_narrative:
        # Reformat the user's narrative into a professional third-person account
        formatted_narrative = _professionalize_narrative(full_narrative, employee)
        parts.append(f"\n\n{formatted_narrative}")

    # ── Expectations paragraph ──
    if "Type A" in violation_type:
        parts.append(
            f"\n\nAll Cerasus Security employees are expected to maintain regular "
            f"and reliable attendance as an essential function of their position. "
            f"{employee} was made aware of the Company's attendance expectations "
            f"and the progressive point system at the time of hire and at each "
            f"prior step of the disciplinary process. Despite prior counseling "
            f"and/or disciplinary action, the attendance pattern has continued. "
            f"(Violation Section 3.5 — Attendance and Punctuality)"
        )
    elif "Type C" in violation_type:
        parts.append(
            f"\n\nThe above conduct, when viewed in the context of the employee's "
            f"overall disciplinary history, raises serious concerns regarding "
            f"{employee}'s ability to meet the minimum standards of employment "
            f"with Cerasus Security. The cumulative record reflects a pattern "
            f"that has not been corrected through prior progressive discipline "
            f"interventions. (Violation Section {primary_section} — {section_title})"
        )
    else:
        parts.append(
            f"\n\nThe conduct described above is inconsistent with the professional "
            f"standards and expectations that Cerasus Security requires of all "
            f"employees. {employee} is expected to conduct themselves in a manner "
            f"that reflects positively on the Company and to comply with all "
            f"policies, procedures, and directives at all times while on duty. "
            f"(Violation Section {primary_section} — {section_title})"
        )

    # ── Additional policy citations based on narrative keywords ──
    extra_citations = _detect_additional_citations(full_narrative, violation_type)
    for citation in extra_citations:
        parts.append(f" {citation}")

    return "".join(parts)


def _professionalize_narrative(raw_narrative: str, employee: str) -> str:
    """
    Reformat raw user narrative into formal third-person account.
    Ensures professional tone without altering factual content.

    Applies comprehensive rule-based transformations:
      1.  Capitalization fixes (sentences, proper nouns)
      2.  Run-on sentence splitting
      3.  Fragment merging
      4.  Double/multiple space collapse
      5.  Missing period insertion
      6.  Professional tone (1st→3rd person, contractions, slang, fillers)
      7.  Subject-verb agreement for "the employee"
      8.  Past-tense consistency
      9.  Punctuation cleanup (Oxford comma, introductory commas)
      10. Redundancy removal
    """
    text = raw_narrative.strip()
    if not text:
        return ""

    # Very short text — just capitalize and punctuate
    if len(text) < 3:
        text = text[0].upper() + text[1:]
        if text[-1] not in ".!?":
            text += "."
        return text

    # ── Helper: word-boundary replacement (case-sensitive) ────────────
    def _wb_replace(pattern_str: str, replacement: str, source: str) -> str:
        """Replace with word boundaries, preserving non-matched text."""
        return re.sub(r"\b" + pattern_str + r"\b", replacement, source)

    def _wb_replace_ic(pattern_str: str, replacement: str, source: str) -> str:
        """Case-insensitive word-boundary replacement."""
        return re.sub(r"\b" + pattern_str + r"\b", replacement, source, flags=re.IGNORECASE)

    # ══════════════════════════════════════════════════════════════════
    # STEP 4 — Collapse multiple spaces (do early so later regexes work)
    # ══════════════════════════════════════════════════════════════════
    text = re.sub(r"[ \t]+", " ", text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 6a — Expand ALL contractions (before other transforms)
    # ══════════════════════════════════════════════════════════════════
    contraction_map = [
        # Order matters — longer patterns first to avoid partial matches
        (r"shouldn't've", "should not have"),
        (r"couldn't've", "could not have"),
        (r"wouldn't've", "would not have"),
        (r"shouldn't", "should not"),
        (r"couldn't", "could not"),
        (r"wouldn't", "would not"),
        (r"doesn't", "does not"),
        (r"haven't", "have not"),
        (r"hadn't", "had not"),
        (r"wasn't", "was not"),
        (r"weren't", "were not"),
        (r"isn't", "is not"),
        (r"aren't", "are not"),
        (r"didn't", "did not"),
        (r"won't", "will not"),
        (r"can't", "cannot"),
        (r"ain't", "is not"),
        (r"don't", "do not"),
        (r"that's", "that is"),
        (r"there's", "there is"),
        (r"here's", "here is"),
        (r"what's", "what is"),
        (r"who's", "who is"),
        (r"it's", "it is"),
        (r"he's been", "he has been"),
        (r"she's been", "she has been"),
        (r"he's", "he is"),
        (r"she's", "she is"),
        (r"let's", "let us"),
        (r"they're", "they are"),
        (r"we're", "we are"),
        (r"you're", "you are"),
        (r"they've", "they have"),
        (r"we've", "we have"),
        (r"you've", "you have"),
        (r"I've", "I have"),
        (r"they'd", "they would"),
        (r"we'd", "we would"),
        (r"you'd", "you would"),
        (r"I'd", "I would"),
        (r"he'd", "he would"),
        (r"she'd", "she would"),
        (r"they'll", "they will"),
        (r"we'll", "we will"),
        (r"you'll", "you will"),
        (r"I'll", "I will"),
        (r"he'll", "he will"),
        (r"she'll", "she will"),
        (r"it'll", "it will"),
        (r"I'm", "I am"),
    ]
    for contraction, expansion in contraction_map:
        # Case-insensitive replacement that preserves leading capitalisation
        pattern = re.compile(re.escape(contraction), re.IGNORECASE)
        def _expand(m, exp=expansion):
            matched = m.group(0)
            if matched[0].isupper():
                return exp[0].upper() + exp[1:]
            return exp
        text = pattern.sub(_expand, text)

    # Also catch contractions typed WITHOUT apostrophes (didnt, wasnt, etc.)
    no_apos_map = [
        (r"\bshouldnt\b", "should not"), (r"\bcouldnt\b", "could not"),
        (r"\bwouldnt\b", "would not"), (r"\bdoesnt\b", "does not"),
        (r"\bhavent\b", "have not"), (r"\bhadnt\b", "had not"),
        (r"\bwasnt\b", "was not"), (r"\bwerent\b", "were not"),
        (r"\bisnt\b", "is not"), (r"\barent\b", "are not"),
        (r"\bdidnt\b", "did not"), (r"\bwont\b", "will not"),
        (r"\bcant\b", "cannot"), (r"\baint\b", "is not"),
        (r"\bdont\b", "do not"), (r"\bthats\b", "that is"),
        (r"\btheres\b", "there is"), (r"\bwhats\b", "what is"),
        (r"\bits\b(?=\s+(?:not|a |the |been |going |clear |important |evident ))", "it is"),
        (r"\btheyre\b", "they are"), (r"\bwere\b(?=\s+(?:not|going|told))", "we are"),
        (r"\byoure\b", "you are"), (r"\btheyve\b", "they have"),
        (r"\bweve\b", "we have"), (r"\byouve\b", "you have"),
        (r"\bIve\b", "I have"), (r"\bIm\b", "I am"),
        (r"\bIll\b", "I will"), (r"\bhes been\b", "he has been"),
        (r"\bshes been\b", "she has been"),
        (r"\bhes\b", "he is"), (r"\bshes\b", "she is"),
    ]
    for pattern, expansion in no_apos_map:
        text = re.sub(pattern, expansion, text, flags=re.IGNORECASE)

    # ══════════════════════════════════════════════════════════════════
    # STEP 6b — First person → third person (must precede tense fixes)
    # ══════════════════════════════════════════════════════════════════
    first_to_third = [
        # Phrases (longest first)
        (r"I was informed", "The supervisor was informed"),
        (r"I was told", "The supervisor was informed"),
        (r"I was notified", "The supervisor was notified"),
        (r"I informed", "The supervisor informed"),
        (r"I instructed", "The supervisor instructed"),
        (r"I directed", "The supervisor directed"),
        (r"I advised", "The supervisor advised"),
        (r"I counseled", "The supervisor counseled"),
        (r"I observed", "It was observed"),
        (r"I noticed", "It was observed"),
        (r"I witnessed", "It was observed"),
        (r"I discovered", "It was discovered"),
        (r"I found", "It was discovered"),
        (r"I saw", "It was observed"),
        (r"I told (?:him|her|them|the (?:officer|employee)) (?:that|this|it)", "The supervisor informed the employee that"),
        (r"I told", "The supervisor directed"),
        (r"I asked", "The supervisor asked"),
        (r"I requested", "The supervisor requested"),
        (r"I spoke with", "The supervisor spoke with"),
        (r"I spoke to", "The supervisor spoke to"),
        (r"I talked to", "The supervisor spoke to"),
        (r"I met with", "The supervisor met with"),
        (r"I contacted", "The supervisor contacted"),
        (r"I called", "The supervisor contacted"),
        (r"I reviewed", "A review was conducted of"),
        (r"I checked", "A review was conducted of"),
        (r"I verified", "It was verified"),
        (r"I confirmed", "It was confirmed"),
        (r"I documented", "It was documented"),
        (r"I noted", "It was noted"),
        (r"I reported", "It was reported"),
        (r"I received", "The supervisor received"),
        (r"I issued", "The supervisor issued"),
        (r"I wrote (?:him|her|them|the (?:officer|employee)) up", "The supervisor issued a corrective action to the employee"),
        (r"I wrote", "The supervisor prepared"),
        (r"I have", "The supervisor has"),
        (r"I had", "The supervisor had"),
        (r"I am", "The supervisor is"),
        (r"I was", "The supervisor was"),
        (r"I will", "The supervisor will"),
        (r"I would", "The supervisor would"),
    ]
    for pattern, replacement in first_to_third:
        def _first_person_replace(m, r=replacement):
            # Determine if this is at the start of a sentence
            start = m.start()
            at_sentence_start = (start == 0)
            if not at_sentence_start:
                # Look backwards for sentence-ending punctuation
                before = m.string[:start].rstrip()
                if before and before[-1] in ".!?":
                    at_sentence_start = True
            if at_sentence_start:
                return r[0].upper() + r[1:]
            return r[0].lower() + r[1:]
        text = re.sub(r"(?i)\b" + pattern + r"\b", _first_person_replace, text)

    # Remaining standalone first-person pronouns
    text = _wb_replace(r"my shift", "the shift", text)
    text = _wb_replace(r"My shift", "The shift", text)
    text = _wb_replace(r"my post", "the post", text)
    text = _wb_replace(r"My post", "The post", text)
    text = _wb_replace(r"my report", "the report", text)
    text = _wb_replace(r"My report", "The report", text)
    text = _wb_replace(r"my area", "the area", text)
    text = _wb_replace(r"My area", "The area", text)
    text = _wb_replace(r"my team", "the team", text)
    text = _wb_replace(r"My team", "The team", text)
    text = _wb_replace(r"my office", "the office", text)
    text = _wb_replace(r"My office", "The office", text)
    text = _wb_replace(r"my department", "the department", text)
    text = _wb_replace(r"My department", "The department", text)
    text = _wb_replace(r"my supervisor", "the supervisor", text)
    text = _wb_replace(r"My supervisor", "The supervisor", text)

    # Generic fallback for remaining "my" → "the" (only before common nouns)
    text = re.sub(r"\bmy\b", "the", text)
    text = re.sub(r"\bMy\b", "The", text)

    # Catch remaining standalone "I" as subject
    text = re.sub(r"\bI\b(?!\.\w)", "the supervisor", text)

    # Object-form first person: "me" → "the supervisor"
    # Only when preceded by a preposition or verb commonly directed at a person
    me_predecessors = [
        "at", "to", "with", "from", "told", "asked", "gave", "showed",
        "called", "emailed", "texted", "informed", "notified", "yelling",
        "screaming", "directed", "toward", "against",
    ]
    for pred in me_predecessors:
        text = re.sub(r"(?<=" + pred + r" )\bme\b", "the supervisor", text)
    text = re.sub(r"\bmy\s*self\b", "the supervisor", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmyself\b", "the supervisor", text, flags=re.IGNORECASE)

    # Insert "that" after "It was observed/discovered/noted" when followed directly by a noun
    text = re.sub(r"([Ii]t was (?:observed|discovered|noted|verified|confirmed))\s+(?!that\b)(\w)",
                  r"\1 that \2", text)

    # Employee name substitutions
    text = text.replace("the officer ", f"{employee} ")
    text = text.replace("The officer ", f"{employee} ")

    # Gendered pronouns → neutral
    text = re.sub(r"\b[Hh]e was\b", "the employee was", text)
    text = re.sub(r"\b[Ss]he was\b", "the employee was", text)
    text = re.sub(r"\b[Hh]e is\b", "the employee is", text)
    text = re.sub(r"\b[Ss]he is\b", "the employee is", text)
    text = re.sub(r"\b[Hh]e had\b", "the employee had", text)
    text = re.sub(r"\b[Ss]he had\b", "the employee had", text)
    text = re.sub(r"\b[Hh]e has\b", "the employee has", text)
    text = re.sub(r"\b[Ss]he has\b", "the employee has", text)
    text = re.sub(r"\b[Hh]e did\b", "the employee did", text)
    text = re.sub(r"\b[Ss]he did\b", "the employee did", text)
    _work_nouns = (r"shift|post|area|badge|uniform|phone|vehicle|report|duty|assignment|"
                   r"schedule|behavior|conduct|attendance|action|response|failure|absence|"
                   r"position|site|location|radio|equipment|keys|supervisor|manager|job|"
                   r"break|lunch|patrol|route|training|performance|actions|responsibilities")
    text = re.sub(r"\b[Hh]is\b(?=\s+(?:" + _work_nouns + r"))", "the employee's", text)
    text = re.sub(r"\b[Hh]er\b(?=\s+(?:" + _work_nouns + r"))", "the employee's", text)
    text = re.sub(r"\b[Hh]im\b(?=\s+(?:up|down|to|that|if|about|from|for|on|at|in))", "the employee", text)
    text = re.sub(r"\b[Hh]imself\b", "the employee", text)
    text = re.sub(r"\b[Hh]erself\b", "the employee", text)

    # Broader standalone "He"/"She" as sentence subject → "The employee"
    # (catches cases not covered by the specific he+verb patterns above)
    text = re.sub(r"\bHe\b(?! employee)", "The employee", text)
    text = re.sub(r"\bShe\b(?! employee)", "The employee", text)
    text = re.sub(r"\bhe\b(?! employee)", "the employee", text)
    text = re.sub(r"\bshe\b(?! employee)", "the employee", text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 6c — Informal language → formal equivalents
    # ══════════════════════════════════════════════════════════════════
    informal_to_formal = [
        # Slang / casual phrasing (longest first)
        (r"no[- ]showed", "failed to report"),
        (r"no[- ]show(?:ed|s)?", "failure to report"),
        (r"showed up late", "arrived late"),
        (r"showed up", "arrived"),
        (r"show(?:s)? up", "arrive"),
        (r"messed up", "failed to comply"),
        (r"screwed up", "failed to comply"),
        (r"kicked (?:him |her |them |the employee )?out", "removed the employee from the site"),
        (r"thrown (?:him |her |them |the employee )?out", "removed the employee from the site"),
        (r"kick (?:him |her |them |the employee )?out", "remove the employee from the site"),
        (r"walked off", "abandoned the post"),
        (r"walked out", "departed the site without authorization"),
        (r"blew off", "disregarded"),
        (r"called out", "reported an absence"),
        (r"called off", "reported an absence"),
        (r"went off on", "directed hostile language toward"),
        (r"cussed out", "directed profanity toward"),
        (r"cussed at", "directed profanity toward"),
        (r"cursed out", "directed profanity toward"),
        (r"cursed at", "directed profanity toward"),
        (r"yelled at", "raised their voice toward"),
        (r"screamed at", "raised their voice toward"),
        (r"freaked out", "became agitated"),
        (r"flipped out", "became agitated"),
        (r"acted up", "behaved in a disruptive manner"),
        (r"goofing off", "engaging in non-work-related activity"),
        (r"goofed off", "engaged in non-work-related activity"),
        (r"hanging out", "loitering"),
        (r"hung out", "loitered"),
        (r"a bunch of", "multiple"),
        (r"a lot of", "numerous"),
        (r"lots of", "numerous"),
        (r"a couple of", "two"),
        (r"a couple", "two"),
        (r"guys", "individuals"),
        (r"guy", "individual"),
        (r"dudes?", "individual"),
        (r"coworkers?", "colleagues"),
        (r"co-workers?", "colleagues"),
        (r"boss", "supervisor"),
        (r"got (?:an? )?attitude", "displayed a negative attitude"),
        (r"gave (?:an? )?attitude", "displayed a negative attitude"),
        (r"gotten", "received"),
        (r"got(?= (?:a|an|the|into|in|to|from|out))", "received"),
        (r"got (?:real |very |super )?mad", "became visibly upset"),
        (r"got (?:real |very |super )?angry", "became visibly agitated"),
        (r"(?:real |very |super )mad", "visibly upset"),
        (r"(?:real |very |super )angry", "visibly agitated"),
        (r"\bmad\b", "upset"),
        (r"pissed off", "visibly agitated"),
        (r"ticked off", "visibly upset"),
        (r"(?:really |very |super )drunk", "appeared to be intoxicated"),
        (r"drunk", "appeared to be intoxicated"),
        (r"(?:really |very |super )high", "appeared to be under the influence"),
        (r"passed out", "found unresponsive"),
        (r"asleep on the job", "found sleeping while on duty"),
        (r"sleeping on the job", "found sleeping while on duty"),
        (r"fell asleep", "was found sleeping while on duty"),
        (r"on (?:his|her|their) phone", "using a personal mobile device"),
        (r"on the phone", "using a personal mobile device"),
        (r"OK(?:ay)?", "acceptable"),
        (r"(?:nope|nah)", "no"),
        (r"(?:yep|yeah|yea)", "yes"),
        (r"kind of", "somewhat"),
        (r"sort of", "somewhat"),
        (r"pretty much", "largely"),
        (r"right away", "immediately"),
        (r"ASAP", "immediately"),
        (r"asap", "immediately"),
        (r"a no go", "not permitted"),
        (r"(?:big|huge) deal", "significant matter"),
        (r"heads up", "advance notice"),
        (r"wrote (?:him|her|them|the employee) up", "issued a corrective action to the employee"),
        (r"write (?:him|her|them|the employee) up", "issue a corrective action to the employee"),
        (r"write[- ]?up", "written corrective action"),
        (r"had (?:an? )?attitude", "displayed a negative attitude"),
        (r"copped (?:an? )?attitude", "displayed a negative attitude"),
        (r"resting (?:his|her|their) eyes", "sleeping while on duty"),
        (r"on (?:his|her|their) (?:break|lunch) (?:too long|for too long)", "exceeded the authorized break period"),
        (r"fire(?:d)?(?= him| her| them| the employee)", "terminate"),
        (r"let go", "separated from employment"),
    ]
    for pattern, replacement in informal_to_formal:
        text = re.sub(r"(?i)\b" + pattern + r"\b", replacement, text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 6d — Filler word removal
    # ══════════════════════════════════════════════════════════════════
    # Only remove fillers when they appear as throwaway qualifiers,
    # not when they are integral to meaning (e.g. "just cause").
    filler_patterns = [
        r"\bbasically[,]?\s+",
        r"\blike[,]?\s+(?=the |a |an |this |that |it |they |we |he |she |\d)",
        r"\bjust\s+(?=then |said |told |went |left |did |was |had |got |came |walked |called )",
        r"\breally\s+",
        r"\bactually[,]?\s+",
        r"\bliterally\s+",
        r"\bhonestly[,]?\s+",
        r"\bobviously[,]?\s+",
        r"\bclearly\s+(?=the |a |this |that |it )",
        r"\banyways?\s+",
        r"\bso\s+(?=basically |like |anyway |then |yeah )",
    ]
    for fp in filler_patterns:
        text = re.sub(fp, "", text, flags=re.IGNORECASE)

    # ══════════════════════════════════════════════════════════════════
    # STEP 10 — Remove common redundancies
    # ══════════════════════════════════════════════════════════════════
    redundancy_map = [
        (r"past history", "history"),
        (r"advance planning", "planning"),
        (r"advance warning", "warning"),
        (r"added bonus", "bonus"),
        (r"basic fundamentals", "fundamentals"),
        (r"close proximity", "proximity"),
        (r"completely destroyed", "destroyed"),
        (r"completely eliminated", "eliminated"),
        (r"completely finished", "finished"),
        (r"completely unanimous", "unanimous"),
        (r"each and every", "each"),
        (r"end result", "result"),
        (r"exactly the same", "the same"),
        (r"false pretense", "pretense"),
        (r"final outcome", "outcome"),
        (r"first and foremost", "first"),
        (r"free gift", "gift"),
        (r"future plans", "plans"),
        (r"general consensus", "consensus"),
        (r"new innovation", "innovation"),
        (r"over exaggerate", "exaggerate"),
        (r"over exaggerated", "exaggerated"),
        (r"over exaggeration", "exaggeration"),
        (r"past experience", "experience"),
        (r"period of time", "period"),
        (r"personal opinion", "opinion"),
        (r"plan ahead", "plan"),
        (r"prior experience", "experience"),
        (r"reason is because", "reason is that"),
        (r"repeat(?:ed)? again", "repeated"),
        (r"revert back", "revert"),
        (r"still remains", "remains"),
        (r"sudden(?:ly)? unexpected", "unexpected"),
        (r"surrounded on all sides", "surrounded"),
        (r"unexpected surprise", "surprise"),
        (r"usual custom", "custom"),
        (r"very unique", "unique"),
        (r"whether or not", "whether"),
    ]
    for pattern, replacement in redundancy_map:
        text = re.sub(r"(?i)\b" + pattern + r"\b", replacement, text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 8 — Tense consistency (present → past)
    # Convert present-tense verbs commonly found in supervisor narratives
    # ══════════════════════════════════════════════════════════════════
    # Only convert when preceded by a subject-like word to avoid false positives
    tense_map = [
        (r"(?<=the employee )\bis\b", "was"),
        (r"(?<=the employee )\bhas\b", "had"),
        (r"(?<=the employee )\bsays\b", "said"),
        (r"(?<=the employee )\btells\b", "told"),
        (r"(?<=the employee )\bcomes\b", "came"),
        (r"(?<=the employee )\bgoes\b", "went"),
        (r"(?<=the employee )\bdoes\b", "did"),
        (r"(?<=the employee )\bmakes\b", "made"),
        (r"(?<=the employee )\btakes\b", "took"),
        (r"(?<=the employee )\bgives\b", "gave"),
        (r"(?<=the employee )\bleaves\b", "left"),
        (r"(?<=the employee )\bgets\b", "got"),
        (r"(?<=the employee )\barrives\b", "arrived"),
        (r"(?<=the employee )\brefuses\b", "refused"),
        (r"(?<=the employee )\bstates\b", "stated"),
        (r"(?<=the employee )\bclaims\b", "claimed"),
        (r"(?<=the employee )\bresponds\b", "responded"),
        (r"(?<=the employee )\breturns\b", "returned"),
        (r"(?<=the employee )\bappears\b", "appeared"),
        (r"(?<=the employee )\bfails\b", "failed"),
    ]
    for pattern, replacement in tense_map:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Broader present→past for common narrative verbs after subject phrases
    broader_subjects = r"(?:the employee|the supervisor|the individual|the officer|" + re.escape(employee) + r")"
    broader_tense = [
        ("is", "was"), ("are", "were"), ("has", "had"),
        ("says", "said"), ("tells", "told"), ("comes", "came"),
        ("goes", "went"), ("does", "did"), ("makes", "made"),
        ("takes", "took"), ("gives", "gave"), ("leaves", "left"),
        ("gets", "got"),
    ]
    for present, past in broader_tense:
        text = re.sub(
            r"(" + broader_subjects + r"\s+)" + r"\b" + present + r"\b",
            lambda m, p=past: m.group(1) + p,
            text, flags=re.IGNORECASE
        )

    # ══════════════════════════════════════════════════════════════════
    # STEP 7 — Subject-verb agreement: "the employee" + singular verb
    # ══════════════════════════════════════════════════════════════════
    sv_fixes = [
        (r"the employee were\b", "the employee was"),
        (r"the employee have\b", "the employee has"),
        (r"the employee are\b", "the employee is"),
        (r"the employee don't\b", "the employee does not"),
        (r"the employee do not\b(?! have)", "the employee does not"),
    ]
    for pattern, replacement in sv_fixes:
        text = re.sub(r"(?i)" + pattern, replacement, text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 9 — Punctuation cleanup
    # ══════════════════════════════════════════════════════════════════

    # 9a — Add commas after introductory phrases
    intro_patterns = [
        r"(On \d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(On (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}(?:,? \d{4})?)",
        r"(At \d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?)",
        r"(At approximately \d{1,2}:\d{2}\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)?)",
        r"(During (?:the |this |that )\w+)",
        r"(Upon (?:arrival|review|inspection|investigation|further review))",
        r"(After (?:the |this |that |an? )\w+)",
        r"(Before (?:the |this |that |an? )\w+)",
        r"(However)",
        r"(Additionally)",
        r"(Furthermore)",
        r"(Moreover)",
        r"(Subsequently)",
        r"(Consequently)",
        r"(Nevertheless)",
        r"(In addition)",
        r"(As a result)",
        r"(At that time)",
        r"(At this time)",
        r"(In response)",
        r"(Per (?:company |site )?policy)",
        r"(According to [\w\s]+?)",
    ]
    for ip in intro_patterns:
        # Add comma after introductory phrase if not already followed by one
        text = re.sub(ip + r"(?!\s*,)\s+", r"\1, ", text)

    # 9b — Oxford comma in lists: "A, B and C" → "A, B, and C"
    text = re.sub(r"(\w+),\s+(\w+)\s+and\s+(\w+)", r"\1, \2, and \3", text)

    # 9c — Fix comma splices before conjunctions that join independent clauses
    # (Light touch: only add comma before "but" and "however" mid-sentence)
    text = re.sub(r"(\w)\s+but\s+(?=[A-Z])", r"\1, but ", text)
    text = re.sub(r"(\w)\s+however\s+(?=[A-Z])", r"\1; however, ", text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 2 — Fix run-on sentences (50+ words without terminal punctuation)
    # Split at conjunctions when a sentence is excessively long.
    # ══════════════════════════════════════════════════════════════════
    def _split_run_ons(input_text: str) -> str:
        # Work sentence-by-sentence
        sentences = re.split(r"(?<=[.!?])\s+", input_text)
        result = []
        for sentence in sentences:
            words = sentence.split()
            if len(words) >= 30:
                # Try to split at conjunctions near the middle
                split_conjunctions = ["and", "but", "however", "because", "which", "although", "whereas", "while"]
                mid = len(words) // 2
                best_idx = None
                best_dist = len(words)
                for i, w in enumerate(words):
                    clean = w.strip(",;").lower()
                    if clean in split_conjunctions and i > 8 and i < len(words) - 8:
                        dist = abs(i - mid)
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = i
                if best_idx is not None:
                    first_half = " ".join(words[:best_idx]).rstrip(",;")
                    if first_half and first_half[-1] not in ".!?":
                        first_half += "."
                    second_word = words[best_idx]
                    clean_conj = second_word.strip(",;").lower()
                    # Drop the bare conjunction at the split point if it is just a joining word
                    if clean_conj in ("and", "but"):
                        second_half = " ".join(words[best_idx + 1:])
                    else:
                        second_half = " ".join(words[best_idx:])
                    if second_half:
                        second_half = second_half[0].upper() + second_half[1:]
                    result.append(first_half + " " + second_half)
                else:
                    result.append(sentence)
            else:
                result.append(sentence)
        return " ".join(result)

    text = _split_run_ons(text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 3 — Merge sentence fragments (very short, <5 words, no verb)
    # ══════════════════════════════════════════════════════════════════
    def _merge_fragments(input_text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", input_text)
        if len(sentences) <= 1:
            return input_text
        merged = []
        skip_next = False
        common_verbs = {
            "was", "were", "is", "are", "had", "has", "have", "did", "does",
            "said", "told", "went", "came", "made", "took", "gave", "left",
            "got", "arrived", "refused", "stated", "claimed", "responded",
            "returned", "appeared", "failed", "observed", "reported", "directed",
            "instructed", "informed", "requested", "contacted", "issued",
            "prepared", "conducted", "verified", "confirmed", "documented",
        }
        for i, sent in enumerate(sentences):
            if skip_next:
                skip_next = False
                continue
            words = sent.strip().rstrip(".!?").split()
            has_verb = any(w.lower() in common_verbs for w in words)
            if len(words) < 5 and not has_verb:
                # This looks like a fragment — merge with next sentence
                if i + 1 < len(sentences):
                    next_sent = sentences[i + 1]
                    # Remove trailing punct from fragment before merging
                    frag = sent.rstrip(".!? ")
                    combined = frag + "; " + next_sent[0].lower() + next_sent[1:]
                    merged.append(combined)
                    skip_next = True
                else:
                    # Last sentence fragment — merge with previous
                    if merged:
                        prev = merged[-1].rstrip(".!? ")
                        frag = sent.strip().rstrip(".!? ")
                        merged[-1] = prev + "; " + frag[0].lower() + frag[1:] + "."
                    else:
                        merged.append(sent)
            else:
                merged.append(sent)
        return " ".join(merged)

    text = _merge_fragments(text)

    # ══════════════════════════════════════════════════════════════════
    # STEP 1 — Fix capitalization
    # ══════════════════════════════════════════════════════════════════

    # 1a — Capitalize first letter of each sentence
    def _capitalize_sentences(input_text: str) -> str:
        # After sentence-ending punctuation followed by space
        result = re.sub(
            r"([.!?])\s+([a-z])",
            lambda m: m.group(1) + " " + m.group(2).upper(),
            input_text
        )
        # Capitalize the very first character
        if result and result[0].islower():
            result = result[0].upper() + result[1:]
        return result

    text = _capitalize_sentences(text)

    # 1b — Capitalize proper nouns: days, months, "Cerasus"
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    months = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    for word in days + months:
        text = re.sub(r"\b" + word + r"\b", word.capitalize(), text, flags=re.IGNORECASE)

    # "Cerasus" should always be capitalized
    text = re.sub(r"\bcerasus\b", "Cerasus", text, flags=re.IGNORECASE)

    # ══════════════════════════════════════════════════════════════════
    # STEP 5 — Final punctuation
    # ══════════════════════════════════════════════════════════════════
    # Ensure text ends with a period
    text = text.strip()
    if text and text[-1] not in ".!?":
        text += "."

    # ══════════════════════════════════════════════════════════════════
    # Final cleanup pass
    # ══════════════════════════════════════════════════════════════════
    # Remove duplicate phrases caused by pronoun → noun replacement chains
    text = re.sub(r"\bthe employee the employee\b", "the employee", text, flags=re.IGNORECASE)
    text = re.sub(r"\bthe supervisor the supervisor\b", "the supervisor", text, flags=re.IGNORECASE)

    # ── Name alternation: reduce "the employee" repetition ──
    # Replace every other occurrence of "the employee" with the actual employee name
    # to make the narrative read more naturally.
    _emp_lower = "the employee"
    _emp_pattern = re.compile(r"\bthe employee\b", re.IGNORECASE)
    _matches = list(_emp_pattern.finditer(text))
    if len(_matches) > 2 and employee:
        # Replace odd-numbered occurrences (2nd, 4th, 6th...) with employee name
        # Keep 1st, 3rd, 5th as "the employee" for variety
        offset_shift = 0
        for idx_m, match in enumerate(_matches):
            if idx_m % 2 == 1:  # Every other one (0-indexed, so 1, 3, 5...)
                start = match.start() + offset_shift
                end = match.end() + offset_shift
                # Preserve capitalization context
                if start == 0 or text[start - 2:start].rstrip().endswith(('.', '!', '?')):
                    replacement = employee
                else:
                    replacement = employee
                text = text[:start] + replacement + text[end:]
                offset_shift += len(replacement) - (match.end() - match.start())

    # Same for "the supervisor" — alternate with "management" or "the on-site supervisor"
    _sup_pattern = re.compile(r"\bthe supervisor\b", re.IGNORECASE)
    _sup_matches = list(_sup_pattern.finditer(text))
    if len(_sup_matches) > 2:
        _sup_alts = ["the on-duty supervisor", "management"]
        offset_shift = 0
        alt_idx = 0
        for idx_m, match in enumerate(_sup_matches):
            if idx_m % 2 == 1:
                start = match.start() + offset_shift
                end = match.end() + offset_shift
                replacement = _sup_alts[alt_idx % len(_sup_alts)]
                # Capitalize if at sentence start
                if start == 0 or text[max(0, start - 2):start].rstrip().endswith(('.', '!', '?')):
                    replacement = replacement[0].upper() + replacement[1:]
                text = text[:start] + replacement + text[end:]
                offset_shift += len(replacement) - (match.end() - match.start())
                alt_idx += 1

    # Collapse any double spaces introduced by replacements
    text = re.sub(r"  +", " ", text)
    # Fix any double periods
    text = re.sub(r"\.\.+", ".", text)
    # Fix space before period/comma
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    # Fix missing space after period (but not in decimals or abbreviations like a.m.)
    text = re.sub(r"\.([A-Z])", r". \1", text)

    return text


def _detect_additional_citations(narrative: str, violation_type: str) -> list:
    """Detect keywords in narrative that warrant additional policy citations."""
    citations = []
    lower = narrative.lower()

    if "Type A" in violation_type:
        if any(kw in lower for kw in ["no call", "no show", "ncns", "no-call", "no-show"]):
            citations.append("(Violation Section 3.7 — No Call / No Show)")
        if any(kw in lower for kw in ["call off", "call-off", "called off", "called out"]):
            citations.append("(Violation Section 3.6 — Call-Off Procedures)")
    else:
        if any(kw in lower for kw in ["insubordinat", "refused", "refusal", "defied", "defy"]):
            citations.append("(Violation Section 4.3 — Insubordination)")
        if any(kw in lower for kw in ["abandon", "left post", "left the post", "walked off"]):
            citations.append("(Violation Section 4.5 — Post Abandonment)")
        if any(kw in lower for kw in ["uniform", "appearance", "out of uniform", "dress code"]):
            citations.append("(Violation Section 6.1 — Uniform and Appearance Standards)")
        if any(kw in lower for kw in ["force", "physical", "struck", "pushed", "grabbed"]):
            citations.append("(Violation Section 5.1 — Use of Force)")
        if any(kw in lower for kw in ["disrespect", "hostile", "threaten", "profan", "vulgar"]):
            citations.append("(Violation Section 4.2 — Workplace Conduct)")

    return citations


def _build_citations(sections, violation_type, intake):
    """Build Section 2: Exact Policy Citations — CEIS v5.6 format with narrative-detected extras."""
    parts = []

    # Primary policy citations
    for sec_id in sections:
        info = HANDBOOK_SECTIONS.get(sec_id)
        if info:
            parts.append(
                f"Section {sec_id} — {info['title']}\n\"{info['quote']}\""
            )

    # Detect and add additional citations from narrative keywords
    narrative = intake.get("incident_narrative", "").lower()
    cited = set(sections)

    extra_sections = []
    if any(kw in narrative for kw in ["insubordinat", "refused", "refusal", "directive"]):
        if "4.3" not in cited:
            extra_sections.append("4.3")
    if any(kw in narrative for kw in ["abandon", "left post", "walked off"]):
        if "4.5" not in cited:
            extra_sections.append("4.5")
    if any(kw in narrative for kw in ["force", "physical", "struck", "pushed", "grabbed"]):
        if "5.1" not in cited:
            extra_sections.append("5.1")
    if any(kw in narrative for kw in ["uniform", "appearance", "dress code"]):
        if "6.1" not in cited:
            extra_sections.append("6.1")
    if any(kw in narrative for kw in ["hostile", "threaten", "profan", "disrespect", "vulgar"]):
        if "4.2" not in cited:
            extra_sections.append("4.2")
    if any(kw in narrative for kw in ["no call", "no show", "ncns"]):
        if "3.7" not in cited:
            extra_sections.append("3.7")
    if any(kw in narrative for kw in ["call off", "call-off", "called off"]):
        if "3.6" not in cited:
            extra_sections.append("3.6")

    if extra_sections:
        parts.append("\n— Additional Applicable Policies —")
        for sec_id in extra_sections:
            info = HANDBOOK_SECTIONS.get(sec_id)
            if info:
                parts.append(
                    f"\nSection {sec_id} — {info['title']}\n\"{info['quote']}\""
                )

    return "\n\n".join(parts)


def _build_violation_analysis(employee, violation_type, narrative, prior_summary, intake):
    """Build Section 3: Violation Analysis — CEIS v5.6 evidence-based format."""
    parts = []
    dates = intake.get("incident_dates", "the date(s) in question")

    if "Type A" in violation_type:
        points = intake.get("attendance_points_at_da", 0)
        parts.append(
            f"ELEMENT 1 — Pattern of Attendance Infractions:\n"
            f"The attendance record for {employee} demonstrates a documented pattern of "
            f"attendance-related infractions that has persisted despite prior corrective "
            f"action. The employee currently carries {points} active disciplinary points "
            f"under the Company's progressive attendance point system (Section 3.5.1). "
            f"Points accumulate on a rolling 365-day window and are applied consistently "
            f"across all personnel."
        )
        parts.append(
            f"\nELEMENT 2 — Threshold Violation:\n"
            f"The most recent infraction, occurring on {dates}, resulted in the accumulation "
            f"of points sufficient to cross the next disciplinary threshold. Under the "
            f"established point system, the current point total of {points} triggers "
            f"the corresponding level of progressive discipline as outlined in Section 3.5.1."
        )
        parts.append(
            f"\nELEMENT 3 — Prior Notice and Opportunity to Correct:\n"
            f"{prior_summary} The employee was made aware of the Company's attendance "
            f"expectations and the progressive point system at the time of hire, and this "
            f"policy was reiterated at each prior disciplinary step. The employee has been "
            f"afforded reasonable opportunity to correct the attendance pattern and has "
            f"failed to demonstrate sustained improvement."
        )

        # Detect specific attendance sub-type from narrative
        lower_narr = narrative.lower() if narrative else ""
        if any(kw in lower_narr for kw in ["no call", "no show", "ncns"]):
            parts.append(
                f"\nELEMENT 4 — No Call / No Show:\n"
                f"The infraction constitutes a No Call / No Show (NCNS) under Section 3.7. "
                f"The employee failed to report for the scheduled shift and failed to provide "
                f"notification to the operations center or direct supervisor. Per policy, "
                f"a first NCNS offense carries 6 points and an automatic Written Warning; "
                f"a second NCNS is grounds for immediate termination."
            )
        elif any(kw in lower_narr for kw in ["call off", "call-off", "called off"]):
            parts.append(
                f"\nELEMENT 4 — Call-Off Procedure Violation:\n"
                f"The employee's call-off is subject to evaluation under Section 3.6 — "
                f"Call-Off Procedures. Employees are required to provide at least four (4) "
                f"hours of advance notice prior to the start of a scheduled shift. Failure "
                f"to meet this notice requirement results in additional disciplinary points."
            )

    elif "Type B" in violation_type:
        parts.append(
            f"ELEMENT 1 — Factual Basis:\n"
            f"On {dates}, {employee} engaged in conduct that constitutes a violation of "
            f"established company policy. The documented facts, as set forth in the Incident "
            f"Narrative above, establish that the employee's actions and/or behavior fell "
            f"below the professional standards required of all Cerasus Security personnel "
            f"under Section 4.1 — Standards of Conduct."
        )
        parts.append(
            f"\nELEMENT 2 — Policy Application:\n"
            f"The conduct described is specifically prohibited under Section 4.1, which "
            f"requires all employees to \"conduct themselves in a professional manner at "
            f"all times while on duty.\" The employee's behavior as documented in the "
            f"incident narrative directly contravenes this standard."
        )

        # Detect additional elements from narrative
        lower_narr = narrative.lower() if narrative else ""
        if any(kw in lower_narr for kw in ["insubordinat", "refused", "refusal", "directive"]):
            parts.append(
                f"\nELEMENT 3 — Insubordination:\n"
                f"The facts further establish a violation of Section 4.3 — Insubordination. "
                f"The employee's refusal to follow a lawful and reasonable directive from a "
                f"supervisor or management representative constitutes a separate and distinct "
                f"policy violation that compounds the severity of the incident."
            )
        if any(kw in lower_narr for kw in ["hostile", "threaten", "profan", "disrespect"]):
            parts.append(
                f"\nELEMENT 3 — Workplace Conduct:\n"
                f"The facts further establish a violation of Section 4.2 — Workplace Conduct. "
                f"The employee's behavior demonstrates a failure to maintain professional "
                f"demeanor and treat others with courtesy and respect as required by policy."
            )

        parts.append(
            f"\n\nPRIOR DISCIPLINE HISTORY:\n{prior_summary}"
        )

        if intake.get("coaching_occurred"):
            parts.append(
                f"\nCOACHING INTERVENTION:\n"
                f"A management coaching session was conducted with {employee} on "
                f"{intake.get('coaching_date', 'a prior date')} addressing "
                f"{intake.get('coaching_content', 'the behavior in question')}. "
                f"The outcome of that session was documented as: "
                f"{intake.get('coaching_outcome', 'N/A')}. Despite this corrective "
                f"intervention, the employee has failed to demonstrate the required "
                f"improvement, and the behavior has continued or recurred."
            )
        else:
            if any([intake.get("prior_verbal_same"), intake.get("prior_written_same"),
                     intake.get("prior_final_same")]):
                parts.append(
                    f"\nThe employee has received prior discipline for the same or similar "
                    f"conduct and was placed on notice that further violations would result "
                    f"in escalated disciplinary action."
                )

    else:  # Type C — Employment Review
        parts.append(
            f"ELEMENT 1 — Basis for Employment Review:\n"
            f"An Employment Review has been initiated for {employee} based on the "
            f"totality of the employee's disciplinary record and the nature of the "
            f"current incident occurring on {dates}. The cumulative record reflects "
            f"a persistent pattern of policy violations that has not been corrected "
            f"through progressive discipline."
        )
        parts.append(
            f"\nELEMENT 2 — Progressive Discipline Exhaustion:\n"
            f"{prior_summary} The prior disciplinary steps afforded the employee "
            f"notice of the deficiency, an opportunity to correct the behavior, and "
            f"clear warning that continued violations would result in further action "
            f"up to and including termination. The employee has failed to sustain "
            f"the required improvement."
        )
        parts.append(
            f"\nELEMENT 3 — Current Incident Severity:\n"
            f"The current incident, as detailed in the Incident Narrative, demonstrates "
            f"that prior corrective measures have been insufficient to bring the "
            f"employee's conduct into compliance with Company standards. The severity "
            f"and/or frequency of the violations warrants a comprehensive review of "
            f"continued employment."
        )

    return "\n".join(parts)


def _build_discipline_determination(employee, violation_type, discipline_level,
                                     prior_summary, intake):
    """Build Section 4: Discipline Level Determination — CEIS v5.6 format."""
    parts = []

    # ── Type classification with detailed rationale ──
    if "Type A" in violation_type:
        type_label = "Type A — Attendance"
        points = intake.get("attendance_points_at_da", 0)
        parts.append(
            f"VIOLATION CLASSIFICATION: {type_label}\n\n"
            f"This infraction is classified as a Type A — Attendance violation under "
            f"Section 3.5 of the Employee Handbook. Attendance violations are governed "
            f"by the progressive point system outlined in Section 3.5.1.\n\n"
            f"POINT ANALYSIS:\n"
            f"  Current Active Points: {points}\n"
            f"  Disciplinary Thresholds:\n"
            f"    2 points  — Verbal Warning\n"
            f"    4 points  — Written Warning\n"
            f"    6 points  — Final Written Warning\n"
            f"    8 points  — Employment Review\n"
            f"    10 points — Termination Eligible\n\n"
            f"The employee's current point total of {points} has reached or exceeded "
            f"the threshold for the next level of progressive discipline."
        )
    elif "Type C" in violation_type:
        type_label = "Type C — Employment Review"
        parts.append(
            f"VIOLATION CLASSIFICATION: {type_label}\n\n"
            f"This matter is classified as a Type C — Employment Review based on the "
            f"cumulative severity of the employee's disciplinary record. An Employment "
            f"Review represents a comprehensive evaluation of continued employment and "
            f"is reserved for cases where progressive discipline has been exhausted or "
            f"the nature of the conduct is sufficiently serious to warrant immediate "
            f"review."
        )
    else:
        type_label = "Type B — Performance/Conduct"
        parts.append(
            f"VIOLATION CLASSIFICATION: {type_label}\n\n"
            f"This infraction is classified as a Type B — Performance/Conduct violation "
            f"under Section 4.1 of the Employee Handbook. Performance and conduct "
            f"violations follow the standard progressive discipline track."
        )

    parts.append(f"\nPRIOR DISCIPLINE RECORD:\n{prior_summary}")

    parts.append(f"\nDETERMINED DISCIPLINE LEVEL: {discipline_level}")

    # ── Detailed rationale for the discipline level ──
    if discipline_level == "Termination":
        parts.append(
            f"\nRATIONALE:\n"
            f"The cumulative disciplinary record, combined with the current violation, "
            f"demonstrates that progressive discipline has been fully exhausted. "
            f"{employee} has been afforded multiple opportunities to correct the "
            f"identified deficiencies through verbal counseling, written warnings, "
            f"and/or final warnings. Despite these interventions, the employee has "
            f"failed to demonstrate sustained improvement. Continued employment is "
            f"no longer viable given the exhaustion of all progressive discipline "
            f"steps and the employee's failure to meet minimum performance and/or "
            f"conduct standards."
        )
    elif discipline_level == "Final Warning":
        parts.append(
            f"\nRATIONALE:\n"
            f"Based on the prior disciplinary record and the nature of the current "
            f"violation, a Final Written Warning is the appropriate next step in the "
            f"progressive discipline process. This represents the last corrective "
            f"step before termination becomes the recommended action. {employee} is "
            f"hereby placed on final notice that any further violations of company "
            f"policy, regardless of type, may result in immediate termination of "
            f"employment."
        )
    elif discipline_level == "Written Warning":
        parts.append(
            f"\nRATIONALE:\n"
            f"The current violation, combined with the prior disciplinary record, "
            f"warrants escalation to a Written Warning under the progressive "
            f"discipline framework. This Written Warning serves as formal "
            f"documentation that {employee} has been counseled on the expected "
            f"standards and that further violations will result in escalated "
            f"disciplinary action up to and including termination."
        )
    else:  # Verbal Warning
        parts.append(
            f"\nRATIONALE:\n"
            f"This Verbal Warning constitutes the initial step in the progressive "
            f"discipline process. It is intended as a corrective measure to formally "
            f"document the deficiency and provide {employee} with clear notice of "
            f"the expected standards of performance and/or conduct. The employee is "
            f"advised that further violations will result in escalated disciplinary "
            f"action."
        )

    return "\n".join(parts)


def _build_risk_assessment(employee, discipline_level, prior_summary, intake):
    """Build Section 5: Risk Assessment — CEIS v5.6 comprehensive format."""
    parts = []
    narrative = intake.get("incident_narrative", "").lower()
    has_witnesses = intake.get("has_witness_statements", False)
    has_coaching = intake.get("coaching_occurred", False)
    has_prior_docs = any([
        intake.get("prior_verbal_same"), intake.get("prior_written_same"),
        intake.get("prior_final_same"),
    ])

    if discipline_level == "Termination":
        parts.append("OVERALL RISK LEVEL: ELEVATED")
        parts.append(
            "\n\nA termination action carries the highest level of procedural and legal "
            "risk. The following assessment evaluates the strength of the Company's "
            "position and identifies any gaps that should be addressed before execution."
        )
        parts.append("\n\nDUE PROCESS EVALUATION:")
        parts.append(
            "\n  1. Progressive Discipline Documentation: "
            + ("ADEQUATE — Prior discipline steps (verbal, written, and/or final "
               "warnings) are documented in the employee's file, establishing a "
               "clear progression of corrective action." if has_prior_docs
               else "DEFICIENCY NOTED — The progressive discipline record may be "
                    "incomplete. Management should verify that all prior disciplinary "
                    "steps are properly documented and accessible before proceeding "
                    "with termination. Gaps in the progressive record create exposure "
                    "to claims of procedural unfairness.")
        )
        parts.append(
            "\n  2. Coaching/Corrective Intervention: "
            + ("DOCUMENTED — A management coaching session was conducted and documented, "
               "demonstrating that the Company provided corrective guidance prior to "
               "escalating discipline." if has_coaching
               else "NOT DOCUMENTED — No formal coaching session is documented in the "
                    "record. While not legally required, the absence of a documented "
                    "coaching intervention prior to termination may be cited as evidence "
                    "of insufficient corrective effort. Consider whether coaching was "
                    "conducted informally and can be documented retroactively.")
        )
        parts.append(
            "\n  3. Evidentiary Support: "
            + ("ADEQUATE — Witness statements are on file to corroborate the factual "
               "basis of the violation." if has_witnesses
               else "DEFICIENCY NOTED — No witness statements are on file. For "
                    "termination actions, independent corroboration of the facts "
                    "significantly strengthens the Company's position. Consider "
                    "obtaining written statements from any witnesses before "
                    "proceeding.")
        )
        parts.append(
            "\n  4. Consistency of Enforcement: Management must verify that this "
            "termination action is consistent with discipline applied to other "
            "employees for similar violations. Inconsistent application of discipline "
            "creates exposure to claims of disparate treatment."
        )
        parts.append(
            "\n  5. Protected Class Considerations: Confirm that no protected class "
            "factors (race, gender, age, disability, religion, national origin) "
            "could be construed as motivating factors in this action. The decision "
            "must be based solely on documented performance and/or conduct."
        )

    elif discipline_level == "Final Warning":
        parts.append("OVERALL RISK LEVEL: MODERATE")
        parts.append(
            "\n\nA Final Written Warning is the last corrective step before termination "
            "and carries moderate procedural risk. This assessment identifies factors "
            "that should be addressed to ensure the action is defensible."
        )
        parts.append("\n\nKEY RISK FACTORS:")
        parts.append(
            "\n  1. Documentation Completeness: "
            + ("Prior discipline steps are documented." if has_prior_docs
               else "Verify that all prior discipline is documented and accessible. "
                    "A Final Warning without documented prior steps weakens the "
                    "progressive discipline chain.")
        )
        parts.append(
            "\n  2. Specificity of Expectations: The Final Warning must clearly "
            "articulate the specific improvements required and the timeline for "
            "compliance. Vague or general expectations are difficult to enforce."
        )
        parts.append(
            "\n  3. Follow-Up Mechanism: A defined review period (30–90 days) should "
            "be established to evaluate compliance. Failure to follow up undermines "
            "the credibility of the disciplinary process."
        )
        parts.append(
            "\n  4. Employee Acknowledgment: Obtain the employee's signature "
            "acknowledging receipt. If the employee refuses to sign, document the "
            "refusal with a witness present."
        )

    elif discipline_level == "Written Warning":
        parts.append("OVERALL RISK LEVEL: LOW TO MODERATE")
        parts.append(
            "\n\nA Written Warning carries low to moderate risk. Standard documentation "
            "and procedural requirements apply."
        )
        parts.append("\n\nKEY CONSIDERATIONS:")
        parts.append(
            "\n  1. Consistent Application: Ensure this action aligns with discipline "
            "applied to other employees for similar violations."
        )
        parts.append(
            "\n  2. Clear Communication: The Written Warning must clearly state the "
            "violation, the expected correction, and the consequences of further "
            "violations."
        )
        parts.append(
            "\n  3. Employee Acknowledgment: Obtain the employee's signature. Document "
            "the employee's response or any objections raised."
        )

    else:  # Verbal Warning
        parts.append("OVERALL RISK LEVEL: LOW")
        parts.append(
            "\n\nA Verbal Warning is the initial corrective step and carries minimal "
            "procedural risk. Standard documentation practices should be followed."
        )
        parts.append("\n\nKEY CONSIDERATIONS:")
        parts.append(
            "\n  1. File Documentation: Although verbal, this counseling must be "
            "documented in the employee's personnel file to preserve the progressive "
            "discipline chain."
        )
        parts.append(
            "\n  2. Clear Expectations: Communicate the specific behavior that must "
            "change and the consequences of continued violations."
        )
        parts.append(
            "\n  3. Follow-Up: Monitor the employee's performance/conduct and "
            "document any improvement or recurrence."
        )

    return "".join(parts)


def _build_recommendation(employee, discipline_level, violation_type, prior_summary):
    """Build Section 6: Final Recommendation — CEIS v5.6 comprehensive format."""
    parts = []

    parts.append(f"RECOMMENDED ACTION: {discipline_level.upper()}")

    if discipline_level == "Termination":
        parts.append(
            f"\n\nBased on the totality of the evidence, the cumulative disciplinary "
            f"record, and the exhaustion of progressive discipline, it is the "
            f"recommendation of this analysis that {employee}'s employment with "
            f"Cerasus Security be terminated effective immediately."
        )
        parts.append(
            f"\n\nThe record demonstrates that {employee} has been afforded every "
            f"reasonable opportunity to correct the identified deficiencies through "
            f"the progressive discipline process. Despite verbal counseling, written "
            f"warnings, and final warnings, the employee has failed to achieve or "
            f"sustain the required standards of {'attendance' if 'Type A' in violation_type else 'performance and conduct'}. "
            f"Continued employment is not supportable given the exhaustion of all "
            f"corrective measures."
        )
        parts.append(
            "\n\nEXECUTION CHECKLIST:"
            "\n  1. Review all progressive discipline documentation for completeness "
            "and accuracy."
            "\n  2. Confirm consistency with prior termination actions for similar "
            "violations."
            "\n  3. Obtain management/HR approval prior to execution."
            "\n  4. Prepare separation paperwork, including final pay calculations."
            "\n  5. Conduct the termination meeting with a management witness present."
            "\n  6. Collect all company property: uniform, identification badge, keys, "
            "radio, and any other issued equipment."
            "\n  7. Deactivate access credentials and system accounts."
            "\n  8. Document the termination meeting and the employee's response."
        )
    elif discipline_level == "Final Warning":
        parts.append(
            f"\n\nIt is recommended that {employee} receive a Final Written Warning. "
            f"This action represents the last corrective step in the progressive "
            f"discipline process. {employee} is hereby placed on formal notice that "
            f"any further violation of company policy — regardless of type or severity "
            f"— may result in the immediate termination of employment."
        )
        parts.append(
            f"\n\nThe purpose of this Final Warning is to provide {employee} with one "
            f"final opportunity to demonstrate that they can meet the minimum standards "
            f"required for continued employment. The Company's expectation is that the "
            f"employee will take immediate and sustained corrective action."
        )
        parts.append(
            "\n\nCONDITIONS AND FOLLOW-UP:"
            "\n  1. Present the Final Warning in a formal, private meeting with a "
            "management witness."
            "\n  2. Clearly articulate the specific improvements required and the "
            "timeline for compliance."
            "\n  3. Establish a review period of 30 to 90 days during which the "
            "employee's performance/conduct will be closely monitored."
            "\n  4. Obtain the employee's signature acknowledging receipt. If the "
            "employee refuses to sign, document the refusal with a witness."
            "\n  5. Schedule follow-up check-in(s) to assess compliance and document "
            "progress or continued deficiency."
        )
    elif discipline_level == "Written Warning":
        parts.append(
            f"\n\nIt is recommended that {employee} receive a Written Warning. This "
            f"action constitutes a formal escalation within the progressive discipline "
            f"process and serves as documented notice that the employee's "
            f"{'attendance record' if 'Type A' in violation_type else 'conduct and/or performance'} "
            f"is not meeting company standards."
        )
        parts.append(
            f"\n\n{employee} is expected to take immediate corrective action and "
            f"maintain full compliance with all company policies, procedures, and "
            f"directives going forward. Failure to do so will result in further "
            f"escalation of discipline up to and including termination of employment."
        )
        parts.append(
            "\n\nCONDITIONS AND FOLLOW-UP:"
            "\n  1. Present the Written Warning in a private meeting."
            "\n  2. Clearly explain the specific behavior or pattern that must be "
            "corrected."
            "\n  3. Document the employee's response and any commitments made."
            "\n  4. Obtain the employee's signature acknowledging receipt."
            "\n  5. Follow up within 30 days to evaluate compliance."
        )
    else:  # Verbal Warning
        parts.append(
            f"\n\nIt is recommended that {employee} receive a Verbal Warning. This "
            f"action constitutes the initial step in the progressive discipline "
            f"process and is intended as a corrective measure to formally address "
            f"the identified deficiency."
        )
        parts.append(
            f"\n\nThe purpose of this Verbal Warning is to ensure that {employee} "
            f"is aware of the Company's expectations and understands that continued "
            f"violations will result in escalated disciplinary action. The employee "
            f"is expected to correct the behavior immediately and maintain compliance "
            f"with all company policies and procedures."
        )
        parts.append(
            "\n\nCONDITIONS AND FOLLOW-UP:"
            "\n  1. Conduct the verbal counseling in a private setting."
            "\n  2. Clearly communicate the expected standards and the consequences "
            "of further violations."
            "\n  3. Document the conversation and the employee's acknowledgment in "
            "the personnel file."
            "\n  4. Follow up within 30 days to confirm sustained improvement."
        )

    return "".join(parts)


# ═══════════════════════════════════════════════════════════════════════
#  Required Improvements Generator
# ═══════════════════════════════════════════════════════════════════════

def generate_required_improvements(discipline_level: str, violation_type: str) -> str:
    """
    Generate conduct-specific required improvements text.
    Checks for custom templates first, falls back to hardcoded defaults.
    """
    # Try custom templates
    custom = _load_custom_templates(violation_type)
    if custom:
        imp_text = custom.get("improvements", {}).get(discipline_level, "")
        if imp_text and imp_text.strip():
            return imp_text

    # Fallback to hardcoded defaults
    if discipline_level == "Termination":
        return "N/A -- Employment terminated."

    improvements = []

    if "Type A" in violation_type:
        improvements.extend([
            "Report to all scheduled shifts on time as assigned.",
            "Provide proper advance notice (minimum 4 hours) for any absences.",
            "Maintain regular and reliable attendance going forward.",
            "Review and acknowledge the company attendance policy.",
        ])
    elif "Type B" in violation_type:
        improvements.extend([
            "Conduct yourself professionally at all times while on duty.",
            "Follow all directives from supervisors and management.",
            "Comply with all company policies and post orders.",
            "Maintain appropriate workplace behavior and communication.",
        ])
    else:
        improvements.extend([
            "Demonstrate sustained improvement in overall job performance.",
            "Comply with all company policies and procedures.",
            "Participate in any required retraining or coaching sessions.",
            "Maintain open communication with your supervisor.",
        ])

    return "\n".join(f"- {item}" for item in improvements)


def _build_discipline_determination_with_templates(
    employee, violation_type, discipline_level, prior_summary, intake, custom
):
    """Build Section 4 using custom escalation language from templates."""
    parts = []

    # Type classification header (always hardcoded — it's structural)
    if "Type A" in violation_type:
        type_label = "Type A -- Attendance"
        parts.append(f"Violation Classification: {type_label}")
        points = intake.get("attendance_points_at_da", 0)
        parts.append(
            f"\nCurrent Active Points: {points}"
            f"\nThreshold Analysis: The employee's point total has reached or exceeded "
            f"the threshold for the next level of progressive discipline."
        )
    elif "Type C" in violation_type:
        type_label = "Type C -- Employment Review"
        parts.append(f"Violation Classification: {type_label}")
    else:
        type_label = "Type B -- Performance/Conduct"
        parts.append(f"Violation Classification: {type_label}")

    parts.append(f"\n{prior_summary}")
    parts.append(f"\nDetermined Discipline Level: {discipline_level}")

    # Use custom escalation language if available
    escalation = custom.get("escalation", {}).get(discipline_level, "")
    if escalation and escalation.strip():
        parts.append(f"\n{escalation}")
    else:
        progression_text = DISCIPLINE_PROGRESSION.get(discipline_level, "")
        if progression_text:
            parts.append(f"\n{progression_text}")

    if discipline_level == "Termination":
        parts.append(
            "\nThe cumulative disciplinary record, combined with the current violation, "
            "demonstrates that progressive discipline has been exhausted. The employee "
            "has been given multiple opportunities to correct the behavior and has "
            "failed to do so."
        )

    return "\n".join(parts)
