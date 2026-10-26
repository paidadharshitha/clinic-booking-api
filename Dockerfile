FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BOOKING_DB_PATH=/app/data/bookings.db

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY clinic_api ./clinic_api
RUN python -m pip install --no-deps . \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "clinic_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
