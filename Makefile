.PHONY: demo bootstrap backend-check backend-dev backend-sync check dependency-audit dependency-inventory dependency-licenses dependency-sbom frontend-browser frontend-check frontend-dev frontend-sync performance-smoke quality-corpus

UV ?= uv
NPM ?= npm

bootstrap: backend-sync frontend-sync frontend-browser

backend-sync:
	cd backend && $(UV) sync --locked

frontend-sync:
	cd frontend && $(NPM) ci

frontend-browser:
	cd frontend && npx playwright install chromium

backend-check:
	cd backend && $(UV) lock --check
	cd backend && $(UV) run --locked ruff format --check .
	cd backend && $(UV) run --locked ruff check .
	cd backend && $(UV) run --locked mypy
	cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(UV) run --locked pytest

frontend-check:
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run test
	cd frontend && $(NPM) run build
	cd frontend && $(NPM) run test:e2e

check: backend-check frontend-check

backend-dev:
	cd backend && $(UV) run --locked uvicorn movie_language_helper.adapters.inbound.http.app:create_app --factory --reload

frontend-dev:
	cd frontend && $(NPM) run dev

# Backend with the offline lexicon analyzer plus the frontend. Upload
# examples/sample.srt at http://127.0.0.1:5173 to try it without any API key.
demo:
	( trap 'kill 0' INT TERM EXIT; \
	  cd backend && MLH_LEXICON_ANALYZER_ENABLED=true $(UV) run --locked uvicorn movie_language_helper.adapters.inbound.http.app:create_app --factory & \
	  cd frontend && $(NPM) run dev & \
	  wait )

dependency-inventory:
	cd backend && $(UV) tree --locked
	cd frontend && $(NPM) ls --all

dependency-licenses:
	cd backend && $(UV) run --locked python -I scripts/dependency_licenses.py
	cd frontend && $(NPM) run licenses

dependency-audit:
	cd backend && $(UV) audit --preview
	cd frontend && $(NPM) audit --audit-level=high

dependency-sbom:
	mkdir -p .artifacts
	cd backend && $(UV) export --preview --format cyclonedx1.5 --output-file ../.artifacts/backend.cdx.json > /dev/null
	cd frontend && $(NPM) sbom --sbom-format=cyclonedx > ../.artifacts/frontend.cdx.json

quality-corpus:
	cd backend && $(UV) run --locked python scripts/validate_golden_corpus.py

performance-smoke:
	cd backend && $(UV) run --locked python scripts/performance_smoke.py
