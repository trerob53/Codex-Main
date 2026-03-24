"""Dev server wrapper for preview tools."""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from src.config import ensure_directories
from src.database import (
    initialize_database, run_module_migrations,
    ensure_module_permissions_column, ensure_assigned_sites_column,
    ensure_default_flex_officers,
)
from src.auth import initialize_users
from src.modules import discover_modules

ensure_directories()
initialize_database()
ensure_module_permissions_column()
ensure_assigned_sites_column()
modules = discover_modules()
run_module_migrations(modules)
ensure_default_flex_officers()
initialize_users()

from src.shared_data import backfill_employee_ids
backfill_employee_ids()

from src.web_app import create_app
app = create_app()

print("Starting Cerasus Hub on http://localhost:8420", flush=True)
app.run(host="0.0.0.0", port=8420, debug=False)
