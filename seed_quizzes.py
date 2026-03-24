"""
Cerasus Hub — Seed Training Quizzes
Creates quiz questions for all 14 chapters of "The Cerasus Way - Director Training"
based on actual chapter content.
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


# ── Quiz data for all 14 chapters ────────────────────────────────────
# Format: {"question": "...", "options": ["A", "B", "C", "D"], "correct": index}

CHAPTER_QUIZZES = {
    1: {
        "title": "Chapter 1 Quiz: The Cerasus Identity & Mission",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "What does the name 'Cerasus' refer to?",
                "options": [
                    "A Roman military formation",
                    "The sour cherry tree (Prunus Cerasus)",
                    "A Latin word meaning 'guardian'",
                    "A Greek word for 'shield'"
                ],
                "correct": 1
            },
            {
                "question": "Which of the following best describes Cerasus's approach to security?",
                "options": [
                    "Aggressive and confrontational",
                    "Reactive and response-driven",
                    "Protective, not reactive",
                    "Minimal presence, maximum force"
                ],
                "correct": 2
            },
            {
                "question": "What is the Cerasus mission?",
                "options": [
                    "To be the largest security company in the Midwest",
                    "To deliver unparalleled corporate security and unmatched customer service",
                    "To provide the cheapest security solutions available",
                    "To replace law enforcement at commercial sites"
                ],
                "correct": 1
            },
            {
                "question": "What does 'deep roots' mean in the Cerasus philosophy?",
                "options": [
                    "Officers should stay at one site permanently",
                    "Building long-term relationships with employees and clients",
                    "Having a large corporate headquarters",
                    "Hiring officers from the local community only"
                ],
                "correct": 1
            },
            {
                "question": "What does 'quiet strength' refer to at Cerasus?",
                "options": [
                    "Officers should not speak to anyone on site",
                    "Officers are visible and professional, deterring trouble without unnecessary confrontation",
                    "Officers should work silently in the background",
                    "Security should never be noticed by clients"
                ],
                "correct": 1
            },
        ],
    },
    2: {
        "title": "Chapter 2 Quiz: Financial Discipline and Understanding",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "If an officer is paid $18/hr and the client is billed $27/hr, what is the multiplier?",
                "options": ["1.0", "1.25", "1.5", "2.0"],
                "correct": 2
            },
            {
                "question": "What does DLS stand for?",
                "options": [
                    "Direct Labor and Supervision",
                    "Daily Labor Schedule",
                    "Director Level Standards",
                    "Distributed Labor System"
                ],
                "correct": 0
            },
            {
                "question": "Why must every Cerasus leader understand financial fundamentals?",
                "options": [
                    "To negotiate their own salary",
                    "To avoid promises that lose money and to protect margins",
                    "To compete with other security companies on price",
                    "Because finance is the only metric that matters"
                ],
                "correct": 1
            },
            {
                "question": "What is the Bill Rate?",
                "options": [
                    "The hourly wage paid to the officer",
                    "The total invoice sent monthly",
                    "The hourly rate charged to the client",
                    "The overtime rate for weekend shifts"
                ],
                "correct": 2
            },
            {
                "question": "What happens when overtime erodes margins?",
                "options": [
                    "The company grows faster",
                    "Client satisfaction increases",
                    "Profitability decreases and the company's financial health is at risk",
                    "Officers get promoted sooner"
                ],
                "correct": 2
            },
        ],
    },
    3: {
        "title": "Chapter 3 Quiz: Customer Relations & Influence",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "A client who asks 'What is our exposure?' is likely which archetype?",
                "options": [
                    "Budget-driven",
                    "Operations-first",
                    "Safety-first (risk-averse)",
                    "Visibility/status-driven"
                ],
                "correct": 2
            },
            {
                "question": "A client who says 'Hold this rate for twelve months' is which archetype?",
                "options": [
                    "Safety-first",
                    "Budget-driven",
                    "Partnership-oriented",
                    "Compliance-driven"
                ],
                "correct": 1
            },
            {
                "question": "What is the key to understanding client archetypes?",
                "options": [
                    "Labeling them immediately and acting accordingly",
                    "Listening, asking the right questions, and adapting",
                    "Treating all clients exactly the same way",
                    "Focusing only on cost when communicating"
                ],
                "correct": 1
            },
            {
                "question": "A compliance-driven client's primary cue is:",
                "options": [
                    "'How fast can we move people?'",
                    "'Our executives see the lobby daily'",
                    "'Show me the record'",
                    "'What's the cheapest option?'"
                ],
                "correct": 2
            },
        ],
    },
    4: {
        "title": "Chapter 4 Quiz: The Cerasus Decision-Making Framework",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "What is the first step in the Cerasus four-step decision cycle?",
                "options": ["Execute", "Debrief", "Pre-brief", "Monitor"],
                "correct": 2
            },
            {
                "question": "What does decision-making discipline prevent?",
                "options": [
                    "Employee satisfaction",
                    "Overtime spikes, unprofitable commitments, and loss of credibility",
                    "Client retention",
                    "Officer promotions"
                ],
                "correct": 1
            },
            {
                "question": "The four-step cycle should be used:",
                "options": [
                    "Only after a decision has been made",
                    "Only for financial decisions",
                    "As the decision process itself, before committing",
                    "Only by senior leadership"
                ],
                "correct": 2
            },
            {
                "question": "What does 'closing the loop' mean in the decision framework?",
                "options": [
                    "Ending the meeting on time",
                    "Reviewing outcomes and continuously improving based on results",
                    "Getting client sign-off on every decision",
                    "Sending a follow-up email"
                ],
                "correct": 1
            },
        ],
    },
    5: {
        "title": "Chapter 5 Quiz: Leadership Styles and Employee Understanding",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "Why should leaders flex their leadership style?",
                "options": [
                    "To confuse employees and keep them alert",
                    "Because no two employees are the same and different situations require different approaches",
                    "Because corporate requires style rotation",
                    "To avoid accountability"
                ],
                "correct": 1
            },
            {
                "question": "A directive style is most appropriate for:",
                "options": [
                    "A seasoned high-performing officer",
                    "A new officer who needs clear guidance",
                    "A team that has been together for years",
                    "A client meeting"
                ],
                "correct": 1
            },
            {
                "question": "How many core leadership styles does Cerasus identify?",
                "options": ["Three", "Four", "Five", "Seven"],
                "correct": 2
            },
            {
                "question": "What happens when a delegating style is used with a struggling officer?",
                "options": [
                    "They become empowered",
                    "They are left without the support they need",
                    "They get promoted faster",
                    "They file a complaint"
                ],
                "correct": 1
            },
        ],
    },
    6: {
        "title": "Chapter 6 Quiz: HR Guidelines and Best Practices",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "What is the foundation for how every Cerasus employee represents the company?",
                "options": [
                    "The employee handbook",
                    "The Code of Conduct",
                    "The client contract",
                    "The training manual"
                ],
                "correct": 1
            },
            {
                "question": "How many steps are in the Cerasus conflict resolution process?",
                "options": ["Four", "Five", "Six", "Eight"],
                "correct": 2
            },
            {
                "question": "When should Code of Conduct expectations be explained?",
                "options": [
                    "Only when violations occur",
                    "During onboarding, acknowledged in writing, and reinforced daily",
                    "At annual reviews only",
                    "When the client requests it"
                ],
                "correct": 1
            },
            {
                "question": "A leader's job regarding workplace conflict is to:",
                "options": [
                    "Prevent all conflict from ever occurring",
                    "Ignore minor conflicts",
                    "Resolve it fairly, quickly, and visibly to the team",
                    "Refer all conflicts to HR"
                ],
                "correct": 2
            },
        ],
    },
    7: {
        "title": "Chapter 7 Quiz: Training and Development",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "How many distinct types of training does Cerasus use?",
                "options": ["Three", "Five", "Seven", "Ten"],
                "correct": 2
            },
            {
                "question": "What is the result of poor or incomplete training?",
                "options": [
                    "Higher client satisfaction",
                    "Lower turnover",
                    "Higher turnover, low morale, and client dissatisfaction",
                    "Faster promotions"
                ],
                "correct": 2
            },
            {
                "question": "Training at Cerasus sets the tone for:",
                "options": [
                    "Salary negotiations",
                    "Culture — officers learn from day one what the company expects",
                    "Client billing rates",
                    "Overtime policies"
                ],
                "correct": 1
            },
            {
                "question": "Why does using the wrong training type for a situation matter?",
                "options": [
                    "It doesn't — all training is the same",
                    "It is inefficient and ineffective because each type addresses a specific gap",
                    "It costs more money",
                    "It violates company policy"
                ],
                "correct": 1
            },
        ],
    },
    8: {
        "title": "Chapter 8 Quiz: Staffing and Redundancy",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "What four things does redundancy protect?",
                "options": [
                    "Revenue, marketing, sales, brand",
                    "Continuity of service, financial discipline, officer well-being, client trust",
                    "Hiring speed, turnover, pay rates, benefits",
                    "Equipment, vehicles, uniforms, technology"
                ],
                "correct": 1
            },
            {
                "question": "What happens without staffing redundancy?",
                "options": [
                    "Service quality improves",
                    "Officers get more hours and are happier",
                    "Overtime explodes, client confidence drops, and officer morale suffers",
                    "Nothing — redundancy is optional"
                ],
                "correct": 2
            },
            {
                "question": "Coverage design includes which three elements?",
                "options": [
                    "Hiring, firing, promoting",
                    "Bench, cross-training, flex",
                    "Morning, afternoon, night shifts",
                    "Client, officer, supervisor"
                ],
                "correct": 1
            },
            {
                "question": "When should coverage design be built?",
                "options": [
                    "After someone calls off",
                    "Before a single person calls off — it is proactive infrastructure",
                    "Only during the holidays",
                    "When the client requests it"
                ],
                "correct": 1
            },
        ],
    },
    9: {
        "title": "Chapter 9 Quiz: Performance Management",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "What happens without structured performance management?",
                "options": [
                    "Officers self-manage effectively",
                    "Small issues compound into turnover, overtime, and client dissatisfaction",
                    "Clients stop caring about service quality",
                    "Nothing changes"
                ],
                "correct": 1
            },
            {
                "question": "Which of the following is a core performance management tool at Cerasus?",
                "options": [
                    "Social media reviews",
                    "Officer scorecards",
                    "Anonymous surveys",
                    "Client tip lines"
                ],
                "correct": 1
            },
            {
                "question": "Performance management builds:",
                "options": [
                    "Competition between officers",
                    "Fairness, transparency, and a clear path for growth",
                    "Fear and compliance",
                    "Complicated bureaucracy"
                ],
                "correct": 1
            },
        ],
    },
    10: {
        "title": "Chapter 10 Quiz: Client-Facing Professionalism",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "Where does professionalism start at Cerasus?",
                "options": [
                    "At the officer level",
                    "At the client's request",
                    "At the top — leadership sets the tone",
                    "At the interview stage"
                ],
                "correct": 2
            },
            {
                "question": "What can a single lapse in leadership communication cause?",
                "options": [
                    "Nothing significant",
                    "A small delay in reporting",
                    "Erosion of client trust and jeopardized contracts",
                    "A team meeting"
                ],
                "correct": 2
            },
            {
                "question": "Leadership professionalism is about:",
                "options": [
                    "Personal behavior only",
                    "Shaping the company's reputation through structure, accountability, and standards",
                    "Being the most liked person at the site",
                    "Wearing the best uniform"
                ],
                "correct": 1
            },
        ],
    },
    11: {
        "title": "Chapter 11 Quiz: Risk Management and Compliance",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "Risk in security extends across how many dimensions?",
                "options": ["Two", "Three", "Four", "Six"],
                "correct": 2
            },
            {
                "question": "Which is NOT one of the four risk dimensions?",
                "options": [
                    "Physical threats",
                    "Legal liability",
                    "Marketing exposure",
                    "Reputational damage"
                ],
                "correct": 2
            },
            {
                "question": "What do compliance failures in security result in?",
                "options": [
                    "Abstract, theoretical risks",
                    "Officer injuries, lawsuits, lost licenses, and terminated contracts",
                    "Higher client satisfaction",
                    "Increased hiring"
                ],
                "correct": 1
            },
            {
                "question": "Leaders must constantly:",
                "options": [
                    "Avoid documenting issues to reduce liability",
                    "Identify, assess, and mitigate risks",
                    "Delegate all risk management to HR",
                    "Wait for incidents before taking action"
                ],
                "correct": 1
            },
        ],
    },
    12: {
        "title": "Chapter 12 Quiz: Crisis Management and Emergency Response",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "How many crisis levels does Cerasus use?",
                "options": ["Two", "Three", "Four", "Five"],
                "correct": 1
            },
            {
                "question": "What is a Level 1 (Minor) crisis?",
                "options": [
                    "Active threat requiring evacuation",
                    "Minor service disruption, no life safety risk — handle on site",
                    "A public relations incident",
                    "A financial audit finding"
                ],
                "correct": 1
            },
            {
                "question": "Every crisis begins as:",
                "options": [
                    "A client complaint",
                    "An incident — the difference is severity and speed of escalation",
                    "A staffing shortage",
                    "A policy violation"
                ],
                "correct": 1
            },
            {
                "question": "When in doubt about crisis level, leaders should:",
                "options": [
                    "Wait and see how it develops",
                    "Consult the employee handbook",
                    "Escalate to the higher level",
                    "Contact the media"
                ],
                "correct": 2
            },
        ],
    },
    13: {
        "title": "Chapter 13 Quiz: Recruitment and Talent Development",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "Why does pipeline health matter?",
                "options": [
                    "It looks good on reports",
                    "A strong pipeline shortens time-to-fill, reduces overtime, and keeps service stable",
                    "It is only important for HR",
                    "It doesn't — reactive hiring works fine"
                ],
                "correct": 1
            },
            {
                "question": "Which metric measures how quickly Cerasus captures strong candidates?",
                "options": [
                    "30-day retention",
                    "Quality of hire",
                    "Time of application to first interview",
                    "Bench depth"
                ],
                "correct": 2
            },
            {
                "question": "How does faster fills tie to finances?",
                "options": [
                    "It doesn't affect finances",
                    "Faster fills reduce overtime and protect margin",
                    "Faster fills increase training costs",
                    "Faster fills lower officer quality"
                ],
                "correct": 1
            },
            {
                "question": "What does 'bench depth by site and shift' measure?",
                "options": [
                    "Number of supervisors per site",
                    "Number of trained backups per post",
                    "Total headcount in the company",
                    "Number of applications received"
                ],
                "correct": 1
            },
        ],
    },
    14: {
        "title": "Chapter 14 Quiz: Vision, Culture, and Long-Term Growth",
        "passing_score": 70.0,
        "questions": [
            {
                "question": "According to Cerasus, culture is:",
                "options": [
                    "A mission statement on a wall",
                    "The daily behaviors we reward, stories we repeat, and standards we enforce",
                    "Something only HR manages",
                    "Only important during onboarding"
                ],
                "correct": 1
            },
            {
                "question": "Which is NOT one of the five cultural pillars at Cerasus?",
                "options": [
                    "Service mindset",
                    "Ownership",
                    "Competition",
                    "Discipline"
                ],
                "correct": 2
            },
            {
                "question": "How should culture be reinforced?",
                "options": [
                    "Through annual company meetings only",
                    "Hire for behaviors, train to behaviors with scripts and drills",
                    "By posting signs around the office",
                    "Through financial incentives only"
                ],
                "correct": 1
            },
            {
                "question": "Without culture, what happens during expansion?",
                "options": [
                    "Growth accelerates",
                    "Expansion creates cracks and quality suffers",
                    "Clients are more forgiving",
                    "Officers become more independent"
                ],
                "correct": 1
            },
        ],
    },
}


def seed_quizzes():
    ensure_directories()
    initialize_database()
    conn = get_conn()

    # Get the course
    course = conn.execute(
        "SELECT course_id FROM trn_courses WHERE title LIKE '%Cerasus Way%'"
    ).fetchone()

    if not course:
        print("ERROR: Course 'The Cerasus Way' not found. Run import_training_data.py first.")
        sys.exit(1)

    course_id = course["course_id"]

    # Get all chapters sorted by sort_order
    chapters = conn.execute(
        "SELECT chapter_id, title, sort_order FROM trn_chapters WHERE course_id = ? ORDER BY sort_order",
        (course_id,),
    ).fetchall()

    print(f"Found {len(chapters)} chapters for course: {course_id}")

    # Clear existing tests for this course
    deleted = conn.execute("DELETE FROM trn_tests WHERE course_id = ?", (course_id,)).rowcount
    if deleted:
        print(f"Cleared {deleted} existing tests")

    created = 0
    for ch in chapters:
        ch_id = ch["chapter_id"]
        sort_order = ch["sort_order"]
        ch_title = ch["title"]

        # Match chapter number from title (check longest matches first to avoid
        # "Chapter 1" matching "Chapter 10", "Chapter 11", etc.)
        ch_num = None
        for n in range(14, 0, -1):
            if f"Chapter {n} " in ch_title or f"Chapter {n} -" in ch_title:
                ch_num = n
                break

        if ch_num is None or ch_num not in CHAPTER_QUIZZES:
            print(f"  SKIP: {ch_title} (no quiz data for chapter {sort_order})")
            continue

        quiz = CHAPTER_QUIZZES[ch_num]
        test_id = _gen_id()

        conn.execute(
            """INSERT INTO trn_tests (test_id, chapter_id, course_id, title, passing_score, questions, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                test_id,
                ch_id,
                course_id,
                quiz["title"],
                quiz["passing_score"],
                json.dumps(quiz["questions"]),
                _now(),
            ),
        )

        # Mark chapter as having a test
        conn.execute(
            "UPDATE trn_chapters SET has_test = 1 WHERE chapter_id = ?", (ch_id,)
        )

        created += 1
        print(f"  Ch {ch_num}: {quiz['title']} ({len(quiz['questions'])} questions)")

    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"  QUIZ SEEDING COMPLETE")
    print(f"{'='*60}")
    print(f"  Tests created: {created}")
    print(f"  Total questions: {sum(len(q['questions']) for q in CHAPTER_QUIZZES.values())}")
    print(f"{'='*60}")


if __name__ == "__main__":
    seed_quizzes()
