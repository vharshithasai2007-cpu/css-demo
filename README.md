# CSS Demo

A standalone, unofficial educational demonstration portal. It is **not** connected
to the live AICTE portal, uses no real AICTE branding, and every submission is
simulated.

> EDUCATIONAL DEMO - UNOFFICIAL CSS REPLICA. NOT CONNECTED TO THE LIVE AICTE
> PORTAL. SUBMISSIONS ARE SIMULATED.

This project was extracted from the AICTE complaint-monitoring dashboard. It has
its own database, its own authentication and its own environment configuration,
and it does not read or write the dashboard's databases or configuration.

## What it does

- Citizens register and log in with a portal-only account.
- They submit a `COMPLAINT`, `GRIEVANCE` or `WILLING_TO_SUPPORT` request.
- Each submission receives a `CSSD-YYYY-NNNNNN` reference ID.
- A background simulator moves requests through
  `SUBMITTED -> UNDER_REVIEW -> REPLY_SENT -> RESOLVED`.
- Citizens track a request by reference ID or browse their own requests.
- `GET /tickets` exposes portal submissions in the dashboard's CSS ticket shape
  so an external consumer could poll them. Nothing polls it by default.

## Layout

```
css-demo/
  backend/            FastAPI service + portal SQLite database
    main.py           App entrypoint, /tickets and /admin endpoints
    portal/           Portal models, auth, routers, simulation
    tests/            Pytest suite
    .env.example      Environment template
  frontend/           React + Vite + Tailwind portal UI
    src/portal/       Portal-only pages and components
  docs/               Data-layer notes
  docker-compose.yml  Optional two-service stack
```

## Requirements

- Python 3.11+
- Node.js 20+ and npm

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8101 --env-file .env
```

The API is at <http://127.0.0.1:8101>, with docs at
<http://127.0.0.1:8101/docs>.

On first start the portal creates `backend/data/css_demo.db` (WAL mode, foreign
keys enabled). It never touches any other database.

### Tests

```powershell
cd backend
python -m pytest -q
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173/css-demo>. `/` redirects to `/css-demo`.

In development Vite proxies `/css-api/*` to `http://127.0.0.1:8101`, stripping
the `/css-api` prefix. Override the target with `VITE_CSS_PROXY_TARGET`. The
backend has no CORS middleware, so use the dev server or the Docker stack rather
than calling the API cross-origin.

### Build

```powershell
cd frontend
npm run build
```

## Docker

```powershell
docker compose up --build
```

- Portal: <http://localhost:5173/css-demo>
- API: <http://localhost:8101>
- Portal data is stored in the `css_demo_data` volume.

`docker compose down -v` deletes that volume and all demo data.

## Configuration

All settings live in `backend/.env` (see `backend/.env.example`). The backend
reads them from the process environment, so pass `--env-file .env` when starting
uvicorn outside Docker.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CSS_PORTAL_DB_PATH` | `./data/css_portal.db` (code default) | Portal SQLite file |
| `CSS_PORTAL_SECRET_KEY` | dev-only insecure default | Portal JWT secret; required when `CSS_PORTAL_ENV=production` |
| `CSS_PORTAL_TOKEN_MINUTES` | `120` | Portal token lifetime |
| `CSS_PORTAL_SIM_STEP_SECONDS` | `45` | Delay between simulated lifecycle steps |
| `CSS_PORTAL_ENV` | `development` | Deployment environment |
| `CSS_PORTAL_SIM_ENABLED` | `true` | Run the lifecycle simulation loop |
| `MOCK_CSS_AUTOGEN` | `true` (code default) | Generate random simulator tickets; this project ships `.env` with `false` |
| `CSS_PORTAL_ADMIN_KEY` | unset | Optional `X-Demo-Admin-Key` for `/admin/*` |
| `VITE_CSS_PROXY_TARGET` | `http://127.0.0.1:8101` | Vite dev proxy target |

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health |
| `GET` | `/tickets` | Simulator + portal tickets in CSS shape |
| `POST` | `/portal/auth/register` | Create a portal account |
| `POST` | `/portal/auth/login` | Obtain a portal JWT |
| `GET` | `/portal/auth/me` | Current portal user |
| `GET` | `/portal/meta` | Categories, request types, institutions |
| `POST` | `/portal/requests` | Submit a request |
| `GET` | `/portal/requests` | List the current user's requests |
| `GET` | `/portal/requests/{reference_id}` | Request detail and timeline |
| `POST` | `/portal/v2/requests` | Request-type-aware submission |
| `GET` | `/portal/v2/requests` | Request-type-aware listing |
| `POST` | `/admin/portal/advance/{reference_id}` | Advance one request |
| `POST` | `/admin/portal/advance-all` | Advance all due requests |

Portal auth is separate from any dashboard auth: JWT HS256 with audience and
issuer `css-portal-demo`, and the frontend stores the token under
`css_portal_token`.

## Disclaimer

This is an educational replica for demonstration purposes only. It is not
affiliated with AICTE, is not connected to the live CSS/AICTE portal, and must
not be used to file real grievances.
