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

# Create a system user and group to run the app securely as non-root
RUN groupadd -r appgroup && useradd -r -g appgroup -u 10001 appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Create data directories and change owner to appuser
RUN mkdir -p /app/data/raw /app/data/processed && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8050

# Run Alembic migrations, then start the platform
CMD ["sh", "-c", "alembic upgrade head && python main.py"]
