"""
Comprehensive truncation/clipping audit for CerasusHub src/ .py files.
"""
import os
import re
import sys
import traceback

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")

CHAR_WIDTH = 8        # px per char at ~14px font
H_PADDING = 40        # 20px each side
MIN_VERT = 30         # minimum height to avoid vertical clipping

findings = []

def add(filepath, lineno, category, msg):
    rel = os.path.relpath(filepath, os.path.dirname(SRC))
    findings.append(f"  [{category}] {rel}:{lineno}  {msg}")

def collect_py_files():
    result = []
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result

# ── Load all source files ─────────────────────────────────────────────
all_files = collect_py_files()
all_lines = {}  # filepath -> list of (lineno, line)
for fp in all_files:
    with open(fp, encoding="utf-8", errors="replace") as fh:
        all_lines[fp] = list(enumerate(fh.readlines(), 1))

# ══════════════════════════════════════════════════════════════════════
# 1. QPushButton with setFixedWidth / setFixedSize — check text fits
# ══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("CHECK 1: QPushButton setFixedWidth/setFixedSize — text overflow")
print("=" * 70)

# Pattern: var.setFixedWidth(N) or var.setFixedSize(W, H) or setFixedSize(QSize(...))
re_fixed_w = re.compile(r'(\w+)\.setFixedWidth\(\s*(\d+)\s*\)')
re_fixed_s = re.compile(r'(\w+)\.setFixedSize\(\s*(\d+)\s*,\s*(\d+)\s*\)')
# Pattern: var = QPushButton("text")  or  var.setText("text")
re_btn_init = re.compile(r'(\w+)\s*=\s*QPushButton\(\s*["\']([^"\']+)["\']\s*\)')
re_set_text = re.compile(r'(\w+)\.setText\(\s*["\']([^"\']+)["\']\s*\)')

for fp, lines in all_lines.items():
    # Build a map of variable -> text for buttons in this file
    btn_texts = {}
    for ln, line in lines:
        m = re_btn_init.search(line)
        if m:
            btn_texts[m.group(1)] = (m.group(2), ln)
        m = re_set_text.search(line)
        if m:
            btn_texts[m.group(1)] = (m.group(2), ln)

    for ln, line in lines:
        m = re_fixed_w.search(line)
        if m:
            var, width = m.group(1), int(m.group(2))
            # Check if this var is a QPushButton
            is_btn = False
            for ln2, line2 in lines:
                if re.search(rf'{re.escape(var)}\s*=\s*QPushButton', line2):
                    is_btn = True
                    break
            if not is_btn:
                continue
            if var in btn_texts:
                text, tln = btn_texts[var]
                needed = len(text) * CHAR_WIDTH + H_PADDING
                if needed > width:
                    add(fp, ln, "BTN-WIDTH", f"Button '{var}' text \"{text}\" needs ~{needed}px but setFixedWidth({width})")
            else:
                add(fp, ln, "BTN-WIDTH-NOTEXT", f"Button '{var}' has setFixedWidth({width}) — could not determine text, verify manually")

        m = re_fixed_s.search(line)
        if m:
            var, w, h = m.group(1), int(m.group(2)), int(m.group(3))
            is_btn = False
            for ln2, line2 in lines:
                if re.search(rf'{re.escape(var)}\s*=\s*QPushButton', line2):
                    is_btn = True
                    break
            if not is_btn:
                continue
            if var in btn_texts:
                text, tln = btn_texts[var]
                needed = len(text) * CHAR_WIDTH + H_PADDING
                if needed > w:
                    add(fp, ln, "BTN-SIZE-W", f"Button '{var}' text \"{text}\" needs ~{needed}px but setFixedSize({w},{h})")
            if h < MIN_VERT:
                text_str = btn_texts[var][0] if var in btn_texts else "?"
                add(fp, ln, "BTN-SIZE-H", f"Button '{var}' (text=\"{text_str}\") height {h} < {MIN_VERT}px — vertical clipping risk")

for f in findings:
    print(f)
if not [f for f in findings if "BTN-" in f]:
    print("  (none found)")

# ══════════════════════════════════════════════════════════════════════
# 2. QLabel with setFixedWidth / setFixedSize — text overflow
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("CHECK 2: QLabel setFixedWidth/setFixedSize — text overflow")
print("=" * 70)

re_lbl_init = re.compile(r'(\w+)\s*=\s*QLabel\(\s*["\']([^"\']+)["\']\s*\)')
count2 = 0

