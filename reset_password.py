"""
Cerasus Hub — Password Reset Utility
Run from command line: python reset_password.py <username> <new_password>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.auth import _hash_password
from src.database import get_conn


def reset_password(username: str, new_password: str):
    conn = get_conn()
    row = conn.execute("SELECT username FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
    if not row:
        print(f"User '{username}' not found.")
        conn.close()
        return False

    pw_hash, salt = _hash_password(new_password)
    conn.execute("UPDATE users SET password_hash=?, salt=? WHERE username=?", (pw_hash, salt, username.strip().lower()))
    conn.commit()
    conn.close()
    print(f"Password reset for '{username}'. New password: {new_password}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python reset_password.py <username> <new_password>")
        print("\nExisting users:")
        conn = get_conn()
        for row in conn.execute("SELECT username, display_name, role FROM users WHERE active=1").fetchall():
            print(f"  {row['username']:35s} {row['display_name']:25s} ({row['role']})")
        conn.close()
    else:
        reset_password(sys.argv[1], sys.argv[2])
