.PHONY: dev backend frontend seed reset reset-hard test

dev:
	@echo "Levantando backend (8000) y frontend (5173)..."
	@(cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && npm run dev)

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

seed:
	mkdir -p backend/data/runtime backend/data/cache
	cp data/*.json backend/data/

# Con el backend levantado, el reset va por la API: así se cancelan las respuestas en curso.
reset: seed
	@curl -sf -X POST http://localhost:8000/reset >/dev/null \
		&& echo "Reset vía API (backend levantado). Cache conservado." \
		|| (rm -rf backend/data/runtime && echo "Backend apagado: runtime borrado. Cache conservado.")

reset-hard: seed
	@curl -sf -X POST "http://localhost:8000/reset?hard=true" >/dev/null \
		&& echo "Reset total vía API (backend levantado)." \
		|| (rm -rf backend/data/runtime backend/data/cache && echo "Backend apagado: runtime y cache borrados.")

test:
	cd backend && . .venv/bin/activate && python -m pytest -q
