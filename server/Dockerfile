# Single image shared by the django / celery-worker / celery-beat services
# (each overrides the command in docker-compose.yml). Deps are installed from
# pyproject.toml — the single source of truth — with uv.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer) — only pyproject changes bust it.
COPY pyproject.toml ./
RUN uv pip install --system --break-system-packages -r pyproject.toml

# App code is bind-mounted in docker-compose for live editing, but copy it so
# the image also runs standalone.
COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8002

CMD ["python", "manage.py", "runserver", "0.0.0.0:8002"]
