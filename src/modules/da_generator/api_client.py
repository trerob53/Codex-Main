"""
Cerasus Hub — DA Generator: Anthropic API Client
Handles communication with Claude API for CEIS engine and clarifying questions.
"""

import json
import urllib.request
import urllib.error
from PySide6.QtCore import QThread, Signal
from src.database import get_conn


def get_api_key() -> str:
    """Read Anthropic API key from settings table."""
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'da_anthropic_api_key'").fetchone()
    conn.close()
    return row["value"] if row else ""


def save_api_key(key: str):
    """Save Anthropic API key to settings table."""
    from datetime import datetime, timezone
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("da_anthropic_api_key", key, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()


def call_anthropic(system_prompt: str, user_message: str, max_tokens: int = 4096) -> dict:
    """
    Call Anthropic Messages API.
    Returns {"success": True, "content": "..."} or {"success": False, "error": "..."}
    """
    api_key = get_api_key()
    if not api_key:
        return {"success": False, "error": "No API key configured. Go to DA Generator > Configuration to set your Anthropic API key."}

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # Extract text from content blocks
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            return {"success": True, "content": text}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(body)
            msg = err_data.get("error", {}).get("message", body)
        except Exception:
            msg = body
        return {"success": False, "error": f"API Error ({e.code}): {msg}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Connection error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


class ApiWorker(QThread):
    """Background thread for API calls. Emits finished signal with result dict."""
    finished = Signal(dict)

    def __init__(self, system_prompt: str, user_message: str, max_tokens: int = 4096):
        super().__init__()
        self.system_prompt = system_prompt
        self.user_message = user_message
        self.max_tokens = max_tokens

    def run(self):
        result = call_anthropic(self.system_prompt, self.user_message, self.max_tokens)
        self.finished.emit(result)
