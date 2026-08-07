# Newmeric Compass — Backend

FastAPI + MongoDB backend for the Newmeric Compass (N5) Vastu app. Powers the
32-pada compass engine, the app content (categories, padas, rules, tips,
submissions) and the admin panel API.

## The N5 compass system
The compass is split into **32 padas of 11.25°** each — `N1..N8`, `E1..E8`,
`S1..S8`, `W1..W8` — anchored so **N5 sits on due North (0°)**. Every pada
carries a 16-wind direction, element (Panchabhuta), dosha, body organ, life
aspect and a default verdict. See `app/domain/padas.py` (single source of truth).

A **rule** is the verdict for a `category × pada` — its `verdict`
(excellent/good/average/bad), `score`, `effects[]` and `treatments[]`. If no
rule is configured for a cell, the engine synthesises a result from the pada's
default so the app never gets an empty response.

## Quick start
```bash
uv sync                       # install deps
cp .env.example .env          # fill in MONGODB_URL, SECRET_KEY, Cloudinary
uv run scripts/seed_all.py    # seed 32 padas + categories + sample rules
uv run scripts/create_admin.py admin@newmericcompass.com 'StrongPass123'
uv run uvicorn app.main:app --reload
```
Docs at http://localhost:8000/docs

## API surface
Public (app):
- `GET  /api/config` — bootstrap (categories + padas + theme)
- `GET  /api/categories`, `GET /api/padas`, `GET /api/tips`
- `GET  /api/vastu/lookup?category=<slug>&degree=<0-360>` — the core engine
- `POST /api/vastu/analyze` — same, JSON body
- `POST /api/submissions` — save a property scan; `GET /api/submissions/{id}`

Auth: `POST /api/auth/login` (form: username=email, password), `GET /api/auth/me`

Admin (Bearer token): `/api/admin/stats`, `/api/admin/users`,
`/api/admin/categories`, `/api/admin/padas`, `/api/admin/rules`
(+ `PUT /upsert/{category}/{pada}`), `/api/admin/tips`,
`POST /api/admin/uploads/image`.

## Deploy
Dockerfile + `render.yaml` included. Set `MONGODB_URL`, `SECRET_KEY` and the
Cloudinary vars, then run the seed + create_admin scripts once against the DB.
