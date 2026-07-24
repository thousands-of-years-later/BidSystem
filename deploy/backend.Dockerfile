FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY backend ./backend
COPY migrations ./migrations

RUN apt-get -o Acquire::Retries=10 -o Acquire::http::Pipeline-Depth=0 update \
    && apt-get -o Acquire::Retries=10 -o Acquire::http::Pipeline-Depth=0 \
        install --no-install-recommends --yes \
        fontconfig \
        fonts-noto-cjk \
        libreoffice-impress \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir . \
    && addgroup --system bid-system \
    && adduser --system --ingroup bid-system bid-system

RUN install -d -o bid-system -g bid-system /home/bid-system

ENV HOME=/home/bid-system

USER bid-system

CMD ["python", "-m", "uvicorn", "bid_system.entrypoints.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
