FROM python:3.12-slim

WORKDIR /app

# Runtime tools only (curl for healthcheck, git/rsync/ripgrep for workspace ops)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    rsync \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1

# Non-root runtime user
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /opt/data \
    && chown -R appuser:appuser /app /opt/data
USER appuser

EXPOSE 8642

HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8642/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8642"]
