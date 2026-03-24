"""
Cerasus Hub — Mobile Web Companion
Lightweight HTTP server for management access from mobile devices.
Runs on port 8420 alongside the desktop app, serves a mobile-friendly dashboard.
NO external dependencies — uses only Python stdlib.
"""

import json
import secrets
import socket
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from src.database import get_conn
from src import auth

# ── Session tokens (in-memory) ────────────────────────────────────────
_tokens = {}  # token -> {"username": ..., "role": ..., "created": ...}

_server_instance = None

COMPANION_PORT = 8420


def _get_local_ip() -> str:
    """Find the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _json_response(handler, data, status=200):
    """Send a JSON response."""
    body = json.dumps(data, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler) -> dict:
    """Read and parse JSON body from a POST request."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _check_auth(handler) -> dict | None:
    """Validate Authorization header token. Returns user info or None."""
    auth_header = handler.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return _tokens.get(token)
    return None


# ── API Handlers ──────────────────────────────────────────────────────

def _api_dashboard() -> dict:
    """Hub-level KPIs."""
    data = {
        "active_officers": 0,
        "pending_reviews": 0,
        "low_stock": 0,
        "open_requests": 0,
        "at_risk_officers": 0,
        "infractions_this_month": 0,
    }
    try:
        conn = get_conn()
        try:
            data["active_officers"] = conn.execute(
                "SELECT COUNT(*) as c FROM officers WHERE status = 'Active'"
            ).fetchone()["c"]
        except Exception:
            pass
        try:
            data["pending_reviews"] = conn.execute(
                "SELECT COUNT(*) as c FROM ats_employment_reviews WHERE review_status = 'Pending'"
            ).fetchone()["c"]
        except Exception:
            pass
        try:
            data["low_stock"] = conn.execute(
                "SELECT COUNT(*) as c FROM uni_catalog WHERE stock_qty <= reorder_point"
            ).fetchone()["c"]
        except Exception:
            pass
        try:
            data["open_requests"] = conn.execute(
                "SELECT COUNT(*) as c FROM ops_records WHERE status = 'Open'"
            ).fetchone()["c"]
        except Exception:
            pass
        try:
            data["at_risk_officers"] = conn.execute(
                "SELECT COUNT(*) as c FROM officers WHERE status = 'Active' AND active_points >= 8"
            ).fetchone()["c"]
        except Exception:
            pass
        try:
            month_start = datetime.now().strftime("%Y-%m-01")
            data["infractions_this_month"] = conn.execute(
                "SELECT COUNT(*) as c FROM ats_infractions WHERE date >= ?",
                (month_start,)
            ).fetchone()["c"]
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return data


def _api_officers() -> list:
    """Officer list with key fields."""
    officers = []
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT officer_id, name, site, active_points, status, discipline_level "
            "FROM officers WHERE status = 'Active' ORDER BY name"
        ).fetchall()
        officers = [dict(r) for r in rows]
        conn.close()
    except Exception:
        pass
    return officers


def _api_officer_detail(officer_id: str) -> dict | None:
    """Single officer with cross-module data."""
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM officers WHERE officer_id = ?", (officer_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        data = dict(row)

        # Recent infractions
        try:
            inf = conn.execute(
                "SELECT infraction_id, type, date, site, points, notes "
                "FROM ats_infractions WHERE officer_id = ? ORDER BY date DESC LIMIT 10",
                (officer_id,)
            ).fetchall()
            data["recent_infractions"] = [dict(r) for r in inf]
        except Exception:
            data["recent_infractions"] = []

        # Uniform issuances
        try:
            uni = conn.execute(
                "SELECT i.issuance_id, c.name as item_name, i.size, i.date_issued, i.status "
                "FROM uni_issuances i LEFT JOIN uni_catalog c ON i.item_id = c.item_id "
                "WHERE i.officer_id = ? ORDER BY i.date_issued DESC LIMIT 10",
                (officer_id,)
            ).fetchall()
            data["uniform_issuances"] = [dict(r) for r in uni]
        except Exception:
            data["uniform_issuances"] = []

        # Training progress
        try:
            trn = conn.execute(
                "SELECT p.progress_id, cr.title as course_title, p.completed, p.score "
                "FROM trn_progress p LEFT JOIN trn_courses cr ON p.course_id = cr.course_id "
                "WHERE p.officer_id = ? ORDER BY p.completed DESC LIMIT 10",
                (officer_id,)
            ).fetchall()
            data["training_progress"] = [dict(r) for r in trn]
        except Exception:
            data["training_progress"] = []

        conn.close()
        return data
    except Exception:
        return None


