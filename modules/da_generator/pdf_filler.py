"""
Cerasus Hub — DA Generator: PDF Form Filler
Fills the official Cerasus "Notice of Disciplinary Action" fillable PDF form.
Uses pypdf to read the template and fill form fields with proper font sizing.
"""

import os
import sys
from datetime import datetime


# Handle frozen (PyInstaller) vs source paths
def _get_template_path() -> str:
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    # Try multiple locations
    candidates = [
        os.path.join(base, "src", "modules", "da_generator", "da_template.pdf"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "da_template.pdf"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]


# FIELD MAP — exact field names from the PDF
# IMPORTANT: The narrative/citations fields are SWAPPED in the PDF form
FIELD_MAP = {
    "employee_name": "Employee Name",
    "position": "Position",
    "site": "Job Location  Site",
    "supervisor": "Supervisor",
    "date_occurred": "Date Occurred",
    "date_written": "Date Written",
    "narrative": "Handbook Policy Violations",  # SWAPPED: narrative goes into this field ID
    "citations": "undefined",                   # SWAPPED: citations go into this field ID
    "prior_same": "Prior Discipline Same Issue",
    "prior_other": "Prior Discipline Other Issues",
    "improvements": "Text1",
    "supervisor_name_sig": "1",
    "employee_name_sig": "2",
    "additional_comments": "Additional Comments Optional",
    "suspension_from": "Suspension Dates if applicable From",
    "suspension_to": "To",
    "supervisor_date": "Date",
    "employee_date": "Date_2",
    "witness_date": "Date_3",
}

CHECKBOX_MAP = {
    "Verbal Warning": "Verbal Warning",
    "Written Warning": "Written Warning",
    "Suspension": "Suspension",
    "Final Warning": "Final Warning",
    "Termination": "Termination",
}

# Font sizes per field — larger for short fields, smaller for long-text areas
FIELD_FONT_SIZES = {
    "Employee Name": 11,
    "Position": 11,
    "Job Location  Site": 11,
    "Supervisor": 11,
    "Date Occurred": 11,
    "Date Written": 11,
    "Handbook Policy Violations": 10,  # Narrative — main text area
    "undefined": 10,                   # Citations — main text area
    "Prior Discipline Same Issue": 10,
    "Prior Discipline Other Issues": 10,
    "Text1": 10,                       # Improvements
    "Additional Comments Optional": 10,
    "1": 11,                           # Supervisor sig name
    "2": 11,                           # Employee sig name
    "Suspension Dates if applicable From": 11,
    "To": 11,
    "Date": 11,
    "Date_2": 11,
    "Date_3": 11,
}


def _sanitize(text):
    """Replace unicode chars that PDF standard fonts can't render."""
    if not isinstance(text, str):
        return str(text) if text else ""
    return (text
        .replace("\u2014", "--")   # em dash
        .replace("\u2013", "-")    # en dash
        .replace("\u2018", "'")    # left single quote
        .replace("\u2019", "'")    # right single quote
        .replace("\u201c", '"')    # left double quote
        .replace("\u201d", '"')    # right double quote
        .replace("\u2022", "-")    # bullet
        .replace("\u2026", "...")  # ellipsis
        .replace("\u00a0", " ")    # non-breaking space
        .replace("\u2705", "")     # checkmark emoji
        .replace("\u26a0", "[!]")  # warning emoji
        .replace("\u2192", "->")   # arrow
    )


def fill_da_pdf(output_path: str, da_data: dict) -> str:
    """
    Fill the Cerasus DA PDF template with the provided data.

    da_data expected keys:
        employee_name, position, site, supervisor, date_occurred,
        discipline_level (str: "Verbal Warning"/"Written Warning"/"Final Warning"/"Termination"),
        narrative, citations,
        prior_same, prior_other,
        improvements, additional_comments,
        suspension_from, suspension_to  (optional, for Suspension level)

    Returns the output file path on success, raises on failure.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject, ArrayObject, NumberObject, BooleanObject

    template_path = _get_template_path()
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"DA template PDF not found at: {template_path}")

    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)

    # Tell PDF viewers to regenerate field appearances from values
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"].update({
            NameObject("/NeedAppearances"): BooleanObject(True),
        })

    # Build field values
    field_values = {
        FIELD_MAP["employee_name"]: _sanitize(da_data.get("employee_name", "")),
        FIELD_MAP["position"]: _sanitize(da_data.get("position", "")),
        FIELD_MAP["site"]: _sanitize(da_data.get("site", "")),
        FIELD_MAP["supervisor"]: _sanitize(da_data.get("supervisor", "")),
        FIELD_MAP["date_occurred"]: _sanitize(da_data.get("date_occurred", "")),
        FIELD_MAP["date_written"]: da_data.get("date_written", datetime.now().strftime("%m/%d/%Y")),
        FIELD_MAP["narrative"]: _sanitize(da_data.get("narrative", "")),
        FIELD_MAP["citations"]: _sanitize(da_data.get("citations", "")),
        FIELD_MAP["prior_same"]: _sanitize(da_data.get("prior_same", "")),
        FIELD_MAP["prior_other"]: _sanitize(da_data.get("prior_other", "")),
        FIELD_MAP["improvements"]: _sanitize(da_data.get("improvements", "")),
        FIELD_MAP["additional_comments"]: _sanitize(da_data.get("additional_comments", "")),
        FIELD_MAP["suspension_from"]: da_data.get("suspension_from", ""),
        FIELD_MAP["suspension_to"]: da_data.get("suspension_to", ""),
        FIELD_MAP["supervisor_name_sig"]: _sanitize(da_data.get("supervisor", "")),
        FIELD_MAP["employee_name_sig"]: "",
        FIELD_MAP["supervisor_date"]: datetime.now().strftime("%m/%d/%Y"),
    }

    # Fill text fields with explicit font size control
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            obj = annot.get_object()
            field_name = obj.get("/T", "")
            if not field_name:
                continue

            # Skip checkboxes
            if obj.get("/FT") == "/Btn":
                continue

            if field_name in field_values:
                value = field_values[field_name]
                if not value:
                    continue

                # Set the value and remove cached appearance so viewer regenerates it
                obj.update({
                    NameObject("/V"): TextStringObject(value),
                })
                if "/AP" in obj:
                    del obj["/AP"]

                # Set font size in the Default Appearance string
                font_size = FIELD_FONT_SIZES.get(field_name, 10)
                da_string = f"/Helv {font_size} Tf 0 g"
                obj.update({
                    NameObject("/DA"): TextStringObject(da_string),
                })

                # For multi-line text fields, ensure multiline flag is set
                if field_name in ("Handbook Policy Violations", "undefined", "Text1",
                                  "Additional Comments Optional",
                                  "Prior Discipline Same Issue", "Prior Discipline Other Issues"):
                    # Set multiline flag (bit 13 = 4096)
                    current_flags = obj.get("/Ff", 0)
                    if isinstance(current_flags, int):
                        obj.update({NameObject("/Ff"): NumberObject(current_flags | 4096)})

    # Handle checkboxes for discipline level
    discipline_level = da_data.get("discipline_level", "")
    for level_name, field_name in CHECKBOX_MAP.items():
        checked = (level_name == discipline_level)
        _set_checkbox(writer, field_name, checked)

    # Handle Paid/Unpaid checkboxes for Suspension
    if discipline_level == "Suspension":
        suspension_type = da_data.get("suspension_type", "Unpaid")
        _set_checkbox(writer, "Paid", suspension_type == "Paid")
        _set_checkbox(writer, "Unpaid", suspension_type == "Unpaid")
    else:
        _set_checkbox(writer, "Paid", False)
        _set_checkbox(writer, "Unpaid", False)

    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Write filled PDF
    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path


def _set_checkbox(writer, field_name: str, checked: bool):
    """Set a checkbox field in the PDF."""
    from pypdf.generic import NameObject

    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            obj = annot.get_object()
            if obj.get("/T") == field_name:
                if checked:
                    # Try to find the 'on' value from the appearance dictionary
                    if "/AP" in obj and "/N" in obj["/AP"]:
                        states = list(obj["/AP"]["/N"].keys())
                        on_value = [s for s in states if s != "/Off"]
                        if on_value:
                            obj.update({
                                NameObject("/V"): NameObject(on_value[0]),
                                NameObject("/AS"): NameObject(on_value[0]),
                            })
                            return
                    obj.update({
                        NameObject("/V"): NameObject("/Yes"),
                        NameObject("/AS"): NameObject("/Yes"),
                    })
                else:
                    obj.update({
                        NameObject("/V"): NameObject("/Off"),
                        NameObject("/AS"): NameObject("/Off"),
                    })
                return


def generate_da_filename(employee_name: str, discipline_level: str, issue: str = "") -> str:
    """Generate filename: Last_First_VW/WW/FW/Termination_Issue.pdf"""
    parts = employee_name.strip().split()
    if len(parts) >= 2:
        last = parts[-1]
        first = parts[0]
    elif parts:
        last = parts[0]
        first = "Unknown"
    else:
        last = "Unknown"
        first = "Unknown"

    level_abbrev = {
        "Verbal Warning": "VW",
        "Written Warning": "WW",
        "Final Warning": "FW",
        "Suspension": "Suspension",
        "Termination": "Termination",
    }
    level_str = level_abbrev.get(discipline_level, discipline_level.replace(" ", ""))

    if not issue:
        issue = "DA"
    issue_clean = issue.replace(" ", "_")[:30]

    def safe(s):
        return "".join(c if c.isalnum() or c in "_-" else "_" for c in s)

    return f"{safe(last)}_{safe(first)}_{safe(level_str)}_{safe(issue_clean)}.pdf"
