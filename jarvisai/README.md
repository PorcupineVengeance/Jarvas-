# JARVIS — Personal AI Assistant

JARVIS is a modular personal AI assistant with a React/TypeScript frontend and a Python/FastAPI backend. The backend is the intelligence and automation layer; the frontend connects through documented REST and WebSocket APIs.

## What works now

- Configurable LLM chat (Groq / OpenAI-compatible) with SSE streaming and saved history
- Six assistant modes: normal, research, assistant, developer, automation, focus (+ auto)
- Local session auth for standalone use (Manus OAuth still supported when configured)
- Persistent tasks, memories, reminders (SQLite by default)
- DuckDuckGo web research (optional Tavily / Manus)
- Groq Whisper speech-to-text and Fish Audio text-to-speech when configured
- Local file upload/index/extraction (PDF, DOCX, XLSX, CSV, TXT, JSON, Markdown)
- Allow-listed tool registry with confirmation for write actions
- Optional local computer control (open apps/URLs/paths, screenshots, authorized file ops)
- System status, integrations readiness, WebSocket live chat events

Calendar and email remain integration-ready stubs until provider credentials are added. Wake-word continuous listening stays off unless explicitly enabled.

## Quick start (local)

```bash
cd jarvisai
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then edit with your keys
# Or use the local .env already prepared for Groq + Fish Audio

cd frontend
corepack prepare pnpm@11.25.0 --activate
pnpm install --frozen-lockfile
pnpm build
cd ..

PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Open http://localhost:3000 and choose **Continue locally**.

For frontend hot reload:

```bash
# terminal 1
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload

# terminal 2
cd frontend && pnpm dev
```

Vite proxies `/api` to port 3000. API docs: http://localhost:3000/docs

## Environment

Never commit `.env`. Placeholders live in `.env.example`.

| Variable | Purpose |
| --- | --- |
| `JARVIS_LLM_API_URL` / `JARVIS_LLM_API_KEY` / `JARVIS_LLM_MODEL` | OpenAI-compatible chat (e.g. Groq `https://api.groq.com/openai/v1`) |
| `JARVIS_STT_*` | Whisper-compatible transcription (Groq Whisper supported) |
| `JARVIS_TTS_PROVIDER` / `JARVIS_TTS_*` | `fish` or `openai` TTS |
| `JARVIS_LOCAL_AUTH_ENABLED` / `JARVIS_LOCAL_AUTH_SECRET` | Standalone cookie sessions |
| `JARVIS_RESEARCH_PROVIDER` | `duckduckgo` (default), `tavily`, or `manus` |
| `JARVIS_ENABLE_COMPUTER_CONTROL` | Local desktop automation |
| `JARVIS_ALLOWED_PATHS` | Comma-separated authorized directories |
| `DATABASE_URL` | Default `sqlite:///./data/jarvis.db` |
| `JARVIS_STORAGE_DIR` | Local uploads/reports directory |

**Security note:** If API keys were pasted into a chat, rotate them in the provider consoles and update `.env`.

## REST API (high level)

| Endpoint | Behavior |
| --- | --- |
| `POST /api/auth/local-login` | Create a local signed session cookie |
| `POST /api/chat` | SSE stream: `delta`, `status`, `done`, `error` |
| `GET/POST/PATCH/DELETE /api/tasks` | Task CRUD (delete requires `{confirmed:true}`) |
| `GET/POST/PATCH/DELETE /api/memory` | Memory CRUD (rejects credential-like text) |
| `GET/POST/DELETE /api/reminders` | Persistent reminders; `GET /due` fires due items |
| `GET /api/system/status` | Host metrics + provider readiness |
| `GET /api/integrations` | Truthful connector status |
| `GET /api/tools` + `POST /api/automation/execute` | Allow-listed tools |
| `POST /api/voice/transcribe` | Multipart audio → text |
| `POST /api/voice/speak` | Text → audio |
| `POST /api/research/search` | Live search via configured provider |
| `POST/GET/DELETE /api/files` | Upload, list, summarize, soft/local delete |
| `WS /api/ws` | Live chat, status, task snapshots |

Example chat body:

```json
{
  "message": "Research the top AI automation companies and summarize with sources.",
  "client_message_id": "unique-client-id",
  "mode": "research"
}
```

## Testing

```bash
cd jarvisai
.venv/bin/pytest -q
.venv/bin/python -m compileall -q backend
cd frontend && pnpm typecheck && pnpm build
```

## Project layout

```text
jarvisai/
├── backend/app/
│   ├── api/          # REST + WebSocket routers
│   ├── core/         # config, security, intelligence, permissions
│   ├── services/     # LLM, STT, TTS, research, computer, files, …
│   ├── tools/        # allow-listed tool registry
│   ├── memory/       # short/long-term helpers
│   ├── database/     # SQLAlchemy session
│   └── models.py
├── frontend/         # React interface (independent)
├── storage/          # local uploads (created at runtime)
├── data/             # SQLite database
├── .env.example
└── requirements.txt
```

## Known limitations

- Calendar and email need provider OAuth adapters before they can act.
- Wake-word detection is configuration-gated and not a full always-on service in this build.
- Computer control only runs when explicitly enabled on a trusted local machine and is limited to authorized paths.
- Hosted/cloud deployments must not claim personal desktop control without a local companion.
- DuckDuckGo results are snippet-level; deeper page analysis needs an explicit fetch step.