def _api_attendance_recent() -> list:
    """Last 20 infractions."""
    results = []
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT i.infraction_id, i.officer_id, o.name as officer_name, "
            "i.type, i.date, i.site, i.points, i.notes "
            "FROM ats_infractions i "
            "LEFT JOIN officers o ON i.officer_id = o.officer_id "
            "ORDER BY i.date DESC LIMIT 20"
        ).fetchall()
        results = [dict(r) for r in rows]
        conn.close()
    except Exception:
        pass
    return results


def _api_uniforms_low_stock() -> list:
    """Low stock items."""
    results = []
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT item_id, name, stock_qty, reorder_point "
            "FROM uni_catalog WHERE stock_qty <= reorder_point ORDER BY stock_qty ASC"
        ).fetchall()
        results = [dict(r) for r in rows]
        conn.close()
    except Exception:
        pass
    return results


def _api_alerts() -> list:
    """All active alerts."""
    try:
        from src.notifications import get_all_alerts
        return get_all_alerts()
    except Exception:
        return []


def _api_login(body: dict) -> tuple:
    """Authenticate and return token. Returns (response_dict, status_code)."""
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if not username or not password:
        return {"error": "Username and password required"}, 400

    user = auth.authenticate(username, password)
    if not user:
        return {"error": "Invalid credentials"}, 401

    token = secrets.token_hex(32)
    _tokens[token] = {
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
        "created": datetime.now(timezone.utc).isoformat(),
    }
    return {"token": token, "user": user}, 200


def _api_post_infraction(body: dict, user_info: dict) -> tuple:
    """Log a quick infraction. Returns (response_dict, status_code)."""
    officer_id = body.get("officer_id", "").strip()
    inf_type = body.get("type", "").strip()
    inf_date = body.get("date", datetime.now().strftime("%Y-%m-%d"))
    site = body.get("site", "").strip()
    notes = body.get("notes", "").strip()

    if not officer_id or not inf_type:
        return {"error": "officer_id and type are required"}, 400

    try:
        conn = get_conn()
        # Verify officer exists
        officer = conn.execute(
            "SELECT officer_id, name FROM officers WHERE officer_id = ?",
            (officer_id,)
        ).fetchone()
        if not officer:
            conn.close()
            return {"error": "Officer not found"}, 404

        inf_id = secrets.token_hex(12)

        # Determine points based on type (simplified)
        points_map = {
            "NCNS": 4, "Late": 1, "Early Leave": 1, "Missed Punch": 0.5,
            "Uniform Violation": 1, "Policy Violation": 2, "Other": 1,
        }
        points = points_map.get(inf_type, 1)

        conn.execute(
            "INSERT INTO ats_infractions (infraction_id, officer_id, type, date, site, points, notes, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (inf_id, officer_id, inf_type, inf_date, site, points, notes,
             user_info["username"], datetime.now(timezone.utc).isoformat())
        )

        # Update officer points
        conn.execute(
            "UPDATE officers SET active_points = active_points + ?, last_infraction_date = ? WHERE officer_id = ?",
            (points, inf_date, officer_id)
        )
        conn.commit()
        conn.close()

        return {"success": True, "infraction_id": inf_id, "points": points}, 201
    except Exception as e:
        return {"error": str(e)}, 500


