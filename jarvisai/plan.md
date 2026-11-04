# JARVIS — Implementation Plan

## Goal and scope

Create a functional JARVIS personal AI assistant in this new, initially empty project. The supplied JARVIS dashboard image is the visual reference for the interface. The UI and API will be separate components, connected only through documented HTTP and WebSocket contracts. This plan preserves the original requirement to avoid fake integrations: a capability is either genuinely wired to an available service/permission or clearly shown as unavailable/unconfigured.

The first usable release will include the designed responsive dashboard, authenticated application shell, a real configurable LLM chat path using the project-provided Manus AI service when available, task and memory CRUD backed by SQLAlchemy, real system-health reporting, a permission-checked tool registry, WebSocket events, API documentation, and speech transcription through the documented platform speech endpoint when its runtime service is available. Voice output, wake-word/continuous listening, external email/calendar, broad web research, unattended computer control, and persistent reminders depend on specific providers, local-device permissions, or published scheduled-work setup; these remain explicit adapter/configuration requirements rather than simulated success. Build integration contracts in modular form and surface readiness accurately. Do not use credentials pasted in chat.

## Implementation approach

- **Frontend:** React, TypeScript and a responsive CSS design system. It will provide Home, Chat, Voice, Tools, Settings and About areas; a living clock; truthful API/system status; accessible navigation; and working quick actions. Chat submission, voice transcription, task/memory flows and settings/status views call the backend. For image fidelity, use CSS and a small inline vector mark rather than turning the supplied screenshot into a flat, non-interactive background.
- **Backend:** Python FastAPI, Pydantic schemas and modular services. Keep route handlers thin; put reasoning, provider selection, safety and tool execution behind service interfaces. Serve the production-built frontend from the application server while keeping frontend source and backend logic in independent folders.
- **Persistence:** SQLAlchemy repositories. SQLite is the initial standalone/local default, with migrations and a driver/URL-based configuration that can support PostgreSQL later. In the managed Cloud runtime, the project currently has its managed database enabled and supplies a MySQL-compatible `DATABASE_URL`; the application will use that configured DSN when available, rather than silently persisting Cloud data to an ephemeral container file. Because Cloud development and publication share that database, schema changes must be additive and migrations deliberate. Tests use isolated SQLite databases, not the shared managed database.
- **AI and speech:** Use the server-only Manus service API (`MANUS_API_URL` / `MANUS_API_KEY`) for the default LLM route and documented transcription endpoint where available. Never expose these runtime credentials to browser code. Provider adapters remain replaceable. Additional provider keys, if later required, are added only through protected project secret input. LLM output is treated as untrusted; tools are allow-listed and permission-gated, and any consequential action requires explicit confirmation.
- **Authentication:** Use Manus OAuth as the default account provider, with server-validated sessions and the Preview-compatible session contract. A logged-out state is real; there is no development bypass or invented user. Access to private data is associated with the authenticated user.
- **Research and external integrations:** Implement interfaces for research, calendar, email, text-to-speech and computer/browser automation. Only activate a connector when its actual service and credentials/permissions exist. The application must report missing configuration precisely. The hosted Cloud app cannot directly manipulate the user's personal desktop; that capability needs an authorized local companion/agent and is not represented as complete in a web-only sandbox.
- **Uploads and reports:** Add validated backend upload handling and an application-owned metadata index. Use managed object storage where the documented runtime service is configured; do not treat a local container path as durable storage or promise deletion where the runtime interface only supports soft-delete/index removal.
- **API:** Document `POST /api/chat`, task and memory CRUD, `GET /api/system/status`, `POST /api/automation/execute`, speech transcribe/speak routes, authentication, upload/research surfaces, and a JSON-event WebSocket endpoint for streaming conversation and task/status updates. Publish request/response examples and safety/error semantics through the README and FastAPI OpenAPI UI.
- **Execution reliability:** Validate input/output, bound request times, classify transient vs permanent failures, use limited retries, log without secrets, return explicit success/failure states, persist task state, and support cancellation/status lookup where applicable. Never execute arbitrary shell text from a model or external content.

## Project structure

The project currently contains only its Git metadata. The planned structure is:

