FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5500 \
    PUBLIC_URL=http://127.0.0.1:5500

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# Saves, cache and the ~17 GB of game assets (downloaded on first start). See docker-entrypoint.sh.
VOLUME ["/data"]

EXPOSE 5500

ENTRYPOINT ["/app/docker-entrypoint.sh"]