# ── HTML Frontend ─────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Cerasus Hub — Mobile</title>
<style>
:root {
    --cerasus-red: #C8102E;
    --cerasus-navy: #1A1A2E;
    --cerasus-rose: #C37474;
    --bg: #F3F4F6;
    --card: #FFFFFF;
    --text: #1F2937;
    --text-light: #6B7280;
    --border: #E5E7EB;
    --success: #059669;
    --warning: #D97706;
    --danger: #C8102E;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', -apple-system, sans-serif; background: var(--bg); color: var(--text); -webkit-tap-highlight-color: transparent; }

/* Header */
.header { background: var(--cerasus-navy); padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
.header .brand { color: var(--cerasus-red); font-size: 22px; font-weight: 300; letter-spacing: 6px; }
.header .subtitle { color: var(--cerasus-rose); font-size: 10px; letter-spacing: 3px; margin-top: 2px; }
.header .status { color: #9CA3AF; font-size: 11px; }

/* Tab nav */
.tab-nav { display: flex; background: var(--card); border-bottom: 1px solid var(--border); position: sticky; top: 62px; z-index: 99; }
.tab-btn { flex: 1; padding: 14px 8px; text-align: center; font-size: 13px; font-weight: 600; color: var(--text-light); background: none; border: none; border-bottom: 3px solid transparent; cursor: pointer; min-height: 48px; }
.tab-btn.active { color: var(--cerasus-red); border-bottom-color: var(--cerasus-red); }

/* Content area */
.tab-content { display: none; padding: 16px; }
.tab-content.active { display: block; }

/* KPI cards */
.kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.kpi-card { background: var(--card); border-radius: 12px; padding: 16px; border-left: 4px solid var(--cerasus-red); }
.kpi-card .value { font-size: 28px; font-weight: 800; color: var(--cerasus-navy); }
.kpi-card .label { font-size: 11px; color: var(--text-light); letter-spacing: 1px; margin-top: 4px; }
.kpi-card.warn { border-left-color: var(--warning); }
.kpi-card.warn .value { color: var(--warning); }
.kpi-card.danger { border-left-color: var(--danger); }
.kpi-card.danger .value { color: var(--danger); }
.kpi-card.success { border-left-color: var(--success); }
.kpi-card.success .value { color: var(--success); }

/* Alert list */
.section-title { font-size: 14px; font-weight: 700; color: var(--cerasus-navy); letter-spacing: 1px; margin: 20px 0 10px; }
.alert-item { background: var(--card); border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; border-left: 4px solid var(--border); }
.alert-item.critical { border-left-color: var(--danger); }
.alert-item.warning { border-left-color: var(--warning); }
.alert-item.info { border-left-color: #3B82F6; }
.alert-item .alert-module { font-size: 10px; font-weight: 700; letter-spacing: 1px; color: var(--text-light); }
.alert-item .alert-title { font-size: 13px; font-weight: 600; margin-top: 2px; }
.alert-item .alert-detail { font-size: 12px; color: var(--text-light); margin-top: 2px; }

/* Officer list */
.search-box { width: 100%; padding: 12px 16px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; background: var(--card); margin-bottom: 12px; min-height: 44px; }
.officer-item { background: var(--card); border-radius: 8px; padding: 14px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
.officer-item:active { background: #F0F0F0; }
.officer-name { font-size: 14px; font-weight: 600; }
.officer-site { font-size: 12px; color: var(--text-light); margin-top: 2px; }
.officer-badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; color: white; min-width: 36px; text-align: center; }
.badge-green { background: var(--success); }
.badge-yellow { background: var(--warning); }
.badge-red { background: var(--danger); }
.officer-status { font-size: 11px; color: var(--text-light); margin-top: 2px; }

/* Detail overlay */
.overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 200; }
.overlay.active { display: block; }
.detail-panel { position: fixed; top: 0; right: 0; bottom: 0; width: 100%; max-width: 420px; background: var(--bg); z-index: 201; overflow-y: auto; padding: 20px; }
.detail-close { background: none; border: none; font-size: 24px; color: var(--text-light); cursor: pointer; padding: 8px; min-width: 44px; min-height: 44px; }
.detail-name { font-size: 20px; font-weight: 700; margin: 8px 0 4px; }
.detail-meta { font-size: 12px; color: var(--text-light); margin-bottom: 16px; }
.detail-section { font-size: 12px; font-weight: 700; letter-spacing: 1px; color: var(--cerasus-red); margin: 16px 0 8px; }
.detail-row { background: var(--card); border-radius: 6px; padding: 10px 12px; margin-bottom: 6px; font-size: 13px; }
.detail-row .label { color: var(--text-light); font-size: 11px; }

/* Quick actions */
.form-group { margin-bottom: 14px; }
.form-label { font-size: 12px; font-weight: 600; color: var(--text-light); letter-spacing: 1px; margin-bottom: 6px; display: block; }
.form-input, .form-select, .form-textarea { width: 100%; padding: 12px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; background: var(--card); min-height: 44px; font-family: inherit; }
.form-textarea { min-height: 80px; resize: vertical; }
.btn { display: block; width: 100%; padding: 14px; border: none; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; letter-spacing: 1px; min-height: 48px; }
.btn-primary { background: var(--cerasus-red); color: white; }
.btn-primary:active { background: #A80D25; }
.btn-outline { background: none; border: 2px solid var(--border); color: var(--text); margin-top: 8px; }
.login-prompt { text-align: center; padding: 40px 20px; }
.login-prompt p { color: var(--text-light); font-size: 14px; margin-bottom: 16px; }
.msg { padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-bottom: 12px; display: none; }
.msg.success { display: block; background: #D1FAE5; color: #065F46; }
.msg.error { display: block; background: #FDE8EB; color: #991B1B; }

/* Loading spinner */
.spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid var(--border); border-top-color: var(--cerasus-red); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.loading { text-align: center; padding: 40px; }
</style>
</head>
<body>

<div class="header">
    <div>
        <div class="brand">cerasus</div>
        <div class="subtitle">MOBILE COMPANION</div>
    </div>
    <div class="status" id="connStatus">Connecting...</div>
</div>

<div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('dashboard')">Dashboard</button>
    <button class="tab-btn" onclick="switchTab('officers')">Officers</button>
    <button class="tab-btn" onclick="switchTab('actions')">Quick Actions</button>
</div>

<!-- Dashboard Tab -->
<div class="tab-content active" id="tab-dashboard">
    <div class="kpi-grid" id="kpiGrid">
        <div class="loading"><div class="spinner"></div></div>
    </div>
    <div class="section-title">ACTIVE ALERTS</div>
    <div id="alertsList"><div class="loading"><div class="spinner"></div></div></div>
</div>

<!-- Officers Tab -->
<div class="tab-content" id="tab-officers">
    <input type="text" class="search-box" id="officerSearch" placeholder="Search officers..." oninput="filterOfficers()">
    <div id="officerList"><div class="loading"><div class="spinner"></div></div></div>
</div>

<!-- Quick Actions Tab -->
<div class="tab-content" id="tab-actions">
    <div id="loginSection" class="login-prompt">
        <p>Sign in to log infractions</p>
        <div class="form-group">
            <input type="text" class="form-input" id="loginUser" placeholder="Username">
        </div>
        <div class="form-group">
            <input type="password" class="form-input" id="loginPass" placeholder="Password">
        </div>
        <div id="loginMsg" class="msg"></div>
        <button class="btn btn-primary" onclick="doLogin()">Sign In</button>
    </div>
    <div id="actionSection" style="display:none;">
        <div class="section-title">LOG INFRACTION</div>
        <div id="actionMsg" class="msg"></div>
        <div class="form-group">
            <label class="form-label">OFFICER</label>
            <select class="form-select" id="infOfficer"></select>
        </div>
        <div class="form-group">
            <label class="form-label">TYPE</label>
            <select class="form-select" id="infType">
                <option value="NCNS">NCNS (No Call No Show)</option>
                <option value="Late">Late</option>
                <option value="Early Leave">Early Leave</option>
                <option value="Missed Punch">Missed Punch</option>
                <option value="Uniform Violation">Uniform Violation</option>
                <option value="Policy Violation">Policy Violation</option>
                <option value="Other">Other</option>
            </select>
        </div>
        <div class="form-group">
            <label class="form-label">DATE</label>
            <input type="date" class="form-input" id="infDate">
        </div>
        <div class="form-group">
            <label class="form-label">SITE</label>
            <input type="text" class="form-input" id="infSite" placeholder="Site name">
        </div>
        <div class="form-group">
            <label class="form-label">NOTES</label>
            <textarea class="form-textarea" id="infNotes" placeholder="Optional notes..."></textarea>
        </div>
        <button class="btn btn-primary" onclick="submitInfraction()">Log Infraction</button>
        <button class="btn btn-outline" onclick="doLogout()">Sign Out</button>
    </div>
</div>

<!-- Officer Detail Overlay -->
<div class="overlay" id="detailOverlay" onclick="closeDetail()"></div>
<div class="detail-panel" id="detailPanel" style="display:none;">
    <button class="detail-close" onclick="closeDetail()">&times;</button>
    <div id="detailContent"></div>
</div>

<script>
let authToken = null;
let allOfficers = [];

// Tab switching
function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach((b, i) => {
        b.classList.toggle('active', b.textContent.toLowerCase().includes(name.substring(0, 4)));
    });
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');

    if (name === 'dashboard') loadDashboard();
    else if (name === 'officers') loadOfficers();
}

// API helper
async function api(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
    try {
        const resp = await fetch(path, { ...opts, headers });
        return await resp.json();
    } catch (e) {
        console.error('API error:', e);
        return null;
    }
}

// Dashboard
async function loadDashboard() {
    const [kpis, alerts] = await Promise.all([api('/api/dashboard'), api('/api/alerts')]);

    if (kpis) {
        document.getElementById('kpiGrid').innerHTML = `
            <div class="kpi-card success"><div class="value">${kpis.active_officers}</div><div class="label">ACTIVE OFFICERS</div></div>
            <div class="kpi-card danger"><div class="value">${kpis.at_risk_officers}</div><div class="label">AT-RISK OFFICERS</div></div>
            <div class="kpi-card warn"><div class="value">${kpis.pending_reviews}</div><div class="label">PENDING REVIEWS</div></div>
            <div class="kpi-card"><div class="value">${kpis.low_stock}</div><div class="label">LOW STOCK ITEMS</div></div>
            <div class="kpi-card"><div class="value">${kpis.open_requests}</div><div class="label">OPEN REQUESTS</div></div>
            <div class="kpi-card warn"><div class="value">${kpis.infractions_this_month}</div><div class="label">INFRACTIONS (MONTH)</div></div>
        `;
        document.getElementById('connStatus').textContent = 'Connected';
    }

    if (alerts && alerts.length > 0) {
        document.getElementById('alertsList').innerHTML = alerts.map(a =>
            `<div class="alert-item ${a.severity}">
                <div class="alert-module">${a.module || ''}</div>
                <div class="alert-title">${a.title}</div>
                <div class="alert-detail">${a.detail || ''}</div>
            </div>`
        ).join('');
    } else {
        document.getElementById('alertsList').innerHTML = '<div style="color:#6B7280;font-size:13px;padding:20px;text-align:center;">No active alerts</div>';
    }
}

// Officers
async function loadOfficers() {
    const data = await api('/api/officers');
    if (data) {
        allOfficers = data;
        renderOfficers(data);
    }
}

function renderOfficers(list) {
    if (!list || list.length === 0) {
        document.getElementById('officerList').innerHTML = '<div style="color:#6B7280;font-size:13px;padding:20px;text-align:center;">No officers found</div>';
        return;
    }
    document.getElementById('officerList').innerHTML = list.map(o => {
        const pts = o.active_points || 0;
        const bc = pts >= 8 ? 'badge-red' : pts >= 4 ? 'badge-yellow' : 'badge-green';
        return `<div class="officer-item" onclick="showOfficerDetail('${o.officer_id}')">
            <div>
                <div class="officer-name">${o.name}</div>
                <div class="officer-site">${o.site || 'Unassigned'}</div>
                <div class="officer-status">${o.discipline_level || 'None'}</div>
            </div>
            <div>
                <span class="officer-badge ${bc}">${pts} pts</span>
            </div>
        </div>`;
    }).join('');
}

function filterOfficers() {
    const q = document.getElementById('officerSearch').value.toLowerCase();
    const filtered = allOfficers.filter(o =>
        (o.name || '').toLowerCase().includes(q) || (o.site || '').toLowerCase().includes(q)
    );
    renderOfficers(filtered);
}

// Officer detail
async function showOfficerDetail(id) {
    document.getElementById('detailOverlay').classList.add('active');
    document.getElementById('detailPanel').style.display = 'block';
    document.getElementById('detailContent').innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    const o = await api('/api/officer/' + id);
    if (!o) { closeDetail(); return; }

    let html = `<div class="detail-name">${o.name}</div>`;
    html += `<div class="detail-meta">${o.site || 'Unassigned'} &bull; ${o.status} &bull; ${o.active_points || 0} pts</div>`;
    html += `<div class="detail-row"><span class="label">Employee ID:</span> ${o.employee_id || 'N/A'}</div>`;
    html += `<div class="detail-row"><span class="label">Hire Date:</span> ${o.hire_date || 'N/A'}</div>`;
    html += `<div class="detail-row"><span class="label">Discipline Level:</span> ${o.discipline_level || 'None'}</div>`;
    html += `<div class="detail-row"><span class="label">Phone:</span> ${o.phone || 'N/A'}</div>`;

    if (o.recent_infractions && o.recent_infractions.length > 0) {
        html += `<div class="detail-section">RECENT INFRACTIONS</div>`;
        o.recent_infractions.forEach(i => {
            html += `<div class="detail-row"><strong>${i.type}</strong> &mdash; ${i.date || ''}<br><span class="label">${i.site || ''} &bull; ${i.points || 0} pts</span></div>`;
        });
    }

    if (o.uniform_issuances && o.uniform_issuances.length > 0) {
        html += `<div class="detail-section">UNIFORM ISSUANCES</div>`;
        o.uniform_issuances.forEach(u => {
            html += `<div class="detail-row">${u.item_name || 'Item'} &mdash; ${u.size || ''}<br><span class="label">${u.date_issued || ''} &bull; ${u.status || ''}</span></div>`;
        });
    }

    if (o.training_progress && o.training_progress.length > 0) {
        html += `<div class="detail-section">TRAINING</div>`;
        o.training_progress.forEach(t => {
            html += `<div class="detail-row">${t.course_title || 'Course'}<br><span class="label">${t.completed ? 'Completed' : 'In Progress'} &bull; Score: ${t.score || 'N/A'}</span></div>`;
        });
    }

    document.getElementById('detailContent').innerHTML = html;
}

function closeDetail() {
    document.getElementById('detailOverlay').classList.remove('active');
    document.getElementById('detailPanel').style.display = 'none';
}

// Login / Quick Actions
async function doLogin() {
    const user = document.getElementById('loginUser').value;
    const pass = document.getElementById('loginPass').value;
    const msg = document.getElementById('loginMsg');
    msg.className = 'msg'; msg.textContent = '';

    const resp = await api('/api/login', { method: 'POST', body: JSON.stringify({ username: user, password: pass }) });
    if (resp && resp.token) {
        authToken = resp.token;
        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('actionSection').style.display = 'block';
        populateOfficerDropdown();
    } else {
        msg.className = 'msg error';
        msg.textContent = (resp && resp.error) || 'Login failed';
    }
}

function doLogout() {
    authToken = null;
    document.getElementById('loginSection').style.display = 'block';
    document.getElementById('actionSection').style.display = 'none';
    document.getElementById('loginUser').value = '';
    document.getElementById('loginPass').value = '';
}

async function populateOfficerDropdown() {
    if (!allOfficers.length) await loadOfficers();
    const sel = document.getElementById('infOfficer');
    sel.innerHTML = '<option value="">Select officer...</option>' +
        allOfficers.map(o => `<option value="${o.officer_id}">${o.name} (${o.site || 'N/A'})</option>`).join('');

    // Set default date to today
    document.getElementById('infDate').value = new Date().toISOString().split('T')[0];
}

async function submitInfraction() {
    const msg = document.getElementById('actionMsg');
    msg.className = 'msg'; msg.textContent = '';

    const body = {
        officer_id: document.getElementById('infOfficer').value,
        type: document.getElementById('infType').value,
        date: document.getElementById('infDate').value,
        site: document.getElementById('infSite').value,
        notes: document.getElementById('infNotes').value,
    };
    if (!body.officer_id) { msg.className = 'msg error'; msg.textContent = 'Select an officer'; return; }

    const resp = await api('/api/infraction', { method: 'POST', body: JSON.stringify(body) });
    if (resp && resp.success) {
        msg.className = 'msg success';
        msg.textContent = 'Infraction logged (' + resp.points + ' pts)';
        document.getElementById('infNotes').value = '';
        document.getElementById('infSite').value = '';
    } else {
        msg.className = 'msg error';
        msg.textContent = (resp && resp.error) || 'Failed to log infraction';
    }
}

// Auto-refresh dashboard every 30s
setInterval(() => {
    const dash = document.getElementById('tab-dashboard');
    if (dash.classList.contains('active')) loadDashboard();
}, 30000);

// Initial load
loadDashboard();
</script>
</body>
</html>"""


# ── Request Handler ───────────────────────────────────────────────────

class CompanionHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the mobile companion."""

    def log_message(self, format, *args):
        """Suppress default logging to avoid console spam."""
        pass

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "" or path == "/":
            # Serve the HTML frontend
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/dashboard":
            _json_response(self, _api_dashboard())

        elif path == "/api/officers":
            _json_response(self, _api_officers())

        elif path.startswith("/api/officer/"):
            officer_id = path.split("/api/officer/")[1]
            data = _api_officer_detail(officer_id)
            if data:
                _json_response(self, data)
            else:
                _json_response(self, {"error": "Officer not found"}, 404)

        elif path == "/api/attendance/recent":
            _json_response(self, _api_attendance_recent())

        elif path == "/api/uniforms/low-stock":
            _json_response(self, _api_uniforms_low_stock())

        elif path == "/api/alerts":
            _json_response(self, _api_alerts())

        else:
            _json_response(self, {"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/login":
            body = _read_body(self)
            data, status = _api_login(body)
            _json_response(self, data, status)

        elif path == "/api/infraction":
            user_info = _check_auth(self)
            if not user_info:
                _json_response(self, {"error": "Authentication required"}, 401)
                return
            body = _read_body(self)
            data, status = _api_post_infraction(body, user_info)
            _json_response(self, data, status)

        else:
            _json_response(self, {"error": "Not found"}, 404)


# ── Server Lifecycle ──────────────────────────────────────────────────

def start_companion_server() -> threading.Thread:
    """Start the companion HTTP server in a daemon thread. Returns the thread."""
    global _server_instance

    local_ip = _get_local_ip()

    _server_instance = HTTPServer(("0.0.0.0", COMPANION_PORT), CompanionHandler)
    _server_instance.timeout = 1

    def _serve():
        print(f"[Web Companion] Mobile dashboard: http://{local_ip}:{COMPANION_PORT}")
        try:
            _server_instance.serve_forever()
        except Exception:
            pass

    thread = threading.Thread(target=_serve, name="WebCompanion", daemon=True)
    thread.start()
    return thread


def stop_companion_server():
    """Shut down the companion server gracefully."""
    global _server_instance
    if _server_instance:
        try:
            _server_instance.shutdown()
        except Exception:
            pass
        _server_instance = None


def get_companion_url() -> str:
    """Return the companion URL string for display."""
    return f"http://{_get_local_ip()}:{COMPANION_PORT}"
