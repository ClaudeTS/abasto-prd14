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
	cp data/proveedores_sim.json data/pedido_demo.json data/respuestas_fijas.json backend/data/

reset:
	rm -rf backend/data/runtime && $(MAKE) seed
	@echo "Estado de demo restaurado (cache de respuestas conservado)."

reset-hard:
	rm -rf backend/data/runtime backend/data/cache && $(MAKE) seed
	@echo "Estado de demo restaurado y cache borrado."

test:
	cd backend && . .venv/bin/activate && python -m pytest tests/test_smoke.py -q
