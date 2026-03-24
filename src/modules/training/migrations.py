"""
Cerasus Hub -- Training Module: SQLite Schema Migrations
"""


def _migration_001(conn):
    """Create training module tables: courses, modules, chapters, tests, progress, attempts, certificates."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trn_courses (
            course_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'General Training',
            image_path TEXT DEFAULT '',
            status TEXT DEFAULT 'Published',
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS trn_modules (
            module_id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS trn_chapters (
            chapter_id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            content TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            has_test INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS trn_tests (
            test_id TEXT PRIMARY KEY,
            chapter_id TEXT DEFAULT '',
            course_id TEXT NOT NULL,
            title TEXT DEFAULT '',
            passing_score REAL DEFAULT 70.0,
            questions TEXT DEFAULT '[]',
            created_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS trn_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            officer_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            chapter_id TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            completed_at TEXT DEFAULT '',
            UNIQUE(officer_id, course_id, chapter_id)
        );

        CREATE TABLE IF NOT EXISTS trn_test_attempts (
            attempt_id TEXT PRIMARY KEY,
            officer_id TEXT NOT NULL,
            test_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            score REAL DEFAULT 0,
            passed INTEGER DEFAULT 0,
            answers TEXT DEFAULT '[]',
            started_at TEXT DEFAULT '',
            completed_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS trn_certificates (
            cert_id TEXT PRIMARY KEY,
            officer_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            issued_date TEXT DEFAULT '',
            expiry_date TEXT DEFAULT '',
            status TEXT DEFAULT 'Active',
            points_earned INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_trn_modules_course ON trn_modules(course_id);
        CREATE INDEX IF NOT EXISTS idx_trn_chapters_module ON trn_chapters(module_id);
        CREATE INDEX IF NOT EXISTS idx_trn_chapters_course ON trn_chapters(course_id);
        CREATE INDEX IF NOT EXISTS idx_trn_tests_chapter ON trn_tests(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_trn_tests_course ON trn_tests(course_id);
        CREATE INDEX IF NOT EXISTS idx_trn_progress_officer ON trn_progress(officer_id);
        CREATE INDEX IF NOT EXISTS idx_trn_progress_course ON trn_progress(course_id);
        CREATE INDEX IF NOT EXISTS idx_trn_attempts_officer ON trn_test_attempts(officer_id);
        CREATE INDEX IF NOT EXISTS idx_trn_attempts_test ON trn_test_attempts(test_id);
        CREATE INDEX IF NOT EXISTS idx_trn_certs_officer ON trn_certificates(officer_id);
        CREATE INDEX IF NOT EXISTS idx_trn_certs_course ON trn_certificates(course_id);
    """)


MIGRATIONS = {1: _migration_001}
