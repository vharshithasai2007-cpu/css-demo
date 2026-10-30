.PHONY: backend-test backend-run frontend-install frontend-run frontend-build up down

backend-test:
	cd backend && python -m pytest -q

backend-run:
	cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8101 --env-file .env

frontend-install:
	cd frontend && npm install

frontend-run:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

up:
	docker compose up --build

down:
	docker compose down
