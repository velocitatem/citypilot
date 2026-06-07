# HONESTY.md

> Mandatory disclosure for the hackathon. This file lives at the root of your repository. Judges cross-check it against your code and your technical video.
>
> **The deal:** disclosed shortcuts are **not** penalized — that is the entire point of this file. Hidden ones are. Undisclosed pre-built code is heavily penalized, each undisclosed mock carries a small penalty, and a faked demo is heavily penalized. Telling the truth here costs you nothing.

---

## 1. Team — who did what
Judges compare this against `git shortlog -sn`, so keep it honest.

| Member | GitHub handle | Main contributions |
|---|---|---|
| Daniel Rosel | velocitatem | Project scaffold, frontend/backend setup, session management, DB schema, seeding scripts, deployment, UI color/styling fixes |
| Armand Hubler | ahubler01 | Weather tools (forecasts, air quality, elevation, geocoding), news scraping (HKFP), HK open data dataset ingestion, Plotly charts |
| Noa Hoque | noahoque |  Preparing the business pitch and positioning, data source research   |

---

## 2. What is fully working
Features that run end-to-end on the live app, with real data and real logic. Be specific: name the feature, what input it takes, what output it produces.

- **Chat system** — user sends a natural-language prompt; OpenAI gpt-5 completion is streamed back token-by-token via Server-Sent Events
- **Research agent** — when the LLM determines a task needs deeper work, it spawns a Celery worker that runs an agentic loop inside a Daytona sandbox; real-time execution events are pushed to the frontend via a Redis stream
- **Weather tools** — live Open-Meteo API calls for 7-day forecasts, historical weather archive, air quality index (PM2.5, O3, NO2), and elevation lookups; input is a city/location name, output is structured data returned to the agent
- **News search** — HKFP articles are scraped daily, embedded with OpenAI `text-embedding-3-small`, and stored in Qdrant; semantic search returns relevant articles ranked by cosine similarity
- **HK open dataset discovery** — queries the data.gov.hk CKAN API and a Qdrant catalog index; downloads CSVs and runs DuckDB queries inside the sandbox; for the demo, data is served from a pre-populated Cloudflare R2 bucket (see Section 3)
- **Document generation** — agent produces PDF (WeasyPrint), DOCX (python-docx), and XLSX (xlsxwriter) files as downloadable artifacts
- **Plotly charting** — agent renders interactive charts as self-contained HTML artifacts displayed inline in the UI
- **Live Dashboard tab** — real ArcGIS Feature Service queries for live journey times, AQHI/PM2.5 air quality readings, and car park occupancy across Hong Kong
- **Conversation persistence** — all sessions, messages, agent runs, and artifacts are stored in PostgreSQL and survive page refresh; multi-turn conversations are fully supported
- **Event streaming** — agent execution steps (tool calls, intermediate results, errors) are streamed in real time from Redis to the frontend

---

## 3. What is mocked, stubbed, or hardcoded
Every shortcut. Examples: a login that accepts any password, a payment that always succeeds, an "AI" that is an if/else, a database that is an in-memory dictionary, fake JSON returned instead of a real API call.

**Undisclosed mocks carry a small penalty each. Anything you list here = free.**

| What is faked | Where (file:line or folder) | Why we mocked it | What the real version would do |
|---|---|---|---|
| HK open dataset CSV files pre-loaded into Cloudflare R2 | `apps/worker/r2_etl.py`, `apps/worker/sandbox_provider.py` | The data.gov.hk CKAN API has a strict rate limit that we hit late in development; to ensure a stable demo we pre-populated an R2 bucket with the relevant CSVs at a point-in-time snapshot | The real version would call the live CKAN API and historical archive endpoints on each agent run, fetching the latest available dataset versions in real time |

---

## 4. External APIs, services & data sources
Everything the project calls or pretends to call. Mark each as real or mocked.

| Service / API / dataset | Used for | Real call or mocked? | Auth (sandbox / test key / none) |
|---|---|---|---|
| OpenAI API (`gpt-5`, `text-embedding-3-small`) | Chat completions, streaming responses, news & dataset embeddings | Real | API key |
| Qdrant (cloud-hosted) | Vector search over HKFP news articles and HK open dataset catalog | Real | API key + URL |
| Open-Meteo | Weather forecasts, historical archive, air quality index, elevation | Real | None (public, no auth) |
| data.gov.hk CKAN API | Dataset catalog search and metadata lookup | Real (rate-limited; demo uses R2 snapshot — see Section 3) | None (public) |
| data.gov.hk historical archive | Versioned CSV/JSON dataset downloads | Real (rate-limited; demo uses R2 snapshot — see Section 3) | None (public) |
| Hong Kong Free Press (web scraping) | Daily ingestion of news articles via BeautifulSoup | Real | None (public) |
| Cloudflare R2 (S3-compatible API) | Storage and ETL source for HK open dataset CSVs used in demo | Real (pre-populated snapshot) | Access key / secret |
| ArcGIS REST Feature Services (HK gov) | Live journey times, AQHI, PM2.5, car park occupancy on the Live Dashboard | Real | None (public) |
| PostgreSQL | Session, conversation, message, run, and artifact persistence | Real | Connection string |
| Redis / Celery | Task queue for agent jobs, real-time event streaming to frontend | Real | URL |
| Daytona sandbox | Isolated code execution environment for the agent (DuckDB, document generation, charting) | Real | Docker-based |

---

## 5. Pre-existing code
Anything written **before** kickoff that we brought into this project: prior personal projects, forked open-source code, templates, boilerplate, internal libraries.

**Undisclosed pre-built code is heavily penalized. Anything you list here = free.**

| Item | Source (URL or description) | Roughly how much | License |
|---|---|---|---|
| Web app frontend/backend scaffold | Personal tech stack "dstack" — a generic scaffold for hackathon-style projects | ~30% of web app structure | Personal/proprietary |
| CRUD route boilerplate | Personal tech stack "dstack" — standard CRUD patterns from the same stack | Several standard create/read/update/delete routes | Personal/proprietary |
| LLM conversation management patterns | Personal tech stack "dstack" — previously used patterns for managing chat sessions, message history, and context handling with LLMs; aggregated from dstack by Claude Code via a genesis prompt and tailored to this solution; covers `apps/backend/services/chat.py` and `apps/backend/services/conversations.py` | Conversation threading, history storage, context windowing | Personal/proprietary |

---

## 6. Known limitations & next steps
What we would build next, and the weak spots we already know about. Naming these honestly is a strength, not a flaw.

- **data.gov.hk rate limiting** — the CKAN API rate limit was discovered late in development; the immediate fix was a pre-populated R2 snapshot for the demo. The real fix would be request throttling and caching in the MCP layer, or a dedicated scheduled sync job that keeps R2 up to date with the live catalog
- **Qdrant date filtering on news** — the KEYWORD index does not support range queries; news search falls back to a full collection scroll when date filtering is requested (`apps/worker/tools/news.py:95-103`), which is slower at scale
- **No retry/circuit-breaker on external APIs** — HKFP scraping has basic 429 backoff but no circuit breaker; OpenAI and Qdrant failures surface as unformatted errors rather than graceful degradation messages
- **Sandbox failure = run failed** — if Daytona sandbox provisioning fails there is no retry; the agent run is immediately marked as failed
- **R2 data is a point-in-time snapshot** — the CSV data served to the agent reflects the state of HK open datasets at the time of pre-population, not live values
