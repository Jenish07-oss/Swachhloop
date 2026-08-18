# NagarLoop — Agent Rules & Engineering Standards

## DOs
1. **Virtual Environment Only:** Always use `.\venv\Scripts\python.exe` on Windows for running scripts and tests.
2. **SQLite Only:** Keep the local SQLite database (`swachhloop.db` / `database.py`) fast, transactional, and relational.
3. **No Paid APIs:** Use open-source Leaflet, OpenStreetMap, local algorithms, and standard libraries.
4. **Modular & Clean:** Keep code structured (`brand.py`, `database.py`, `app.py`).
5. **Real Product Aesthetic:** No mention of "SIH", "Hackathon", "PS 8-L", "Smart India", or dummy placeholder texts anywhere in UI.
6. **Pass/Fail Verification:** Test all endpoints and verify status codes and UI rendering.
7. **Git Discipline:** Commit with conventional commit messages and push when requested.

## DON'Ts
1. Do not use external paid geocoding or proprietary AI APIs.
2. Do not leave broken nav links or unhandled exception routes.
3. Do not hardcode static hackathon banners into citizen or operational dashboards.
