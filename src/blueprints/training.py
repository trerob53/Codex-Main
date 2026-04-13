"""
Cerasus Hub — Training Module Blueprint
Web routes for the training / e-learning module.
"""

import json

from flask import (
    Blueprint, render_template, request, session, redirect, url_for, flash, jsonify,
)

from src.web_middleware import login_required, role_required
from src.modules.training import data_manager as dm

trn_bp = Blueprint("training", __name__, url_prefix="/module/training")

MODULE_ID = "training"
MODULE_COLOR = "#059669"
MODULE_BG = "#D1FAE5"

SIDEBAR = [
    ("LEARNING", [
        ("Dashboard", "training.dashboard"),
        ("My Courses", "training.my_courses"),
        ("Leaderboard", "training.leaderboard"),
        ("Certificates", "training.certificates"),
        ("My Profile", "training.profile"),
    ]),
    ("ADMIN", [
        ("Manage Courses", "training.manage_courses"),
        ("Manage Simulations", "training.manage_simulations"),
        ("Reports", "training.reports"),
    ]),
]


def _ctx(active_tab, **extra):
    """Common template context for all training pages."""
    breadcrumb = [
        {"label": "Training", "url": url_for("training.dashboard")},
    ]
    if active_tab and active_tab != "Dashboard":
        breadcrumb.append({"label": active_tab, "url": ""})
    ctx = dict(
        active_module=MODULE_ID,
        module_color=MODULE_COLOR,
        module_bg=MODULE_BG,
        sidebar_sections=SIDEBAR,
        active_tab=active_tab,
        breadcrumb_items=breadcrumb,
    )
    ctx.update(extra)
    return ctx


def _current_officer_id():
    """Resolve the current user's officer_id from session."""
    return session.get("officer_id", session.get("user_id", ""))


# ── LEARNING ─────────────────────────────────────────────────────────

@trn_bp.route("/")
def training_root():
    return redirect(url_for("training.dashboard"))


@trn_bp.route("/dashboard")
@login_required
def dashboard():
    officer_id = _current_officer_id()
    summary = dm.get_dashboard_summary(officer_id)
    role = session.get("role", "")
    user_sites = session.get("assigned_sites", [])
    courses = dm.get_courses_for_user(role, user_sites) if role != "admin" else dm.get_all_courses()
    # Attach progress per course
    for c in courses:
        c["progress"] = dm.get_course_completion_pct(officer_id, c["course_id"])
    # Recent test attempts
    recent_attempts = dm.get_attempts_for_officer(officer_id) if officer_id else []
    stats = {
        "courses_available": len(courses),
        "courses_completed": sum(1 for c in courses if c.get("progress", 0) >= 100),
        "certificates": len(dm.get_certificates_for_officer(officer_id)) if officer_id else 0,
        "test_attempts": len(recent_attempts),
    }
    return render_template(
        "training/dashboard.html",
        **_ctx("dashboard", stats=stats, courses=courses,
               recent_attempts=recent_attempts, officer_id=officer_id),
    )


@trn_bp.route("/courses")
@login_required
def my_courses():
    officer_id = _current_officer_id()
    role = session.get("role", "")
    user_sites = session.get("assigned_sites", [])
    courses = dm.get_courses_for_user(role, user_sites) if role != "admin" else dm.get_all_courses()
    # Attach completion % per course for the current officer
    for course in courses:
        course["completion_pct"] = dm.get_course_completion_pct(officer_id, course["course_id"])
    categories = list(set(c.get("category", "") for c in courses if c.get("category")))
    return render_template(
        "training/my_courses.html",
        **_ctx("courses", courses=courses, categories=sorted(categories), officer_id=officer_id),
    )


@trn_bp.route("/leaderboard")
@login_required
def leaderboard():
    site_filter = request.args.get("site", "")
    sites = dm.get_site_names()
    board = dm.get_leaderboard(site_filter)
    return render_template(
        "training/leaderboard.html",
        **_ctx("leaderboard", board=board, sites=sites, site_filter=site_filter),
    )


@trn_bp.route("/simulations")
@login_required
def simulations():
    sims = dm.get_published_simulations()
    is_admin = session.get("role") == "admin"
    if is_admin:
        sims = dm.get_all_simulations()
    return render_template(
        "training/simulations.html",
        **_ctx("simulations", simulations=sims, is_admin=is_admin),
    )


