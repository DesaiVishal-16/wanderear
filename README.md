# WanderEar 🍃👂

> **Shazam for the wild.** Record the world around you — wind, a creek, an owl at
> dusk, cicadas, rain on leaves — and get back a *sound postcard*: what you were
> actually hearing, written in words. Fully on-device, with **no signal needed**.

Built for the **Hacktoberfest × DEV "Touch Grass"** challenge (Week 1): an
open-source AI app that gets you off the screen and into the world.

---

## Why this exists

You are standing in a forest. Shazam can't help you — it only knows music and it
needs a server. Field-guide apps want Wi-Fi. The one moment you most want to know
*what am I hearing* is exactly the moment you have no bars.

WanderEar flips it: the model lives **on your device**, so the app works where
nature actually is. Press record, pocket the phone, listen, and later read the
postcard.

---

## How it works (30-second version)

```
   🎙 record 5–10s          🧠 classify (open audio model)      ✍️ narrate (local LLM)
   on-device mic    ───►     YAMNet / PANNs / CLAP      ───►     Gemma via Ollama
                                                                        │
                                     📮 sound postcard (text + wav + spectrogram)
```

Everything runs locally. The cloud is **optional and opt-in** (sync your
postcards, host the gallery). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Open-source AI is the whole point

This project only works *because* every AI component is open-weight and local:

| Requirement | Why a closed API fails | Why open wins |
|---|---|---|
| **Works on a trail** | Needs internet | Weights bundled, runs offline |
| **Privacy** | Uploads your backyard audio | Audio never leaves the device |
| **Cost** | Per-request billing | Zero marginal cost |
| **Swappable** | Locked to one vendor | Swap YAMNet ↔ CLAP ↔ BirdNET |
| **Hackable** | Can't retrain | Fine-tune on *your* biome |

This is the "where open beat closed" story the challenge asks for.

---

## Quickstart (local, offline)

```bash
# 1. Get an open-weight model running locally (one-time)
ollama pull gemma3:4b          # or gemma3n:e2b / gemma2:2b for low RAM

# 2. Install WanderEar
python -m venv .venv && source .venv/bin/activate
pip install -e ".[audio,plot]"

# 3. Check your setup
wanderear doctor

# 4. Record a soundscape and get a postcard
wanderear listen --seconds 8

# 5. Or classify an existing file
wanderear analyze path/to/recording.wav

# 6. Find a sound like this one (offline vector search)
wanderear search --like <postcard-id>
wanderear search --file another_clip.wav

# 7. Browse your postcards
wanderear gallery

# 8. Optional: sync to the hosted gallery
wanderear sync https://your-app.onrender.com
```

If no local model is available, WanderEar falls back to a **deterministic
template narrator** so the pipeline always works — the LLM just makes it prettier.

## Commands

| Command | What it does |
|---|---|
| `wanderear listen` | Record live audio → postcard (needs `sounddevice`) |
| `wanderear analyze <file>` | Classify a wav/flac/… → postcard |
| `wanderear watch` | Keep listening on an interval and log postcards |
| `wanderear list` / `show <id>` | Inspect saved postcards |
| `wanderear search --like <id>` / `--file <path>` | Offline similarity search |
| `wanderear gallery` | Build a self-contained HTML gallery |
| `wanderear sync <url>` | Upload postcards + media to the hosted gallery |
| `wanderear doctor` | Check mic, ffmpeg, Ollama, models, storage |

## Interactive web app

Prefer clicking to typing? Run the local web app and use it in your browser:

```bash
python web/server.py          # → http://127.0.0.1:8000
```

Then **record from your mic** or **upload a clip**, pick your ears (classifier)
and voice (narrator), and watch the postcard appear — with audio playback,
spectrogram, label chips, and a **"Find similar"** offline search. The same
server doubles as the hosted gallery for `wanderear sync`.

The page degrades gracefully: opened as a static file it becomes a read-only
gallery (recording/analysis need the local server).

---

## Project layout