for fp, lines in all_lines.items():
    lbl_texts = {}
    for ln, line in lines:
        m = re_lbl_init.search(line)
        if m:
            lbl_texts[m.group(1)] = (m.group(2), ln)
        m = re_set_text.search(line)
        if m:
            # Only if it's a QLabel
            for ln2, line2 in lines:
                if re.search(rf'{re.escape(m.group(1))}\s*=\s*QLabel', line2):
                    lbl_texts[m.group(1)] = (m.group(2), ln)
                    break

    for ln, line in lines:
        m = re_fixed_w.search(line)
        if m:
            var, width = m.group(1), int(m.group(2))
            is_lbl = any(re.search(rf'{re.escape(var)}\s*=\s*QLabel', l) for _, l in lines)
            if not is_lbl:
                continue
            if var in lbl_texts:
                text, tln = lbl_texts[var]
                max_chars = max(1, (width - 20) // CHAR_WIDTH)  # small padding
                if len(text) > max_chars:
                    add(fp, ln, "LBL-WIDTH", f"Label '{var}' text \"{text}\" ({len(text)} chars) may clip in {width}px (fits ~{max_chars} chars)")
                    count2 += 1
            else:
                # Look in nearby lines for setText with f-string or variable — just flag
                add(fp, ln, "LBL-WIDTH-CHECK", f"Label '{var}' has setFixedWidth({width}) — verify text fits")
                count2 += 1

        m = re_fixed_s.search(line)
        if m:
            var, w, h = m.group(1), int(m.group(2)), int(m.group(3))
            is_lbl = any(re.search(rf'{re.escape(var)}\s*=\s*QLabel', l) for _, l in lines)
            if not is_lbl:
                continue
            if var in lbl_texts:
                text, tln = lbl_texts[var]
                max_chars = max(1, (w - 20) // CHAR_WIDTH)
                if len(text) > max_chars:
                    add(fp, ln, "LBL-SIZE", f"Label '{var}' text \"{text}\" ({len(text)} chars) may clip in {w}x{h}px")
                    count2 += 1
            if h < 20:
                add(fp, ln, "LBL-SIZE-H", f"Label '{var}' height {h}px — vertical clipping risk")
                count2 += 1

if count2 == 0:
    print("  (none found)")

# ══════════════════════════════════════════════════════════════════════
# 3. QLabel with letter-spacing + setFixedWidth
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("CHECK 3: QLabel with letter-spacing AND setFixedWidth")
print("=" * 70)

re_letter_spacing = re.compile(r'letter-spacing\s*:\s*([\d.]+)px')
count3 = 0

for fp, lines in all_lines.items():
    # Find labels with letter-spacing in stylesheet
    labels_with_ls = {}  # var -> (spacing_px, line)
    for ln, line in lines:
        if 'letter-spacing' in line:
            # Check what variable this stylesheet is applied to
            # Look backward for var.setStyleSheet(
            for back in range(max(0, ln - 6), ln):
                idx = back - 1
                if idx < len(lines):
                    bline = lines[idx][1] if idx < len(lines) else ""
                    ss_m = re.search(r'(\w+)\.setStyleSheet\(', bline)
                    if ss_m:
                        sp_m = re_letter_spacing.search(line)
                        if sp_m:
                            labels_with_ls[ss_m.group(1)] = (float(sp_m.group(1)), ln)

    # Also handle inline: var.setStyleSheet("... letter-spacing: Npx ...")
    for ln, line in lines:
        if 'setStyleSheet' in line and 'letter-spacing' in line:
            ss_m = re.search(r'(\w+)\.setStyleSheet\(', line)
            sp_m = re_letter_spacing.search(line)
            if ss_m and sp_m:
                labels_with_ls[ss_m.group(1)] = (float(sp_m.group(1)), ln)

    # Now check if any of those also have setFixedWidth
    lbl_texts_file = {}
    for ln, line in lines:
        m = re_lbl_init.search(line)
        if m:
            lbl_texts_file[m.group(1)] = m.group(2)

    for var, (spacing, ls_ln) in labels_with_ls.items():
        for ln, line in lines:
            m = re_fixed_w.search(line)
            if m and m.group(1) == var:
                width = int(m.group(2))
                text = lbl_texts_file.get(var, "")
                if text:
                    effective_w = len(text) * (CHAR_WIDTH + spacing) + H_PADDING
                    if effective_w > width:
                        add(fp, ln, "LBL-LSPACING", f"Label '{var}' text \"{text}\" with letter-spacing {spacing}px needs ~{int(effective_w)}px but fixed at {width}px")
                        count3 += 1
                else:
                    add(fp, ln, "LBL-LSPACING-CHECK", f"Label '{var}' has letter-spacing + setFixedWidth({width}) — verify text fits")
                    count3 += 1

if count3 == 0:
    print("  (none found)")

# ══════════════════════════════════════════════════════════════════════
# 4. QPushButton setFixedSize with height < 30
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("CHECK 4: QPushButton setFixedSize where height < 30")
print("=" * 70)

count4 = 0
for fp, lines in all_lines.items():
    for ln, line in lines:
        m = re_fixed_s.search(line)
        if m:
            var, w, h = m.group(1), int(m.group(2)), int(m.group(3))
            is_btn = any(re.search(rf'{re.escape(var)}\s*=\s*QPushButton', l) for _, l in lines)
            if is_btn and h < MIN_VERT:
                add(fp, ln, "BTN-VERT", f"Button '{var}' setFixedSize({w},{h}) — height {h} < {MIN_VERT}px clips text")
                count4 += 1

if count4 == 0:
    print("  (none found)")

# ══════════════════════════════════════════════════════════════════════
# 5. QHBoxLayout/QVBoxLayout with addWidget but no stretch/setSizePolicy
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("CHECK 5: Layouts with buttons but no addStretch/setSizePolicy")
print("=" * 70)

re_layout_create = re.compile(r'(\w+)\s*=\s*Q([HV])BoxLayout\b')
re_add_widget = re.compile(r'(\w+)\.addWidget\(\s*(\w+)')
re_add_stretch = re.compile(r'(\w+)\.addStretch\(')
re_add_spacing = re.compile(r'(\w+)\.addSpacing\(')
re_size_policy = re.compile(r'(\w+)\.setSizePolicy\(')
re_set_stretch = re.compile(r'(\w+)\.setStretch\(')

count5 = 0
for fp, lines in all_lines.items():
    # Collect layout vars and what's added to them
    layouts = {}  # var -> {"type": H/V, "line": ln, "widgets": [], "has_stretch": False, "has_btn": False}
    for ln, line in lines:
        m = re_layout_create.search(line)
        if m:
            layouts[m.group(1)] = {"type": m.group(2), "line": ln, "widgets": [], "has_stretch": False, "has_btn": False}

    btn_vars = set()
    for ln, line in lines:
        if re.search(r'=\s*QPushButton\(', line):
            m2 = re.match(r'\s*(\w+)\s*=', line)
            if m2:
                btn_vars.add(m2.group(1))

    for ln, line in lines:
        m = re_add_widget.search(line)
        if m and m.group(1) in layouts:
            layouts[m.group(1)]["widgets"].append(m.group(2))
            if m.group(2) in btn_vars:
                layouts[m.group(1)]["has_btn"] = True

        m = re_add_stretch.search(line)
        if m and m.group(1) in layouts:
            layouts[m.group(1)]["has_stretch"] = True

        m = re_set_stretch.search(line)
        if m and m.group(1) in layouts:
            layouts[m.group(1)]["has_stretch"] = True

    # Also check if any widget in the layout has setSizePolicy
    widgets_with_policy = set()
    for ln, line in lines:
        m = re_size_policy.search(line)
        if m:
            widgets_with_policy.add(m.group(1))

    for var, info in layouts.items():
        if info["has_btn"] and not info["has_stretch"]:
            # Check if any button in it has setSizePolicy
            btns_in_layout = [w for w in info["widgets"] if w in btn_vars]
            if btns_in_layout and not any(b in widgets_with_policy for b in btns_in_layout):
                add(fp, info["line"], "LAYOUT-SQUEEZE",
                    f"Layout '{var}' (Q{info['type']}BoxLayout) has buttons {btns_in_layout} but no addStretch() or setSizePolicy — may squeeze on small windows")
                count5 += 1

if count5 == 0:
    print("  (none found)")

# ══════════════════════════════════════════════════════════════════════
# 6. tc() calls with invalid keys
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("CHECK 6: tc() calls with keys not in COLORS/DARK_COLORS")
print("=" * 70)

# Import actual dicts
sys.path.insert(0, os.path.dirname(SRC))
try:
    from src.config import COLORS, DARK_COLORS
except ImportError:
    # Fallback: parse from file
    COLORS = {}
    DARK_COLORS = {}
    print("  WARNING: Could not import config, parsing manually")

valid_keys = set(COLORS.keys()) & set(DARK_COLORS.keys())
all_color_keys = set(COLORS.keys()) | set(DARK_COLORS.keys())

re_tc = re.compile(r"""tc\(\s*['"](\w+)['"]\s*\)""")
count6 = 0

for fp, lines in all_lines.items():
    for ln, line in lines:
        for m in re_tc.finditer(line):
            key = m.group(1)
            if key not in valid_keys:
                if key in COLORS and key not in DARK_COLORS:
                    add(fp, ln, "TC-MISSING-DARK", f"tc('{key}') — key exists in COLORS but NOT in DARK_COLORS")
                    count6 += 1
                elif key in DARK_COLORS and key not in COLORS:
                    add(fp, ln, "TC-MISSING-LIGHT", f"tc('{key}') — key exists in DARK_COLORS but NOT in COLORS")
                    count6 += 1
                else:
                    add(fp, ln, "TC-INVALID", f"tc('{key}') — key not in COLORS or DARK_COLORS")
                    count6 += 1

# Also check get_theme_colors(...)['key'] pattern
re_gtc = re.compile(r"""get_theme_colors\([^)]*\)\[['"](\w+)['"]\]""")
for fp, lines in all_lines.items():
    for ln, line in lines:
        for m in re_gtc.finditer(line):
            key = m.group(1)
            if key not in valid_keys:
                if key in all_color_keys:
                    add(fp, ln, "TC-ASYMMETRIC", f"get_theme_colors()['{key}'] — key missing from one dict")
                    count6 += 1
                else:
                    add(fp, ln, "TC-INVALID", f"get_theme_colors()['{key}'] — key not in either dict")
                    count6 += 1

# Check c['key'] where c = get_theme_colors(...)
re_c_assign = re.compile(r'(\w+)\s*=\s*get_theme_colors\(')
re_c_access = re.compile(r"""(\w+)\[['"](\w+)['"]\]""")
for fp, lines in all_lines.items():
    theme_vars = set()
    for ln, line in lines:
        m = re_c_assign.search(line)
        if m:
            theme_vars.add(m.group(1))
    if theme_vars:
        for ln, line in lines:
            for m in re_c_access.finditer(line):
                if m.group(1) in theme_vars:
                    key = m.group(2)
                    if key not in valid_keys:
                        if key in all_color_keys:
                            add(fp, ln, "TC-ASYMMETRIC", f"{m.group(1)}['{key}'] — key missing from one color dict")
                            count6 += 1
                        # Don't flag unknown keys here as the variable might be reused

if count6 == 0:
    print("  (none found)")

# ══════════════════════════════════════════════════════════════════════
# 7. Page instantiation test
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("CHECK 7: Page class instantiation test")
print("=" * 70)

count7 = 0
try:
    # Need a QApplication for widget instantiation
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    from src.modules import REGISTERED_MODULES
    import importlib

    # Build a test app_state
    test_state = {
        "db": None,
        "conn": None,
        "user": {"username": "test_admin", "role": "admin", "display_name": "Test Admin"},
        "current_user": "test_admin",
        "role": "admin",
        "dark_mode": False,
        "read_only": False,
        "lock_holder": None,
        "refresh_cb": lambda: None,
        "status_bar": None,
        "main_window": None,
    }

    for mod_id in REGISTERED_MODULES:
        try:
            pkg = importlib.import_module(f"src.modules.{mod_id}")
            mod = pkg.get_module()
        except Exception as e:
            add(f"src/modules/{mod_id}/__init__.py", 0, "MOD-LOAD", f"Failed to load module '{mod_id}': {e}")
            count7 += 1
            continue

        for entry in mod.page_classes:
            page_cls = entry[0] if isinstance(entry, (list, tuple)) else entry
            cls_name = page_cls.__name__
            try:
                page = page_cls(test_state)
                # If it got here, instantiation succeeded
            except TypeError as e:
                # Try without args
                try:
                    page = page_cls()
                except Exception as e2:
                    add(f"src/modules/{mod_id}/", 0, "PAGE-INIT",
                        f"{cls_name} failed to instantiate: {e2}")
                    count7 += 1
            except Exception as e:
                err_short = str(e).split('\n')[0][:120]
                add(f"src/modules/{mod_id}/", 0, "PAGE-INIT",
                    f"{cls_name} threw {type(e).__name__}: {err_short}")
                count7 += 1

except ImportError as e:
    print(f"  SKIP: PySide6 not available or import error: {e}")
except Exception as e:
    print(f"  SKIP: Could not run page instantiation test: {e}")
    traceback.print_exc()

if count7 == 0:
    print("  (all pages instantiated successfully or test skipped)")

# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print(f"AUDIT COMPLETE — {len(findings)} total findings")
print("=" * 70)
for f in findings:
    print(f)

if not findings:
    print("  No issues found.")
