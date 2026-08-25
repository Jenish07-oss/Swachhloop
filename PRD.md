# NagarLoop — Product Requirements Document (PRD)

## Phase 1: Rebranding, Landing, i18n & Auth Foundation
- **Brand:** NagarLoop (`brand.py`)
- **Slogan:** 
  - EN: "Collect. Recover. Reuse. Repeat."
  - GU: "એકત્ર કરો. પુનઃપ્રાપ્ત કરો. પુનઃઉપયોગ કરો. પુનરાવર્તન કરો."
- **City:** Ahmedabad
- **Support:** support@nagarloop.in
- **Roles:** Citizen (`/login/citizen`), Driver (`/login/driver`), Municipal Admin (`/login/admin`)
- **Key Routes:**
  - `GET /` — Compact product homepage with animated SVG loop and audience cards
  - `GET /book` — Citizen segregated booking portal
  - `POST /set-lang` — English / Gujarati toggle
  - `GET /privacy`, `GET /rewards`, `GET /help` — Legal and user policy center
  - `GET /driver`, `GET /driver/history` — Minimal driver route portal
  - `GET /leaderboard` — Civic green champions leaderboard
