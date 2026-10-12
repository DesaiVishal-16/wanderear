# Deploying WanderEar

WanderEar is local-first: everything the app *does* runs on your machine with no
network. The only thing you deploy is the **optional hosted gallery** — a small
service that serves the same web app and lets `wanderear sync <url>` push your
trail postcards somewhere browsable.

This guide covers the recommended host from [`docs/SERVICES.md`](docs/SERVICES.md):

| Service | Role | Required? |
|---|---|---|
| **Render** | Hosts the gallery + sync API (Docker) | Yes, for the hosted gallery |
| MongoDB Atlas | Cloud postcard store + Vector Search | Optional |
| Sentry | Latency/cost traces for the write-up | Optional |

The repo is already deploy-ready: [`render.yaml`](render.yaml) is a Render
Blueprint and [`deploy/Dockerfile`](deploy/Dockerfile) builds the service.

---

## 1. Docker (run it anywhere)

```bash
# build
docker build -f deploy/Dockerfile -t wanderear .

# run (postcards persist in a named volume)
docker run --rm -p 8000:8000 -e HOST=0.0.0.0 -v wanderear-data:/data wanderear
# → http://127.0.0.1:8000
```

Or with Compose:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

Health check: `curl http://127.0.0.1:8000/healthz` → `{"status": "ok"}`.

---

## 2. Deploy to Render (Blueprint)

Render's Hacktoberfest credit can fund the `starter` plan, which is the only
plan that supports a **persistent disk** at `/data` (so postcards survive
redeploys).

1. Push this repo to GitHub (see below).
2. Open <https://dashboard.render.com/blueprints> → **New Blueprint Instance**.
3. Select the `wanderear` repository. Render detects [`render.yaml`](render.yaml)
   at the repo root and shows the `wanderear-gallery` service.
4. (Optional, recommended) Set `WANDEREAR_SYNC_TOKEN` to a random secret.
   This locks the write endpoints so only you can push postcards. Generate one:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
5. Click **Apply**. Render builds the Docker image and gives you a URL like
   `https://wanderear-gallery.onrender.com`.
6. Verify:
   ```bash
   curl https://wanderear-gallery.onrender.com/healthz
   curl https://wanderear-gallery.onrender.com/api/status
   ```

### Push your postcards

```bash
# no token configured
wanderear sync https://wanderear-gallery.onrender.com

# token configured
WANDEREAR_SYNC_TOKEN=<the-same-secret> wanderear sync https://wanderear-gallery.onrender.com
```

Sync is idempotent — re-running only uploads new postcards.

### Free plan (no disk)

Free web services don't support disks. If you want $0 (and accept that the
gallery resets on every deploy/restart), edit `render.yaml`: change
`plan: starter` to `plan: free` and delete the `disk:` block.

---

## 3. Optional cloud multipliers

These stay opt-in and never block the offline path.

### MongoDB Atlas — durable store + Vector Search

1. Create a free M0 cluster at <https://www.mongodb.com/atlas>.
2. Add your Render service's outbound IP (or `0.0.0.0/0` for a demo) to Network
   Access, and create a database user.
3. Copy the connection string and set it as `WANDEREAR_MONGO_URI` on Render (and
   locally in `.env`).
4. Create an Atlas Vector Search index named `wanderear_vector` on the
   `wanderear.postcards` collection, field `embedding`, `numDimensions`
   matching your embedding length, similarity `cosine`.

`src/wanderear/atlas.py` already upserts to Atlas and falls back to client-side
cosine if the vector index is missing.

### Sentry — traces for the "where open beat closed" evidence

1. Create a project at <https://sentry.io> and copy the DSN.
2. Set `SENTRY_DSN` on Render (and locally). `src/wanderear/observability.py`
   wraps `classify` / `narrate` / `sync` in spans automatically.

---

## 4. What gets deployed

```
GitHub repo ──► Render Blueprint (render.yaml)
                     │
                     ├── deploy/Dockerfile   (python:3.12-slim + ffmpeg)
                     │      └─ pip install -e ".[server]"
                     └── web/server.py        (PORT from Render)
                            └─ disk /data       (index.jsonl + media/)
```

- `PORT` and `HOST` are read from the environment; Render injects `PORT`.
- `/healthz` is the health-check path.
- `WANDEREAR_SYNC_TOKEN`, when set, gates `POST /api/postcards` and
  `POST /api/media/*`. Reads and `POST /api/analyze` stay open.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails at `pip install` | Ensure `pyproject.toml` is committed (it is). |
| Analyze returns "could not read audio" | The image ships `ffmpeg`; if you changed the Dockerfile, keep it. |
| Gallery is empty after redeploy | You're on the free plan — postcards are ephemeral. Use a disk or Atlas. |
| `sync` returns 401 | Set the same `WANDEREAR_SYNC_TOKEN` locally as on Render. |
