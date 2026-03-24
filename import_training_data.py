"""
Cerasus Hub — Import Training Website Data
Imports course, module, and chapter content from the cerasus_training_export.json
file scraped from the live E-Learning platform.

Usage:
    python import_training_data.py [path_to_json]
"""

import json
import os
import sys
import secrets
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import ensure_directories
from src.database import initialize_database, get_conn


def _gen_id():
    return secrets.token_hex(8)


def _now():
    return datetime.now(timezone.utc).isoformat()


def import_data(json_path):
    print(f"[Import] Loading training data from: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ensure_directories()
    initialize_database()
    conn = get_conn()

    course_info = data["course"]
    module_info = data["module"]
    chapters = data["chapters"]

    # ── Course ────────────────────────────────────────────────────────
    course_id = _gen_id()

    # Check if course already exists by title
    existing = conn.execute(
        "SELECT course_id FROM trn_courses WHERE LOWER(title) = LOWER(?)",
        (course_info["title"],)
    ).fetchone()

    if existing:
        course_id = existing["course_id"]
        print(f"[Course] Already exists: {course_info['title']} (id={course_id})")

        # Delete existing chapters and module to re-import fresh content
        conn.execute("DELETE FROM trn_chapters WHERE course_id = ?", (course_id,))
        conn.execute("DELETE FROM trn_modules WHERE course_id = ?", (course_id,))
        conn.commit()
        print("  Cleared existing chapters and modules for re-import")
    else:
        conn.execute(
            """INSERT INTO trn_courses (course_id, title, description, category, status, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                course_id,
                course_info["title"],
                course_info.get("description", ""),
                course_info.get("category", "General Training"),
                course_info.get("status", "Published"),
                "system_import",
                _now(),
                _now(),
            ),
        )
        print(f"[Course] Created: {course_info['title']} (id={course_id})")

    # ── Module ────────────────────────────────────────────────────────
    module_id = _gen_id()
    conn.execute(
        """INSERT INTO trn_modules (module_id, course_id, title, sort_order, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            module_id,
            course_id,
            module_info.get("title", "Module 1"),
            module_info.get("sortOrder", 1),
            _now(),
        ),
    )
    print(f"[Module] Created: {module_info['title']} (id={module_id})")

    # ── Chapters ──────────────────────────────────────────────────────
    print(f"\n[Chapters] Importing {len(chapters)} chapters...")
    imported = 0
    for ch in chapters:
        try:
            chapter_id = _gen_id()
            title = ch.get("title", f"Chapter {ch.get('index', '?')}")

            # Clean content: remove the title from the beginning if it's repeated
            content = ch.get("content", "")
            if content.startswith(title):
                content = content[len(title):].strip()

            conn.execute(
                """INSERT INTO trn_chapters
                   (chapter_id, module_id, course_id, title, content, sort_order, has_test, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chapter_id,
                    module_id,
                    course_id,
                    title,
                    content,
                    ch.get("index", imported + 1),
                    0,  # no tests scraped
                    _now(),
                ),
            )
            imported += 1
            print(f"  Ch {ch.get('index', '?')}: {title[:55]} ({len(content)} chars)")
        except Exception as e:
            print(f"  [ERROR] Chapter {ch.get('index')}: {e}")

    conn.commit()
    conn.close()

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  TRAINING IMPORT COMPLETE")
    print("=" * 60)
    print(f"  Course:   {course_info['title']}")
    print(f"  Module:   {module_info['title']}")
    print(f"  Chapters: {imported} imported")
    total_chars = sum(ch.get("contentLength", 0) for ch in chapters)
    print(f"  Content:  {total_chars:,} characters total")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        candidates = [
            os.path.join(os.path.dirname(__file__), "cerasus_training_export.json"),
            os.path.expanduser("~/Downloads/cerasus_training_export.json"),
        ]
        path = None
        for c in candidates:
            if os.path.isfile(c):
                path = c
                break

    if not path or not os.path.isfile(path):
        print("ERROR: Could not find cerasus_training_export.json")
        sys.exit(1)

    import_data(path)