```
wanderear/
├── src/wanderear/           # core package (local-first)
│   ├── audio.py             # capture + preprocess + features
│   ├── classify.py          # pluggable audio classifiers
│   ├── classifiers/         # yamnet · panns · clap (lazy, optional)
│   ├── embeddings.py        # offline soundscape vectors + similarity
│   ├── narrate.py           # pluggable narrators (Gemma / template)
│   ├── postcard.py          # postcard model + render
│   ├── store.py             # local store + vector search
│   ├── sync.py              # optional push to the hosted gallery
│   ├── atlas.py             # optional MongoDB Atlas + Vector Search
│   ├── pipeline.py          # shared audio→labels→narrate→store flow
│   ├── observability.py     # optional Sentry spans
│   └── cli.py               # `wanderear` command
├── web/                     # interactive app + optional hosted gallery
│   ├── index.html · app.js · style.css
│   └── server.py            # /api/analyze · /api/search · sync endpoints
├── Dockerfile               # container image (runs on any host)
├── render.yaml              # Render Blueprint (hosted gallery)
├── deploy/                  # docker-compose
├── data/field_guide/        # bundled offline nature glossary
├── docs/                    # architecture, plan, tasks, services (local)
└── tests/
```

## Deploy the hosted gallery

The optional gallery (what `wanderear sync` pushes to) is a single Docker
service built from the root [`Dockerfile`](Dockerfile).

```bash
# run it locally in Docker
docker compose -f deploy/docker-compose.yml up --build   # → http://127.0.0.1:8000

# or expose your local gallery on a public URL (no account, no card)
make serve      # terminal 1
make tunnel     # terminal 2 → prints a public https:// URL
```

Free, **no-credit-card** hosts: **Koyeb** (no sleep), **Back4app Containers**,
**SnapDeploy**. Render needs a card for web services (static sites are card-free)
and Hugging Face Docker Spaces became paid in July 2026.

### Deploy free without a card

The root [`Dockerfile`](Dockerfile) works on any container host. It binds
`0.0.0.0` and follows the platform's `PORT` env var.

**Koyeb — free, no sleep, usually no card**

1. Sign up at https://app.koyeb.com with GitHub.
2. **Create Service → GitHub** → pick `DesaiVishal-16/wanderear`.
3. Builder: **Dockerfile** (auto-detected at the repo root).
4. Instance: the free instance (Frankfurt or Washington, D.C.).
5. Port **8000**, health check path `/healthz`.
6. Optional secret `WANDEREAR_SYNC_TOKEN` to lock the write endpoints.
7. Deploy → `https://<app>-<org>.koyeb.app`.

```bash
curl https://<app>-<org>.koyeb.app/healthz
WANDEREAR_SYNC_TOKEN=<secret> wanderear sync https://<app>-<org>.koyeb.app
```

**Back4app Containers — free, explicitly no card**

1. Sign up at https://www.back4app.com and install the *Back4app Containers*
   GitHub app for `wanderear`.
2. **Create app → Containers**: branch `main`, root `/`, autodeploy on.
3. Env: `HOST=0.0.0.0`, `PORT=8000`, optional `WANDEREAR_SYNC_TOKEN`.
4. Deploy → `https://<app>-<id>.b4a.run`.

**Local + tunnel — instant, zero accounts**

```bash
make serve      # terminal 1 → http://127.0.0.1:8000
make tunnel     # terminal 2 → prints a public https:// URL
```

`scripts/tunnel.sh` uses `cloudflared` if installed, otherwise a free
`localhost.run` SSH tunnel. The URL lives while your machine and the tunnel do.

**Render (needs a card on file)**

`render.yaml` is a Blueprint with a persistent disk: Dashboard → **New →
Blueprint** → pick the repo → Apply. Free tier is ephemeral; `plan: starter`
supports the disk at `/data`.

> Free hosts use ephemeral storage, so postcards reset on redeploy. For durable
> postcards, point `WANDEREAR_MONGO_URI` at a free MongoDB Atlas cluster (no
> card) — see [`src/wanderear/atlas.py`](src/wanderear/atlas.py).

## Docs
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation plan](docs/PLAN.md)
- [Task checklist](docs/TASKS.md)
- [Prize service mapping](docs/SERVICES.md)
- [DEV write-up outline](docs/DEV_POST_OUTLINE.md)

## License
MIT — see [LICENSE](LICENSE).