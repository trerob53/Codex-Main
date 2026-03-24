"""
Cerasus Hub -- Document Vault
Store and manage files (Guard Cards, Training Certs, IDs, etc.) per officer.
Files live in documents/{officer_id}/ next to the EXE; metadata tracked in SQLite.
"""

import os
import secrets
import shutil
from datetime import datetime, timezone, timedelta

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from src.config import ROOT_DIR
from src.database import get_conn

# ── Constants ─────────────────────────────────────────────────────────

DOCS_DIR = os.path.join(ROOT_DIR, "documents")

DOC_TYPES = [
    "Signed DA",
    "Guard Card",
    "Driver's License",
    "Training Certificate",
    "Photo ID",
    "Background Check",
    "Drug Test",
    "Other",
]

# ── Schema ────────────────────────────────────────────────────────────

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS document_vault (
    doc_id TEXT PRIMARY KEY,
    officer_id TEXT NOT NULL,
    officer_name TEXT DEFAULT '',
    doc_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    expiry_date TEXT DEFAULT '',
    uploaded_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _ensure_table():
    """Create the document_vault table if it does not exist."""
    conn = get_conn()
    conn.executescript(_TABLE_SQL)
    conn.commit()
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────

def _gen_id() -> str:
    return secrets.token_hex(12)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_docs_dir(officer_id: str = "") -> str:
    """Create the documents/ directory (and optional officer sub-dir).
    Returns the path that was ensured."""
    path = os.path.join(DOCS_DIR, officer_id) if officer_id else DOCS_DIR
    os.makedirs(path, exist_ok=True)
    return path


# ── CRUD ──────────────────────────────────────────────────────────────

def upload_document(
    officer_id: str,
    officer_name: str,
    doc_type: str,
    source_path: str,
    description: str = "",
    expiry_date: str = "",
    uploaded_by: str = "",
) -> str:
    """Copy *source_path* into documents/{officer_id}/ and record metadata.
    Returns the new doc_id."""
    _ensure_table()
    dest_dir = ensure_docs_dir(officer_id)

    original_filename = os.path.basename(source_path)
    doc_id = _gen_id()

    # Build a unique on-disk name to avoid collisions
    ext = os.path.splitext(original_filename)[1]
    stored_name = f"{doc_id}{ext}"
    dest_path = os.path.join(dest_dir, stored_name)

    shutil.copy2(source_path, dest_path)
    file_size = os.path.getsize(dest_path)

    conn = get_conn()
    conn.execute(
        """INSERT INTO document_vault
           (doc_id, officer_id, officer_name, doc_type, filename, original_filename,
            file_path, file_size, description, expiry_date, uploaded_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, officer_id, officer_name, doc_type, stored_name,
            original_filename, dest_path, file_size, description,
            expiry_date, uploaded_by, _now(),
        ),
    )
    conn.commit()
    conn.close()
    return doc_id


def get_documents_for_officer(officer_id: str) -> list[dict]:
    """Return all documents for the given officer, newest first."""
    _ensure_table()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM document_vault WHERE officer_id = ? ORDER BY created_at DESC",
        (officer_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_expiring_documents(days: int = 30) -> list[dict]:
    """Return documents whose expiry_date is within *days* from today."""
    _ensure_table()
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=days)
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM document_vault
           WHERE expiry_date != '' AND expiry_date IS NOT NULL
           ORDER BY expiry_date""",
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        r = dict(r)
        try:
            exp = datetime.strptime(r["expiry_date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if exp <= horizon:
            r["_days_remaining"] = (exp - today).days
            results.append(r)
    results.sort(key=lambda d: d.get("expiry_date", ""))
    return results


def delete_document(doc_id: str) -> bool:
    """Remove a document's file and its metadata row. Returns True on success."""
    _ensure_table()
    conn = get_conn()
    row = conn.execute(
        "SELECT file_path FROM document_vault WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    file_path = row["file_path"]
    conn.execute("DELETE FROM document_vault WHERE doc_id = ?", (doc_id,))
    conn.commit()
    conn.close()

    # Remove the physical file (best-effort)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
    return True


def open_document(doc_id: str) -> bool:
    """Open the document with the system default application.
    Returns True if the file was found and the open request was sent."""
    _ensure_table()
    conn = get_conn()
    row = conn.execute(
        "SELECT file_path FROM document_vault WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    file_path = row["file_path"]
    if not os.path.exists(file_path):
        return False
    QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
    return True
