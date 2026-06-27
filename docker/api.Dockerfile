FROM python:3.13-slim

WORKDIR /app

# Install build essentials for any C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifest first for better layer caching
COPY pyproject.toml .

# Create minimal package stub so hatchling can install deps without the full source
RUN mkdir -p app && touch app/__init__.py

RUN pip install --no-cache-dir .

# Now copy full source (invalidates only on source changes, not dep changes)
COPY app/ ./app/
COPY alembic.ini .
COPY .env.defaults .

# Create uploads directory
RUN mkdir -p /app/uploads

# Run DB migrations then start the API server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
