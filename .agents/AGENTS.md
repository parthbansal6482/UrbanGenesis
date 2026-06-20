## UrbanGenesis / FarmGuard \u2014 Development Guidelines

### Project Context
FastAPI backend (app.py) + Next.js 16 dashboard (dashboard/).
Python 3.11+. Node 20+.

### Backend (Python)
- Run: `UVICORN_RELOAD=true PYTHONPATH=. python app.py`
- Test: `PYTHONPATH=. pytest tests/ -v`
- Lint: `ruff check .` (or flake8)
- All analytics modules export from `analytics/` package root

### Frontend (Next.js)
- Run: `cd dashboard && npm run dev`
- Type-check: `cd dashboard && npx tsc --noEmit`
- Lint: `cd dashboard && npm run lint`

### Code Style
- Python: Black-compatible (88 char line length), type hints required for public functions
- TypeScript: strict mode; no `any` without justification and ESLint disable comment
- Commit message format: `<scope>: <short description>` (e.g. `dashboard: fix gradeClass D`)