@trn_bp.route("/simulations/manage", methods=["GET", "POST"])
@login_required
def manage_simulations():
    """Admin: create/edit/delete simulations."""
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            dm.create_simulation({
                "title": request.form.get("title", ""),
                "description": request.form.get("description", ""),
                "category": request.form.get("category", "General"),
                "duration": request.form.get("duration", ""),
                "status": request.form.get("status", "Draft"),
                "created_by": session.get("username", ""),
            })
            flash("Simulation created.", "success")
        elif action == "delete":
            dm.delete_simulation(request.form.get("sim_id", ""))
            flash("Simulation deleted.", "warning")
        return redirect(url_for("training.manage_simulations"))

    sims = dm.get_all_simulations()
    return render_template(
        "training/manage_simulations.html",
        **_ctx("manage", simulations=sims),
    )


@trn_bp.route("/simulations/<sim_id>/build", methods=["GET", "POST"])
@login_required
def simulation_builder(sim_id):
    """Admin: build scenarios for a simulation."""
    sim = dm.get_simulation(sim_id)
    if not sim:
        flash("Simulation not found.", "error")
        return redirect(url_for("training.manage_simulations"))

    if request.method == "POST":
        # Parse scenarios from form
        scenarios = []
        s_idx = 0
        while request.form.get(f"s_{s_idx}_situation"):
            situation = request.form.get(f"s_{s_idx}_situation", "")
            options = []
            o_idx = 0
            while request.form.get(f"s_{s_idx}_opt_{o_idx}"):
                options.append({
                    "text": request.form.get(f"s_{s_idx}_opt_{o_idx}", ""),
                    "points": int(request.form.get(f"s_{s_idx}_pts_{o_idx}", 0)),
                    "feedback": request.form.get(f"s_{s_idx}_fb_{o_idx}", ""),
                })
                o_idx += 1
            scenarios.append({"situation": situation, "options": options})
            s_idx += 1

        dm.update_simulation(sim_id, {
            "title": request.form.get("title", sim["title"]),
            "description": request.form.get("description", ""),
            "category": request.form.get("category", "General"),
            "duration": request.form.get("duration", ""),
            "status": request.form.get("status", "Draft"),
            "scenarios": scenarios,
        })
        flash("Simulation saved.", "success")
        return redirect(url_for("training.simulation_builder", sim_id=sim_id))

    return render_template(
        "training/simulation_builder.html",
        **_ctx("manage", simulation=sim),
    )


@trn_bp.route("/simulations/<sim_id>/play", methods=["GET", "POST"])
@login_required
def play_simulation(sim_id):
    """Play through a simulation."""
    sim = dm.get_simulation(sim_id)
    if not sim or sim["status"] != "Published":
        flash("Simulation not available.", "error")
        return redirect(url_for("training.simulations"))

    officer_id = _current_officer_id()

    if request.method == "POST":
        # Score the simulation
        scenarios = sim.get("scenarios", [])
        total_points = 0
        max_points = 0
        responses = []
        for i, sc in enumerate(scenarios):
            selected = int(request.form.get(f"s_{i}", 0))
            opts = sc.get("options", [])
            best = max((o.get("points", 0) for o in opts), default=0)
            max_points += best
            chosen = opts[selected] if selected < len(opts) else {}
            pts = chosen.get("points", 0)
            total_points += pts
            responses.append({
                "scenario_index": i,
                "selected": selected,
                "points": pts,
                "feedback": chosen.get("feedback", ""),
            })

        score = round((total_points / max_points) * 100, 1) if max_points > 0 else 0
        passed = score >= 70

        dm.create_sim_attempt({
            "officer_id": officer_id,
            "sim_id": sim_id,
            "score": score,
            "passed": 1 if passed else 0,
            "responses": responses,
        })

        return render_template(
            "training/simulation_result.html",
            **_ctx("simulations", simulation=sim, score=score, passed=passed,
                   responses=responses, total_points=total_points, max_points=max_points),
        )

    return render_template(
        "training/simulation_play.html",
        **_ctx("simulations", simulation=sim),
    )


@trn_bp.route("/certificates")
@login_required
def certificates():
    certs = dm.get_all_certificates()
    return render_template(
        "training/certificates.html",
        **_ctx("certificates", certificates=certs),
    )