```text
jarvisai/
├── backend/
│   ├── app/main.py                 # FastAPI app, middleware, static frontend mount
│   ├── app/api/                    # REST and WebSocket routers
│   ├── app/core/                   # settings, auth, permissions, reasoning, orchestration
│   ├── app/schemas/                # validated API request/response/event schemas
│   ├── app/services/               # LLM, speech, research, files, integrations
│   ├── app/tools/                  # safe tool registry and independently replaceable tools
│   ├── app/memory/                 # context and long-term memory logic
│   ├── app/database/               # SQLAlchemy models, sessions, migrations/repositories
│   └── tests/                      # isolated API/service/database tests
├── frontend/
│   ├── src/components/             # shell, HUD, cards, accessible controls
│   ├── src/pages/                  # Home, Chat, Voice, Tools, Settings, About
│   ├── src/lib/                    # typed REST/WebSocket client
│   └── src/styles/                 # tokens, layout, responsive and motion styles
├── public/manus-routes.json        # source-derived page route declaration
├── .env.example                    # names and placeholders only
├── .gitignore                      # excludes .env, secrets, data, build and caches
├── Dockerfile                      # clean-checkpoint production build and API entrypoint
├── pyproject.toml                  # pinned Python dependencies and project metadata
├── frontend/package.json           # pinned Node package manager/toolchain and scripts
├── frontend/pnpm-lock.yaml
├── plan.md
├── TODO.md                         # created only after plan approval
└── README.md                       # setup, API, security, coverage and known limitations
```

## Design system (from the supplied image)

- **Design movement:** Futuristic command-center HUD, restrained rather than ornamental.
- **Core principles:** Operational clarity; signal-like red used with discipline; telemetry that is honest and legible; controls that visibly do what they say.
- **Color philosophy:** Near-black surfaces recede so the user’s conversation and live system state lead. Bright JARVIS red identifies focus, active navigation and command affordances; pale gray carries hierarchy; green is reserved for verified online/connected state, never decorative success.
- **Layout paradigm:** Persistent slim left rail, wide central console with greeting and segmented circular HUD, compact right-side status/quick-action rail, and a grounded bottom command bar. On narrow screens, rails collapse into accessible navigation and stack without hiding the core conversation.
- **Signature elements:** Angular red perimeter/edge cuts; segmented circular JARVIS telemetry ring; fine red connector traces and restrained glow.
- **Interaction philosophy:** State changes are explicit and truthful. Quick actions navigate to real capabilities; uncertain/unconfigured actions explain what is required. Keyboard focus, disabled state, loading, errors and reduced-motion preferences are first-class.
- **Animation:** Short 150–250 ms transitions for focus and panel changes; slow low-amplitude ring movement only when useful; no fake activity indicators; respect `prefers-reduced-motion` and never use motion to imply an integration is connected.
- **Typography:** Space Grotesk-style geometric headings with Inter-style neutral UI/body text and tabular numerals for time and metrics; use packaged/local fonts with sans-serif fallbacks so the interface does not depend on third-party font requests.
- **Brand essence:** A calm command console for people who want a capable, inspectable personal assistant; **precise, composed, dependable**.
- **Brand voice:** Calm, concise, professional, confident, and lightly witty only when appropriate. Example lines: “Systems ready. What should we handle next?” and “I can’t reach that service yet; configure its connection and I’ll try again.”
- **Wordmark and logo:** A compact, custom angular red J/chevron signal mark paired with a tracked uppercase JARVIS wordmark, drawn as vector/CSS rather than using a default text treatment alone.
- **Signature brand color:** Signal red `#f0183c`, supported by ink black, charcoal, soft white, and status green.

## Build sequence and delivery boundary

1. After this plan is approved, create `TODO.md` with outcome-based criteria carried from the original brief, retaining all concrete constraints and marking work open until evidence exists.
2. Configure TypeScript, JavaScript, Python, HTML and CSS diagnostics before the first application-code batch; pin dependencies and lockfiles before installing.
3. Implement the API/data/auth foundation and typed frontend shell together, then real chat, memory, tasks and status paths; continue with speech, safe tool orchestration, file/research adapters and documented integration states.
4. Add deployment/runtime declarations that match the app and verify health with the server running. Do not publish unless separately requested. Do not write test data into the shared Cloud database; use isolated SQLite for tests.
5. Run focused automated checks and one requirements/architecture review, correct confirmed defects, then save the completed work as a project checkpoint. Report which provider-dependent capabilities are active versus awaiting credentials, permissions or publication.

## Decisions and constraints needing approval

This plan assumes (a) Manus AI is the default LLM because the project runtime supplies the managed service, with external providers added through secure configuration; (b) Manus OAuth is the login provider because none was specified; (c) SQLite is used for standalone/local development while the already-enabled managed MySQL-compatible database is used in Cloud when its DSN is present, with PostgreSQL compatibility in the SQLAlchemy adapter; and (d) this pass delivers a complete usable dashboard and real core assistant flows, while external integrations and personal-desktop control are activated only when their actual provider/permissions are configured. No pasted chat credential will be embedded or reused.