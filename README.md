# Hospital Calling — automated vet-clinic outreach

A small full-stack system that **sources US veterinary clinics, classifies
them, and runs scheduled outbound voice-AI phone calls** to collect
information on a mission (e.g. *"find the earliest puppy-vaccination
appointment within a week"*).

It is a trimmed, self-contained copy of an internal Dr.Tail project, packaged
so you can run the whole thing locally with one command and click through real
seeded data.

```
┌──────────────┐      ┌──────────────────────┐      ┌─────────────────┐
│  Backoffice  │ ───▶ │  Django REST API     │ ───▶ │  PostgreSQL     │
│  (Next.js)   │      │  + Celery workers     │      │  Redis (broker) │
└──────────────┘      └──────────┬───────────┘      └─────────────────┘
                                  │
              ┌───────────────────┼────────────────────┐
              ▼                   ▼                     ▼
       Google Places         Anthropic (Claude)      Bland.ai
       (source clinics)      (classify clinics)      (place the calls)
```

## What it does

1. **Sourcing** — sweeps a city/region via Google Places and stores every vet
   clinic it finds.
2. **Classification** — a rule pass (regex **Chain Keywords** like `VCA`,
   `Banfield`, `NVA`…) plus a Claude pass label each clinic's *ownership*
   (INDEPENDENT / MARS_VH / CHAIN / RETAIL_EMBEDDED …) and *service tags*.
3. **Prompts** — versioned call missions (the "task" the voice agent runs).
4. **Schedules** — a campaign fans out to an ordered list of clinics and dials
   them **sequentially** via Bland.ai; results (recording, transcript,
   summary) come back through a webhook.
5. **Backoffice** — operator UI to browse/curate hospitals, chain keywords,
   prompts, schedules, and call logs.

## Quick start

Requires **Docker** (Compose v2). Nothing else — no Python/Node/DB install.

```bash
git clone <this-repo>
cd hospital-calling
make up            # builds images, starts everything, runs migrations + seed
```

First boot builds two images and installs deps (~2–4 min). When it settles:

| Service        | URL                              |
|----------------|----------------------------------|
| **Backoffice** | http://localhost:3000            |
| API            | http://localhost:8002            |
| API health     | http://localhost:8002/health/    |
| Django admin   | http://localhost:8002/admin/ (`make createsuperuser`) |

### Login

The backoffice is gated by a simple login. Use:

```
username: demo
password: hospcall2026
```

(Change via `BASIC_AUTH_USERS` in a root `.env` — see `.env.example`.)

### What to explore

The database is **pre-seeded** so every screen has content:

- **Hospitals** — 14 clinics across several US states, a mix of independent
  practices and chains/retail.
- **Chain Keywords** — the regex rule set (VCA, Banfield, NVA, Thrive…) that
  drives chain labeling. See how `VCA Westside` and `Banfield` got tagged
  `MARS_VH`.
- **Prompts** — the mission *"earliest puppy-vaccination appointment within a
  week"* for a 14-week-old Golden Retriever puppy named Bella.
- **Schedules** — 2 pending campaigns, each dialing an ordered clinic
  sequence. (No call has been placed — see note below.)

## Common commands

```bash
make up            # build + start everything
make down          # stop
make clean         # stop + delete the DB volume (fresh seed next time)
make logs          # tail all logs

make django        # start API only (runs migrations + seed)
make celery        # start Celery worker + beat only
make backoffice    # start the Next.js UI only

make migrate       # apply migrations / re-seed
make shell         # Django shell
```

## Live features (optional)

The demo is fully browsable **read-only with no keys**. To exercise the live
integrations, copy `.env.example` to `.env` and fill in any of:

| Key                     | Enables                                  |
|-------------------------|------------------------------------------|
| `GOOGLE_PLACES_API_KEY` | Sourcing real clinics from Google        |
| `ANTHROPIC_API_KEY`     | Claude classification of sourced clinics |
| `BLANDAI_API_KEY`       | Placing the actual outbound phone calls  |

Then `make up` again.

## Notes for reviewers

- **Seeded phone numbers are fictitious** (the reserved `555-01xx` range) on
  purpose — even with a Bland.ai key, firing a schedule will not call a real
  clinic.
- **No real call data ships.** Seeded campaigns are `PENDING` with no
  recordings or transcripts.

## Tech stack

Python 3.13 · Django 5.2 · DRF · Celery · PostgreSQL 17 · Redis ·
Next.js 16 / React 19 · Tailwind · Bland.ai · Google Places · Anthropic Claude.
