FROM node:22-slim AS frontend-build
WORKDIR /src/frontend
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate
COPY frontend/package.json frontend/pnpm-workspace.yaml ./
COPY frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PORT=3000
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY public/ ./public/
COPY --from=frontend-build /src/frontend/dist ./frontend/dist
EXPOSE 3000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-3000}"]
