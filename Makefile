# UrbanGenesis Makefile
# Usage:
#   make dev       \u2014 start both backend and frontend (requires two terminals)
#   make backend   \u2014 start FastAPI backend only
#   make frontend  \u2014 start Next.js dashboard only
#   make test      \u2014 run Python test suite
#   make typecheck \u2014 run TypeScript type checker
#   make lint      \u2014 run all linters
#   make install   \u2014 install all dependencies

.PHONY: all dev backend frontend test typecheck lint install

PYTHON  ?= python
NPM     ?= npm

# ---- Installation -------------------------------------------------------
install:
	$(PYTHON) -m pip install -r requirements.txt
	cd dashboard && $(NPM) install

# ---- Development servers ------------------------------------------------
backend:
	PYTHONPATH=. UVICORN_RELOAD=true $(PYTHON) app.py

frontend:
	cd dashboard && $(NPM) run dev

# dev: print instructions (cannot run two foreground processes from one make target)
dev:
	@echo ""
	@echo "Start the backend in one terminal:"
	@echo "  make backend"
	@echo ""
	@echo "Start the dashboard in another terminal:"
	@echo "  make frontend"
	@echo ""
	@echo "Then open: http://localhost:3000"
	@echo ""

# ---- Quality checks -----------------------------------------------------
test:
	PYTHONPATH=. pytest tests/ -v

typecheck:
	cd dashboard && npx tsc --noEmit

lint:
	cd dashboard && $(NPM) run lint
