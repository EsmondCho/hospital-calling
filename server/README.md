# hospcall-server

Backend for **automated vet-clinic outreach (HOSPCALL)** — Dr.Tail's data collection
project that uses BlandAI voice calls to collect referral-fee policies and service
pricing from US local vet hospitals.

Linear project: [HOSPCALL](https://linear.app/drtail/project/local-vet-hospital-intelligence-hospcall-referral-fee-and-pricing-data-f6e40d6e6989/overview)

## Quick start

```bash
# 1. Build packages image
make build

# 2. Start PostgreSQL + Valkey
make prepare-datastore

# 3. Apply migrations (loads dummy data)
make migrate

# 4. Start API server (port 8002)
make server

# 5. (in another terminal) Start Celery worker + beat
make worker
```

API: http://localhost:8002 / Backoffice list: GET `/backoffice/calls/`.

See [`CLAUDE.md`](./CLAUDE.md) for the full convention index.

## Stack

Python 3.13 · Django 5.2 · DRF · PostgreSQL 17 · Valkey/Redis · Celery 5
· BlandAI · AWS (CDK, single `prod` env) · uv · Docker Compose
