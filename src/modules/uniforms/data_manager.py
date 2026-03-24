"""
Cerasus Hub -- Uniforms Module: Data Manager
SQLite-backed CRUD for all uni_* tables.
Officers and sites are delegated to the shared data layer.
"""

import csv
import io
import json
import secrets
from datetime import datetime, timezone, timedelta

from src.database import get_conn
from src.shared_data import (
    get_all_officers,
    get_officer,
    get_active_officers,
    get_all_sites,
    get_site_names,
)

# ── Constants ───────────────────────────────────────────────────────

ITEM_CATEGORIES = [
    "Shirts", "Pants", "Outerwear", "Footwear", "Headwear",
    "Accessories", "Equipment", "Badges & Patches",
]

UNIFORM_SIZES = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL"]

STORAGE_LOCATIONS = ["Main Office", "Warehouse", "Field"]

JOB_TITLES = [
    "Security Officer",
    "Flex Security Officer",
    "Field Service Supervisor",
    "Security Director",
    "Account Manager",
]

# ── Helpers ─────────────────────────────────────────────────────────

def _gen_id() -> str:
    return secrets.token_hex(8)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_site_from_address(address: str) -> str:
    """Attempt to match an address string to a known site name."""
    if not address:
        return ""
    addr_lower = address.lower()
    sites = get_all_sites()
    for s in sites:
        site_addr = (s.get("address") or "").lower()
        site_name = (s.get("name") or "").lower()
        if site_addr and site_addr in addr_lower:
            return s.get("name", "")
        if site_name and site_name in addr_lower:
            return s.get("name", "")
    return ""


# ══════════════════════════════════════════════════════════════════════
# Catalog
# ══════════════════════════════════════════════════════════════════════

