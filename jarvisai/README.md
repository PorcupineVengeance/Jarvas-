# JARVIS — Personal AI Assistant

JARVIS is a red-on-black command-console web app with a separate React/TypeScript frontend and Python/FastAPI backend. It is designed as a real, permission-aware system: connected services are called for real, and unavailable capabilities are labeled as unavailable rather than simulated.

## Current capabilities

The project implements the JARVIS dashboard, Manus OAuth session gate, server-only managed LLM chat with SSE streaming and saved conversation history, six selectable assistant modes, user-scoped task CRUD, persistent user-scoped memory with credential-pattern rejection, system/resource status, a small allow-listed tool registry with audit entries, real-time WebSocket chat events, browser recording followed by server-side speech transcription, configurable OpenAI-compatible TTS, file upload/index/extraction for PDF/DOCX/XLSX/CSV/TXT/JSON/Markdown using managed object storage, and a configurable API Hub research adapter.

Calendar and email connectors, wake word/continuous listening, persistent reminder scheduling, and personal desktop/browser automation are not represented as connected. They need their specific provider configuration, publication/schedule setup, or a separately authorized local companion. File removal hides an indexed item; the runtime storage interface does not provide physical object deletion. Check **Tools & Files** for current connection readiness.

## Architecture

- `frontend/`: React, TypeScript, Vite, local Space Grotesk/Inter fonts, responsive dashboard, typed REST/SSE client and route pages.
- `backend/app/api/`: authentication, chat, tasks, memory, status, voice, tools, files, research and WebSocket endpoints.
- `backend/app/core/`: runtime settings, provider state and session/origin security.
- `backend/app/database/` and `backend/app/models.py`: SQLAlchemy persistence for accounts, conversations, tasks, memories, files and tool audit events.
- `backend/app/services/`: provider adapters (LLM streaming now; other integrations only when configured).
- `public/manus-routes.json`: static manifest of the interface routes.

Standalone/local execution defaults to SQLite at `data/jarvis.db`. In managed Cloud, the application uses the configured `DATABASE_URL` when present; the current managed database is MySQL-compatible. SQLAlchemy URL normalization supports PostgreSQL DSNs for future use. Cloud development and production share the project database, so do not use it for destructive tests or casual test data.

## Installation and local run

Requirements: Python 3.12+, Node 22+, and the project-pinned pnpm 11.25.0.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
cd frontend
corepack prepare pnpm@11.25.0 --activate
pnpm install --frozen-lockfile
pnpm build
cd ..
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3000
```

The Cloud Preview app listens on port 3000. For interface development, Vite can run at port 5173 and proxies `/api` to the backend on 3000; rebuilding with `pnpm build` refreshes the static frontend served by FastAPI. API documentation is available at `/docs`; health is `/api/health`.

## Environment and credentials

The managed Cloud runtime supplies `MANUS_API_URL`, `MANUS_API_KEY`, OAuth values and `DATABASE_URL` according to the project contracts. They are read server-side only. For local standalone development, configure the applicable variables in `.env`; keep `.env` out of version control. `.env.example` contains names/placeholders only. Never put secrets in a chat, memory, browser bundle, URL, log or commit. The credentials previously pasted into the conversation are not used by this code.

Optional adapters:

- `JARVIS_RESEARCH_API_ID`: an API Hub identifier for a supported search endpoint. The query argument may need to match that registered API's contract.
- `JARVIS_TTS_API_URL`, `JARVIS_TTS_API_KEY`, `JARVIS_TTS_MODEL`, and optional `JARVIS_TTS_VOICE`: configure a compatible TTS service. Store the key through protected project settings rather than source.
- `JARVIS_ALLOWED_ORIGINS`: comma-separated exact HTTPS origins when the published site uses an origin other than this project's Preview URL. Localhost dev origins are allowed for development; non-local sign-in requires an allow-listed exact origin.

## REST and realtime API

Protected application routes require the `webdev_app_session` cookie from a validated Manus OAuth session.

| Method and path | Behavior |
| --- | --- |
| `GET /api/auth/config` / `/api/auth/session` | Report real login-provider availability and current session state. |
| `GET /api/auth/login?origin=…`, `GET /api/auth/callback` | Manus OAuth with nonce-bound state and server-validated session cookie. |
| `POST /api/auth/logout` | Clear the application session. |
| `POST /api/chat` | Accept `{message, conversation_id?, client_message_id, mode}` and stream SSE `delta`, `done` or `error` events. |
| `GET /api/chat/conversations` / `GET /api/chat/conversations/{id}` | List and retrieve only the signed-in user's conversation records. |
| `POST /api/tasks`, `GET /api/tasks` | Create/list owned tasks. `PATCH /api/tasks/{id}` updates; `DELETE /api/tasks/{id}` requires `{ "confirmed": true }`. |
| `POST /api/memory`, `GET /api/memory` | Create/list owned memories. `PATCH` and `DELETE /api/memory/{id}` edit/remove them. Credentials are rejected. |
| `GET /api/system/status`, `GET /api/integrations`, `GET /api/tools` | Return actual status, connector readiness and registered safe tools. |
| `POST /api/automation/execute` | Run only a registered operation with validated arguments; write tools require `{ "confirmed": true }`. |
| `POST /api/voice/transcribe` | Multipart audio upload, limited by `JARVIS_MAX_UPLOAD_MB`, forwarded to the configured transcription service. |
| `POST /api/voice/speak` | Accept `{text, voice?, speed?}` and return audio only when a TTS provider is configured. |
| `POST /api/research/search` | Query a configured API Hub provider; returns its actual raw result. |
| `POST /api/files`, `GET /api/files` | Upload/index and list owned supported documents in managed storage. `GET /api/files/{id}` returns extracted text; `GET /api/files/{id}/download` issues an authorized temporary download; `DELETE` soft-hides the record. |
| `WS /api/ws` | Events: client `chat.message`; server `assistant.status`, `assistant.delta`, `assistant.done`, `task.status` and `error`. Cookie and Origin are validated. |
| `GET /api/health`, `GET /manus-routes.json` | Unauthenticated health and static website route manifest. |

Example chat request:

```json
{"message":"Help me break this project into three tasks.","client_message_id":"<unique-client-generated-id>","mode":"assistant"}
```

SSE emits `event: delta` with `{"text":"…"}` as text arrives, followed by `event: done` with the persisted conversation identifier. Provider failures emit `event: error`; the user's input stays available to retry. The `client_message_id` prevents duplicate saving on a retry.

## Testing and checks

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q backend
cd frontend && pnpm typecheck && pnpm build
```

Tests use isolated SQLite. Do not run migration or destructive tests against the Cloud `DATABASE_URL`. The route manifest is served at `GET /manus-routes.json` and lists `/`, `/chat`, `/voice`, `/tools`, `/settings`, `/about`.

## Security and known limitations

The service uses a bounded in-process API rate limiter; production multi-instance deployments should add a shared rate-limit backend before high-traffic use. Application data is scoped by authenticated user. File uploads have format/size checks and store extracted text for indexing; highly untrusted office/PDF files should still be reviewed before automated action. Tool calls are allow-listed, permissions are checked and the model does not get arbitrary OS/shell access. Task and file deletion behaviors require confirmation in the UI/API; physical stored-object removal is not supported by the runtime API.

Persistent scheduling is not activated until a handler is published and a schedule registered. Calendar, email, third-party research, wake-word listening and local computer control require additional provider credentials or permissions. No external credentials were embedded. Publish is intentionally not performed unless separately requested.
#   J a r v a s -  
 