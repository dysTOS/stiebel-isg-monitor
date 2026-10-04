FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STIEBEL_DB_PATH=/app/data/measurements.sqlite3 \
    STIEBEL_WEB_LISTEN=0.0.0.0 \
    STIEBEL_WEB_PORT=8081

WORKDIR /app
COPY pyproject.toml ./
COPY stiebel_monitor ./stiebel_monitor
RUN pip install --no-cache-dir . \
    && useradd --system --create-home --uid 10001 monitor \
    && mkdir -p /app/data \
    && chown monitor:monitor /app/data

USER monitor
EXPOSE 8081
CMD ["stiebel-monitor", "serve", "--listen", "0.0.0.0", "--web-port", "8081"]
