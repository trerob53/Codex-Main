"""
Cerasus Hub — Entry Point
Web-based operations hub served via Flask + Waitress.
Accessible on LAN at http://<machine-ip>:8420
"""

import sys
import os
import socket
import webbrowser
import threading

# Handle PyInstaller frozen paths
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
    os.chdir(base_dir)
    if os.path.join(base_dir, 'src') not in sys.path:
        sys.path.insert(0, base_dir)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

PORT = 8420


def _get_local_ip():
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    from src.config import ensure_directories
    from src.database import (
        initialize_database, run_module_migrations,
        ensure_module_permissions_column, ensure_assigned_sites_column,
        ensure_default_flex_officers,
    )
    from src.auth import initialize_users
    from src.modules import discover_modules

    # 1. Create runtime directories
    ensure_directories()

    # 2. Initialize database and run core migrations
    initialize_database()
    ensure_module_permissions_column()
    ensure_assigned_sites_column()

    # Check if a newer database exists in common locations
    import glob
    from src.config import DB_FILE
    possible_dbs = glob.glob(
        os.path.join(os.path.dirname(base_dir), "**", "cerasus_hub.db"),
        recursive=True,
    )
    if possible_dbs:
        newest = max(possible_dbs, key=os.path.getmtime)
        if newest != DB_FILE and os.path.getmtime(newest) > os.path.getmtime(DB_FILE) + 60:
            print(f"[Info] Newer database found at: {newest}")

    # 3. Discover modules and run their migrations
    modules = discover_modules()
    run_module_migrations(modules)
    ensure_default_flex_officers()

    # 4. Ensure default admin user exists
    initialize_users()

    # 5. Backfill any officers missing employee IDs
    from src.shared_data import backfill_employee_ids
    backfilled = backfill_employee_ids()
    if backfilled:
        print(f"[Info] Assigned employee IDs to {backfilled} officer(s)")

    # 6. Start background backup scheduler
    from src.backup_manager import BackupScheduler
    backup_scheduler = BackupScheduler(interval_hours=4)
    backup_scheduler.start()

    # 7. Create Flask app
    from src.web_app import create_app
    app = create_app()

    # 8. Print startup info and open browser
    local_ip = _get_local_ip()
    local_url = f"http://localhost:{PORT}"
    lan_url = f"http://{local_ip}:{PORT}"

    print()
    print("=" * 60)
    print("  CERASUS HUB — Web Server")
    print("=" * 60)
    print(f"  Local:   {local_url}")
    print(f"  Network: {lan_url}")
    print()
    print("  Share the Network URL with other users on your LAN.")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 60)
    print()

    # Open browser after a short delay
    threading.Timer(1.5, lambda: webbrowser.open(local_url)).start()

    # 9. Start Waitress WSGI server
    import waitress
    waitress.serve(app, host="0.0.0.0", port=PORT, threads=6)


if __name__ == "__main__":
    main()
