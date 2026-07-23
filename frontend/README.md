# TTTI AMS — React + Vite Frontend

Production frontend for the Thika Technical Academic Management System.

## Stack

- React 18 + Vite
- React Router (lazy route-level code splitting)
- TanStack Query
- Axios (`withCredentials` session cookies)
- Tailwind CSS 4
- Framer Motion (selective)
- Chart.js / Recharts
- Socket.IO client (opt-in via `VITE_SOCKET_URL`)
- React Player (available for media screens)

## Architecture

```
React + Vite
  → React Router (lazy portals)
  → TanStack Query
  → Axios (`src/lib/apiClient.ts`)
  → Flask `/api/v1/*`
  → Supabase Auth + PostgreSQL + Storage
```

Existing Jinja portals remain available. This SPA is migrated incrementally
**without changing the visual design language** (same tokens, sidebar, login layout).

## Local development

1. Start Flask API (repo root):

```bash
pip install -r requirements.txt
flask --app app run -p 5000
```

2. Start Vite (this folder):

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/static` to Flask.

## Environment

Copy `.env.example` to `.env`:

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Empty in local (use Vite proxy). Production: Flask origin e.g. `https://api.example.com` |
| `VITE_LEGACY_ORIGIN` | Flask origin for not-yet-migrated pages |
| `VITE_SOCKET_URL` | Optional Socket.IO server |

Flask side (repo root `.env`):

| Variable | Purpose |
|---|---|
| `SPA_ORIGINS` | Comma-separated SPA origins (default localhost:5173) |
| `SPA_CROSS_SITE` | `true` when SPA and API are on different HTTPS domains |

## Production build

```bash
npm run build
```

Deploy `dist/` to a static host (Render Static Site, Netlify, etc.). Point
`VITE_API_BASE_URL` at the Flask API. Enable CORS via `SPA_ORIGINS`.

## Migration status

| Area | Status |
|---|---|
| Auth login (staff + trainee) | Done |
| Trainer dashboard (parity UI) | Done |
| Other trainer screens | Placeholder → legacy Flask |
| Other portals | Scaffolded routing / next increments |

Jinja routes are **not** removed. Do not delete templates until each screen is ported and verified.