@trn_bp.route("/profile")
@login_required
def profile():
    officer_id = _current_officer_id()
    summary = dm.get_dashboard_summary(officer_id)
    my_certs = dm.get_certificates_for_officer(officer_id)
    my_attempts = dm.get_attempts_for_officer(officer_id)
    courses = dm.get_all_courses()
    course_progress = []
    for course in courses:
        pct = dm.get_course_completion_pct(officer_id, course["course_id"])
        course_progress.append({
            "course_id": course["course_id"],
            "title": course["title"],
            "category": course.get("category", ""),
            "completion_pct": pct,
        })

    # Get officer info for profile display
    from src.shared_data import get_officer
    officer_info = get_officer(officer_id)

    return render_template(
        "training/profile.html",
        **_ctx("profile", summary=summary, certificates=my_certs,
               attempts=my_attempts, course_progress=course_progress,
               officer_id=officer_id, officer_info=officer_info),
    )


# ── COURSE DETAIL & CONTENT ──────────────────────────────────────────

@trn_bp.route("/course/<course_id>")
@login_required
def course_detail(course_id):
    """Course overview page with chapter listing."""
    officer_id = _current_officer_id()
    course = dm.get_course(course_id)
    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("training.my_courses"))
    modules = dm.get_modules_for_course(course_id)
    chapters = dm.get_chapters_for_course(course_id)
    progress = dm.get_course_progress(officer_id, course_id)

    # Group chapters by module
    module_chapters = {}
    orphan_chapters = []
    for ch in chapters:
        mid = ch.get("module_id", "")
        if mid:
            module_chapters.setdefault(mid, []).append(ch)
        else:
            orphan_chapters.append(ch)

    # Mark which chapters the officer has completed
    completed_ids = set()
    from src.database import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT chapter_id FROM trn_progress WHERE officer_id = ? AND course_id = ? AND completed = 1",
        (officer_id, course_id),
    ).fetchall()
    conn.close()
    completed_ids = {r["chapter_id"] for r in rows}

    return render_template(
        "training/course_detail.html",
        **_ctx("courses", course=course, modules=modules, chapters=chapters,
               module_chapters=module_chapters, orphan_chapters=orphan_chapters,
               progress=progress, completed_ids=completed_ids, officer_id=officer_id),
    )


@trn_bp.route("/course/<course_id>/chapter/<chapter_id>")
@login_required
def chapter_view(course_id, chapter_id):
    """View a single chapter's content."""
    officer_id = _current_officer_id()
    course = dm.get_course(course_id)
    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("training.my_courses"))

    chapters = dm.get_chapters_for_course(course_id)
    current_chapter = None
    chapter_idx = 0
    for i, ch in enumerate(chapters):
        if ch["chapter_id"] == chapter_id:
            current_chapter = ch
            chapter_idx = i
            break

    if not current_chapter:
        flash("Chapter not found.", "error")
        return redirect(url_for("training.course_detail", course_id=course_id))

    # Check completion for current chapter + all chapters (for sidebar)
    from src.database import get_conn
    conn = get_conn()
    row = conn.execute(
        "SELECT completed FROM trn_progress WHERE officer_id = ? AND course_id = ? AND chapter_id = ?",
        (officer_id, course_id, chapter_id),
    ).fetchone()
    all_completed = conn.execute(
        "SELECT chapter_id FROM trn_progress WHERE officer_id = ? AND course_id = ? AND completed = 1",
        (officer_id, course_id),
    ).fetchall()
    conn.close()
    is_completed = bool(row and row["completed"])
    completed_ids = {r["chapter_id"] for r in all_completed}

    # Modules for sidebar grouping
    modules = dm.get_modules_for_course(course_id)

    # Check for test
    test = dm.get_test_for_chapter(chapter_id)
    best_attempt = None
    if test:
        best_attempt = dm.get_best_attempt(officer_id, test["test_id"])

    # Nav links
    prev_ch = chapters[chapter_idx - 1] if chapter_idx > 0 else None
    next_ch = chapters[chapter_idx + 1] if chapter_idx < len(chapters) - 1 else None

    return render_template(
        "training/chapter_view.html",
        **_ctx("courses", course=course, chapter=current_chapter,
               chapters=chapters, chapter_idx=chapter_idx, modules=modules,
               is_completed=is_completed, completed_ids=completed_ids,
               test=test, best_attempt=best_attempt,
               prev_chapter=prev_ch, next_chapter=next_ch, officer_id=officer_id),
    )