def get_all_catalog() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM uni_catalog ORDER BY item_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_catalog_item(item_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM uni_catalog WHERE item_id = ?", (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_catalog_item(data: dict, created_by: str = "system") -> str:
    item_id = _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO uni_catalog
           (item_id, item_name, category, description, unit_cost,
            reorder_point, status, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (item_id, data.get("item_name", ""), data.get("category", ""),
         data.get("description", ""), data.get("unit_cost", "0"),
         data.get("reorder_point", "5"), data.get("status", "Active"),
         created_by, now, now),
    )
    conn.commit()
    conn.close()
    return item_id


def delete_catalog_item(item_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM uni_catalog WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()


def seed_default_catalog():
    """Seed a minimal default catalog if empty."""
    if get_all_catalog():
        return
    defaults = [
        {"item_name": "Polo Shirt", "category": "Shirts", "unit_cost": "25.00"},
        {"item_name": "Dress Shirt", "category": "Shirts", "unit_cost": "30.00"},
        {"item_name": "Cargo Pants", "category": "Pants", "unit_cost": "35.00"},
        {"item_name": "Security Jacket", "category": "Outerwear", "unit_cost": "65.00"},
        {"item_name": "Baseball Cap", "category": "Headwear", "unit_cost": "12.00"},
        {"item_name": "Security Badge", "category": "Badges & Patches", "unit_cost": "8.00"},
        {"item_name": "Name Tag", "category": "Badges & Patches", "unit_cost": "5.00"},
        {"item_name": "Duty Belt", "category": "Equipment", "unit_cost": "40.00"},
    ]
    for item in defaults:
        create_catalog_item(item)


# ══════════════════════════════════════════════════════════════════════
# Item sizes / stock
# ══════════════════════════════════════════════════════════════════════

def get_item_sizes(item_id: str, location: str = "") -> list:
    conn = get_conn()
    if location:
        rows = conn.execute(
            "SELECT * FROM uni_item_sizes WHERE item_id = ? AND location = ?",
            (item_id, location)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM uni_item_sizes WHERE item_id = ?",
            (item_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_item_size_stock(item_id: str, size: str, qty: int, location: str = "Main Office"):
    now = _now()
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM uni_item_sizes WHERE item_id = ? AND size = ? AND location = ?",
        (item_id, size, location)).fetchone()
    if existing:
        conn.execute(
            "UPDATE uni_item_sizes SET stock_qty = ?, updated_at = ? WHERE id = ?",
            (qty, now, existing["id"]))
    else:
        conn.execute(
            """INSERT INTO uni_item_sizes (item_id, size, stock_qty, location, updated_at)
               VALUES (?,?,?,?,?)""",
            (item_id, size, qty, location, now))
    conn.commit()
    conn.close()


def get_low_stock_items() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.item_id, c.item_name, c.category, c.reorder_point,
               COALESCE(SUM(s.stock_qty), 0) as total_stock
        FROM uni_catalog c
        LEFT JOIN uni_item_sizes s ON c.item_id = s.item_id
        GROUP BY c.item_id
        HAVING total_stock <= CAST(c.reorder_point AS INTEGER)
        ORDER BY total_stock ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════
# Officers (delegated to shared data, with uniform-specific parsing)
# ══════════════════════════════════════════════════════════════════════

def get_all_officers_parsed() -> list:
    officers = get_all_officers()
    for o in officers:
        o["uniform_sizes"] = _parse_sizes(o.get("uniform_sizes", "{}"))
    return officers


def get_active_officers_parsed() -> list:
    officers = get_active_officers()
    for o in officers:
        o["uniform_sizes"] = _parse_sizes(o.get("uniform_sizes", "{}"))
    return officers


def _parse_sizes(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# ══════════════════════════════════════════════════════════════════════
# Sites
# ══════════════════════════════════════════════════════════════════════

def get_all_site_names() -> list:
    return get_site_names()


def get_all_managed_sites() -> list:
    return get_all_sites()


# ══════════════════════════════════════════════════════════════════════
# Issuances
# ══════════════════════════════════════════════════════════════════════

def create_issuance(data: dict, created_by: str = "system") -> str:
    issuance_id = _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO uni_issuances
           (issuance_id, officer_id, officer_name, item_id, item_name,
            size, quantity, condition_issued, date_issued,
            issued_by, notes, location, status, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (issuance_id, data.get("officer_id", ""), data.get("officer_name", ""),
         data.get("item_id", ""), data.get("item_name", ""),
         data.get("size", ""), data.get("quantity", "1"),
         data.get("condition_issued", "New"), data.get("date_issued", now[:10]),
         data.get("issued_by", created_by), data.get("notes", ""),
         data.get("location", ""), "Issued", created_by, now, now),
    )
    conn.commit()
    conn.close()
    _log_audit("issuance_created", f"Issued {data.get('item_name','')} to {data.get('officer_name','')}", created_by)
    return issuance_id


def get_all_issuances() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM uni_issuances ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_outstanding_issuances() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM uni_issuances WHERE status = 'Issued' ORDER BY date_issued DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def process_return(issuance_id: str, condition: str, notes: str, updated_by: str = "system") -> bool:
    conn = get_conn()
    row = conn.execute("SELECT * FROM uni_issuances WHERE issuance_id = ? AND status = 'Issued'",
                       (issuance_id,)).fetchone()
    if not row:
        conn.close()
        return False
    now = _now()
    conn.execute(
        """UPDATE uni_issuances
           SET status = 'Returned', return_condition = ?, return_notes = ?,
               return_date = ?, updated_by = ?, updated_at = ?
           WHERE issuance_id = ?""",
        (condition, notes, now[:10], updated_by, now, issuance_id),
    )
    conn.commit()
    conn.close()
    _log_audit("return_processed", f"Return of issuance {issuance_id}", updated_by)
    return True


# ══════════════════════════════════════════════════════════════════════
# Pending Orders
# ══════════════════════════════════════════════════════════════════════

def get_all_pending_orders() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM uni_pending_orders WHERE status = 'Pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_order_count() -> int:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM uni_pending_orders WHERE status = 'Pending'").fetchone()
    conn.close()
    return row["cnt"] if row else 0


def fulfill_pending_order(order_id: str, fulfilled_by: str = "system"):
    conn = get_conn()
    order = conn.execute("SELECT * FROM uni_pending_orders WHERE order_id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return
    now = _now()
    conn.execute(
        "UPDATE uni_pending_orders SET status = 'Fulfilled', fulfilled_by = ?, fulfilled_at = ?, updated_at = ? WHERE order_id = ?",
        (fulfilled_by, now, now, order_id),
    )
    conn.commit()
    conn.close()
    # Create the issuance record
    order = dict(order)
    create_issuance({
        "officer_id": order.get("officer_id", ""),
        "officer_name": order.get("officer_name", ""),
        "item_id": order.get("item_id", ""),
        "item_name": order.get("item_name", ""),
        "size": order.get("size", ""),
        "quantity": order.get("quantity", "1"),
        "condition_issued": "New",
        "date_issued": now[:10],
        "issued_by": fulfilled_by,
    }, created_by=fulfilled_by)


def cancel_pending_order(order_id: str):
    conn = get_conn()
    now = _now()
    conn.execute(
        "UPDATE uni_pending_orders SET status = 'Cancelled', updated_at = ? WHERE order_id = ?",
        (now, order_id),
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════
# Kits
# ══════════════════════════════════════════════════════════════════════

def get_all_kits() -> list:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM uni_kits ORDER BY kit_name").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


# ══════════════════════════════════════════════════════════════════════
# Requirements
# ══════════════════════════════════════════════════════════════════════

def get_requirements() -> list:
    return get_all_requirements()


def get_all_requirements() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM uni_requirements ORDER BY job_title, item_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_requirement(data: dict) -> str:
    req_id = _gen_id()
    now = _now()
    conn = get_conn()
    conn.execute(
        """INSERT INTO uni_requirements
           (req_id, job_title, item_id, item_name, qty_required, created_at)
           VALUES (?,?,?,?,?,?)""",
        (req_id, data.get("job_title", ""), data.get("item_id", ""),
         data.get("item_name", ""), data.get("qty_required", "1"), now),
    )
    conn.commit()
    conn.close()
    return req_id


def delete_requirement(req_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM uni_requirements WHERE req_id = ?", (req_id,))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════
# Dashboard & Analytics
# ══════════════════════════════════════════════════════════════════════

def get_dashboard_summary(site_filter: str = "") -> dict:
    return get_dashboard_summary_filtered(site_filter)


def get_dashboard_summary_filtered(site_filter: str = "") -> dict:
    conn = get_conn()
    where = ""
    params = ()
    if site_filter and site_filter != "All Sites":
        where = "WHERE i.location = ?"
        params = (site_filter,)

    total_issued = conn.execute(
        f"SELECT COUNT(*) as cnt FROM uni_issuances i {where}", params
    ).fetchone()["cnt"]

    outstanding = conn.execute(
        f"SELECT COUNT(*) as cnt FROM uni_issuances i {where.replace('WHERE', 'WHERE i.status = \\'Issued\\' AND') if where else 'WHERE i.status = \\'Issued\\''}",
        params,
    ).fetchone()["cnt"] if False else 0

    # Simpler outstanding count
    if where:
        outstanding = conn.execute(
            "SELECT COUNT(*) as cnt FROM uni_issuances i WHERE i.status = 'Issued' AND i.location = ?",
            params,
        ).fetchone()["cnt"]
    else:
        outstanding = conn.execute(
            "SELECT COUNT(*) as cnt FROM uni_issuances i WHERE i.status = 'Issued'"
        ).fetchone()["cnt"]

    catalog_count = conn.execute("SELECT COUNT(*) as cnt FROM uni_catalog").fetchone()["cnt"]
    pending = get_pending_order_count()

    conn.close()
    return {
        "total_issued": total_issued,
        "outstanding": outstanding,
        "catalog_items": catalog_count,
        "pending_orders": pending,
    }


def get_cost_analytics(site_filter: str = "") -> dict:
    conn = get_conn()
    # Total cost of issued items
    rows = conn.execute("""
        SELECT i.item_name, i.quantity, COALESCE(c.unit_cost, 0) as unit_cost,
               i.officer_name, i.location, i.date_issued
        FROM uni_issuances i
        LEFT JOIN uni_catalog c ON i.item_id = c.item_id
        ORDER BY i.date_issued DESC
    """).fetchall()
    conn.close()

    total_cost = 0
    by_category = {}
    by_officer = {}
    by_site = {}
    monthly = {}

    for r in rows:
        r = dict(r)
        qty = int(r.get("quantity", 1) or 1)
        cost = float(r.get("unit_cost", 0) or 0) * qty
        total_cost += cost

        officer = r.get("officer_name", "Unknown")
        by_officer[officer] = by_officer.get(officer, 0) + cost

        site = r.get("location", "Unknown") or "Unknown"
        by_site[site] = by_site.get(site, 0) + cost

        date = r.get("date_issued", "")[:7]  # YYYY-MM
        if date:
            monthly[date] = monthly.get(date, 0) + cost

    return {
        "total_cost": round(total_cost, 2),
        "by_officer": by_officer,
        "by_site": by_site,
        "monthly_trends": monthly,
    }


def get_compliance_report(site_filter: str = "") -> list:
    """Check each active officer's uniform compliance against requirements."""
    officers = get_active_officers_parsed()
    requirements = get_all_requirements()
    if not requirements:
        return []

    conn = get_conn()
    report = []
    for officer in officers:
        oid = officer.get("officer_id", "")
        name = officer.get("name", "")
        job_title = officer.get("job_title", "Security Officer")

        # Get officer's current issuances
        issued = conn.execute(
            "SELECT item_name, SUM(quantity) as qty FROM uni_issuances WHERE officer_id = ? AND status = 'Issued' GROUP BY item_name",
            (oid,),
        ).fetchall()
        issued_map = {r["item_name"]: int(r["qty"]) for r in issued}

        # Check against requirements for their job title
        officer_reqs = [r for r in requirements if r.get("job_title", "") == job_title]
        missing = []
        for req in officer_reqs:
            needed = int(req.get("qty_required", 1))
            have = issued_map.get(req.get("item_name", ""), 0)
            if have < needed:
                missing.append({
                    "item_name": req.get("item_name", ""),
                    "needed": needed,
                    "have": have,
                    "short": needed - have,
                })

        status = "Compliant" if not missing else "Non-Compliant"
        report.append({
            "officer_id": oid,
            "name": name,
            "job_title": job_title,
            "status": status,
            "missing": missing,
        })
    conn.close()
    return report


def get_compliance_summary(site_filter: str = "") -> dict:
    report = get_compliance_report(site_filter)
    total = len(report)
    compliant = sum(1 for r in report if r["status"] == "Compliant")
    return {
        "total": total,
        "compliant": compliant,
        "non_compliant": total - compliant,
        "rate": round((compliant / total * 100) if total else 0, 1),
    }


def get_replacement_schedule(days: int = 90, site_filter: str = "All Sites") -> list:
    """Items issued more than `days` ago that may need replacement."""
    conn = get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT * FROM uni_issuances
        WHERE status = 'Issued' AND date_issued <= ?
        ORDER BY date_issued ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_location_inventory_summary() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT location, SUM(stock_qty) as total_qty, COUNT(DISTINCT item_id) as item_count
        FROM uni_item_sizes
        GROUP BY location
        ORDER BY location
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_issuance_trends() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT SUBSTR(date_issued, 1, 7) as month, COUNT(*) as count
        FROM uni_issuances
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cost_breakdown_by_category() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.category, SUM(CAST(i.quantity AS INTEGER) * CAST(c.unit_cost AS REAL)) as total_cost
        FROM uni_issuances i
        JOIN uni_catalog c ON i.item_id = c.item_id
        GROUP BY c.category
        ORDER BY total_cost DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cost_breakdown_by_officer() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.officer_name, SUM(CAST(i.quantity AS INTEGER) * CAST(c.unit_cost AS REAL)) as total_cost
        FROM uni_issuances i
        JOIN uni_catalog c ON i.item_id = c.item_id
        GROUP BY i.officer_name
        ORDER BY total_cost DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cost_breakdown_by_site() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.location as site, SUM(CAST(i.quantity AS INTEGER) * CAST(c.unit_cost AS REAL)) as total_cost
        FROM uni_issuances i
        JOIN uni_catalog c ON i.item_id = c.item_id
        GROUP BY i.location
        ORDER BY total_cost DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_location_comparison() -> list:
    return get_location_inventory_summary()


# ══════════════════════════════════════════════════════════════════════
# Settings
# ══════════════════════════════════════════════════════════════════════

def save_setting(key: str, value: str):
    from src.config import save_setting as _save
    _save(f"uni_{key}", value)


# ══════════════════════════════════════════════════════════════════════
# Audit Log
# ══════════════════════════════════════════════════════════════════════

def _log_audit(event_type: str, details: str, username: str = "system"):
    try:
        from src.audit import log_event
        log_event("uniforms", event_type, username=username, details=details)
    except Exception:
        pass


def get_audit_log_entries(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE module_name = 'uniforms' ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════
# CSV Export
# ══════════════════════════════════════════════════════════════════════

def export_collection_csv(collection: str) -> str:
    if collection == "catalog":
        data = get_all_catalog()
    elif collection == "issuances":
        data = get_all_issuances()
    else:
        return ""
    if not data:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def export_compliance_csv() -> str:
    report = get_compliance_report()
    if not report:
        return ""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Officer", "Job Title", "Status", "Missing Items"])
    for r in report:
        missing_str = "; ".join(
            f"{m['item_name']} (need {m['needed']}, have {m['have']})" for m in r.get("missing", [])
        )
        writer.writerow([r["name"], r["job_title"], r["status"], missing_str])
    return output.getvalue()


def export_outstanding_csv() -> str:
    data = get_outstanding_issuances()
    if not data:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()
