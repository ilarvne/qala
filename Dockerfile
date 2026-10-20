FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig*.json components.json ./
COPY src ./src
COPY public ./public
COPY data/voice-languages.json ./data/voice-languages.json
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000 QALA_MEMORY_PATH=/app/var/preferences.sqlite3
WORKDIR /app
COPY requirements.lock.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.lock.txt \
    && useradd --create-home --uid 10001 qala
COPY backend ./backend
COPY data ./data
COPY --from=frontend /build/dist ./dist
RUN mkdir -p /app/var && chown -R qala:qala /app
USER qala
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8000') + '/api/health', timeout=4)"
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]