@trn_bp.route("/course/<course_id>/chapter/<chapter_id>/complete", methods=["POST"])
@login_required
def mark_complete(course_id, chapter_id):
    """Mark a chapter as complete."""
    officer_id = _current_officer_id()
    dm.mark_chapter_complete(officer_id, course_id, chapter_id)
    flash("Chapter marked as complete!", "success")
    return redirect(url_for("training.chapter_view", course_id=course_id, chapter_id=chapter_id))


@trn_bp.route("/course/<course_id>/chapter/<chapter_id>/quiz", methods=["GET", "POST"])
@login_required
def take_quiz(course_id, chapter_id):
    """Take a quiz for a chapter."""
    officer_id = _current_officer_id()
    course = dm.get_course(course_id)
    test = dm.get_test_for_chapter(chapter_id)
    chapter = None
    for ch in dm.get_chapters_for_course(course_id):
        if ch["chapter_id"] == chapter_id:
            chapter = ch
            break

    if not test or not course or not chapter:
        flash("Quiz not found.", "error")
        return redirect(url_for("training.course_detail", course_id=course_id))

    if request.method == "POST":
        # Score the quiz
        questions = test.get("questions", [])
        correct = 0
        answers = []
        for i, q in enumerate(questions):
            selected = request.form.get(f"q_{i}", "")
            is_correct = selected == str(q.get("correct", q.get("answer", "")))
            if is_correct:
                correct += 1
            answers.append({"question_index": i, "selected": selected, "correct": is_correct})

        score = round((correct / len(questions)) * 100, 1) if questions else 0
        passing = test.get("passing_score", 70)
        passed = score >= passing

        dm.create_attempt({
            "officer_id": officer_id,
            "test_id": test["test_id"],
            "course_id": course_id,
            "score": score,
            "passed": 1 if passed else 0,
            "answers": answers,
        })

        if passed:
            dm.mark_chapter_complete(officer_id, course_id, chapter_id)
            # Check if all tests passed for certificate
            if dm.all_course_tests_passed(officer_id, course_id):
                existing = dm.get_certificates_for_officer(officer_id)
                already_has = any(c.get("course_id") == course_id for c in existing)
                if not already_has:
                    dm.issue_certificate(officer_id, course_id, points=100)
                    flash("🎉 Congratulations! You earned a certificate for completing this course!", "success")

        return render_template(
            "training/quiz_result.html",
            **_ctx("courses", course=course, chapter=chapter, test=test,
                   score=score, passed=passed, passing=passing, correct=correct,
                   total=len(questions), answers=answers, questions=questions,
                   officer_id=officer_id),
        )

    return render_template(
        "training/quiz_take.html",
        **_ctx("courses", course=course, chapter=chapter, test=test, officer_id=officer_id),
    )


# ── ADMIN ────────────────────────────────────────────────────────────

@trn_bp.route("/manage", methods=["GET", "POST"])
@login_required
def manage_courses():
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            assigned_roles = request.form.getlist("assigned_roles")
            assigned_sites = request.form.getlist("assigned_sites")
            fields = {
                "title": request.form.get("title", ""),
                "description": request.form.get("description", ""),
                "category": request.form.get("category", "General Training"),
                "status": request.form.get("status", "Draft"),
                "created_by": session.get("username", ""),
                "assigned_roles": json.dumps(assigned_roles) if assigned_roles else "",
                "assigned_sites": json.dumps(assigned_sites) if assigned_sites else "",
            }
            dm.create_course(fields)
            flash("Course created successfully.", "success")
        elif action == "update":
            course_id = request.form.get("course_id", "")
            assigned_roles = request.form.getlist("assigned_roles")
            assigned_sites = request.form.getlist("assigned_sites")
            fields = {
                "title": request.form.get("title", ""),
                "description": request.form.get("description", ""),
                "category": request.form.get("category", ""),
                "status": request.form.get("status", ""),
                "assigned_roles": json.dumps(assigned_roles) if assigned_roles else "",
                "assigned_sites": json.dumps(assigned_sites) if assigned_sites else "",
            }
            dm.update_course(course_id, fields)
            flash("Course updated.", "success")
        elif action == "delete":
            course_id = request.form.get("course_id", "")
            dm.delete_course(course_id)
            flash("Course deleted.", "warning")
        return redirect(url_for("training.manage_courses"))

    courses = dm.get_all_courses()
    all_sites = dm.get_site_names()
    all_roles = ["admin", "director", "standard", "viewer"]
    return render_template(
        "training/manage_courses.html",
        **_ctx("manage", courses=courses, all_sites=all_sites, all_roles=all_roles),
    )


