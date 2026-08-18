# AGENTS.md — Rules for AI agents working on NagarLoop
> Read PRD.md + ROADMAP.md BEFORE any change. Follow DOs, respect DON'Ts.

## Environment
Root: C:\Users\patel jenish\swachhloop • venv: .\venv (Python 3.11)
Run: venv\Scripts\python.exe app.py • Tests: venv\Scripts\python.exe test_swachhloop.py
Repo: github.com/Jenish07-oss/Swachhloop (branch main)

## DO ✅
- ALWAYS use venv; never install global packages.
- Modular code: queries→database.py • routes→app.py • loops→simulate_trucks.py • UI→templates/ • brand/strings→brand.py.
- After EVERY feature/fix: git add . && git commit -m "type(scope): msg" && git push origin main.
- Test every touched route locally BEFORE saying done; report pass/fail per route.
- On any error: first ask user to paste the terminal traceback; don't guess-fix.
- All UI strings via brand.T in EN + GU. All numbers labelled "estimated" where applicable.
- Demo creds shown only when DEBUG.
- Explain WHY (beginner-friendly) after each code block.

## DON'T ❌
- No PostgreSQL/MySQL/Mongo (SQLite only). No Docker/AWS/microservices.
- No paid APIs (maps, SMS, AI). SMS = simulated log + toasts.
- No IoT/hardware/sensors. No deep learning.
- DO NOT break/rename core routes: /, /book, /report, /my-pickups, /impact, /manifest/<id>, /admin, /admin/dispatch, /admin/route/<van>, /api/* (status, citizen/verify, route/deliver, route/recalculate, route/apply, vans, facilities, leaderboard, reset-demo).
- NO SIH/hackathon/PS-8-L/SDG/"demo ward" text in WEBSITE UI (product-only look). SIH content ONLY in PPT artifacts when explicitly asked.
- No lorem ipsum; every screen renders real seeded data.
- No formulas in UI. No paragraphs in UI or PPT.

## PPT RULES (only when asked to make SIH PPT content)
Follow: max 6 slides incl. title • slide 7 deleted • PDF only • template locked (no new colors/fonts/logos, headers fixed) • bullets/diagrams/tables only • fill PSID/TeamID exactly • slide 3 flowchart • slide 4 Challenge→Mitigation 2-col table • slide 5 numbers + who benefits • slide 6 REAL links only.
IGNORE: slide 7 content, extra slides (agenda/thank-you/team-intro/appendix), college branding, template redesign, placeholder IDs ("TBD"), copied PS wording as idea, fake links, tiny-font overcrowding.