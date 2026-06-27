FROM python:3.13-slim

WORKDIR /app

# Install build essentials for any C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN mkdir -p app && touch app/__init__.py

RUN pip install --no-cache-dir .

COPY app/ ./app/
COPY .env.defaults .

RUN mkdir -p /app/uploads

# Run Celery worker with concurrency=2
CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
