FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY backend ./backend
COPY migrations ./migrations

RUN python -m pip install --no-cache-dir . \
    && addgroup --system bid-system \
    && adduser --system --ingroup bid-system bid-system

USER bid-system

CMD ["python", "-m", "uvicorn", "bid_system.entrypoints.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