@trn_bp.route("/manage/<course_id>/build", methods=["GET", "POST"])
@login_required
def course_builder(course_id):
    """Full course content builder — modules, chapters, tests."""
    course = dm.get_course(course_id)
    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("training.manage_courses"))

    if request.method == "POST":
        action = request.form.get("action", "")

        # ── Module actions ──
        if action == "add_module":
            dm.create_module({
                "course_id": course_id,
                "title": request.form.get("title", "New Module"),
                "sort_order": int(request.form.get("sort_order", 0)),
            })
            flash("Module added.", "success")
        elif action == "update_module":
            dm.update_module(request.form.get("module_id"), {
                "title": request.form.get("title", ""),
                "sort_order": int(request.form.get("sort_order", 0)),
            })
            flash("Module updated.", "success")
        elif action == "delete_module":
            dm.delete_module(request.form.get("module_id"))
            flash("Module deleted.", "warning")

        # ── Chapter actions ──
        elif action == "add_chapter":
            dm.create_chapter({
                "course_id": course_id,
                "module_id": request.form.get("module_id", ""),
                "title": request.form.get("title", "New Chapter"),
                "content": request.form.get("content", ""),
                "sort_order": int(request.form.get("sort_order", 0)),
                "has_test": 1 if request.form.get("has_test") else 0,
            })
            flash("Chapter added.", "success")
        elif action == "update_chapter":
            dm.update_chapter(request.form.get("chapter_id"), {
                "title": request.form.get("title", ""),
                "content": request.form.get("content", ""),
                "module_id": request.form.get("module_id", ""),
                "sort_order": int(request.form.get("sort_order", 0)),
                "has_test": 1 if request.form.get("has_test") else 0,
            })
            flash("Chapter updated.", "success")
        elif action == "delete_chapter":
            dm.delete_chapter(request.form.get("chapter_id"))
            flash("Chapter deleted.", "warning")

        # ── Test actions ──
        elif action == "save_test":
            chapter_id = request.form.get("chapter_id", "")
            test_title = request.form.get("test_title", "Quiz")
            passing_score = float(request.form.get("passing_score") or 70)
            # Parse questions from form
            questions = []
            q_idx = 0
            while request.form.get(f"q_{q_idx}_text"):
                q_text = request.form.get(f"q_{q_idx}_text", "")
                options = [
                    request.form.get(f"q_{q_idx}_opt_0", ""),
                    request.form.get(f"q_{q_idx}_opt_1", ""),
                    request.form.get(f"q_{q_idx}_opt_2", ""),
                    request.form.get(f"q_{q_idx}_opt_3", ""),
                ]
                correct = int(request.form.get(f"q_{q_idx}_correct", 0))
                questions.append({"question": q_text, "options": options, "correct": correct})
                q_idx += 1

            existing_test = dm.get_test_for_chapter(chapter_id)
            if existing_test:
                dm.update_test(existing_test["test_id"], {
                    "title": test_title,
                    "passing_score": passing_score,
                    "questions": questions,
                })
            else:
                dm.create_test({
                    "chapter_id": chapter_id,
                    "course_id": course_id,
                    "title": test_title,
                    "passing_score": passing_score,
                    "questions": questions,
                })
            flash("Test saved.", "success")

        return redirect(url_for("training.course_builder", course_id=course_id))

    modules = dm.get_modules_for_course(course_id)
    chapters = dm.get_chapters_for_course(course_id)
    tests = dm.get_tests_for_course(course_id)
    test_map = {t["chapter_id"]: t for t in tests}

    return render_template(
        "training/course_builder.html",
        **_ctx("manage", course=course, modules=modules, chapters=chapters,
               test_map=test_map),
    )


@trn_bp.route("/reports")
@login_required
def reports():
    by_course = dm.get_completion_by_course()
    by_site = dm.get_completion_by_site()
    top_performers = dm.get_top_performers()
    return render_template(
        "training/reports.html",
        **_ctx("reports", by_course=by_course, by_site=by_site, top_performers=top_performers),
    )
