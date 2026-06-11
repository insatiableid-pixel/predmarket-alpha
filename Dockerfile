# Multi-stage Dockerfile for predmarket-alpha
# Build: docker build -t predmarket .
# Run:   docker run -p 8050:8050 --env-file .env predmarket

# ---- Builder stage ----
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Create data directory
RUN mkdir -p /app/data/raw /app/data/processed

EXPOSE 8050

# Run Alembic migrations, then start the platform
CMD ["sh", "-c", "alembic upgrade head && python main.py"]
