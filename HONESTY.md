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

---

## 2. What is fully working
Features that run end-to-end on the live app, with real data and real logic. Be specific: name the feature, what input it takes, what output it produces.

-
-
-

---

## 3. What is mocked, stubbed, or hardcoded
Every shortcut. Examples: a login that accepts any password, a payment that always succeeds, an "AI" that is an if/else, a database that is an in-memory dictionary, fake JSON returned instead of a real API call.

**Undisclosed mocks carry a small penalty each. Anything you list here = free.**

| What is faked | Where (file:line or folder) | Why we mocked it | What the real version would do |
|---|---|---|---|
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |

If nothing is mocked, write: *"Nothing is mocked — every feature listed above uses real logic and real data."*

---

## 4. External APIs, services & data sources
Everything the project calls or pretends to call. Mark each as real or mocked.

| Service / API / dataset | Used for | Real call or mocked? | Auth (sandbox / test key / none) |
|---|---|---|---|
|  |  |  |  |
|  |  |  |  |

---

## 5. Pre-existing code
Anything written **before** kickoff that we brought into this project: prior personal projects, forked open-source code, templates, boilerplate, internal libraries.

**Undisclosed pre-built code is heavily penalized. Anything you list here = free.**

| Item | Source (URL or description) | Roughly how much | License |
|---|---|---|---|
| Web app frontend/backend scaffold | Personal tech stack "dstack" — a generic scaffold for hackathon-style projects | ~30% of web app structure | Personal/proprietary |
| CRUD route boilerplate | Personal tech stack "dstack" — standard CRUD patterns from the same stack | Several standard create/read/update/delete routes | Personal/proprietary |
| LLM conversation management patterns | Personal tech stack "dstack" — previously used patterns for managing chat sessions, message history, and context handling with LLMs; aggregated from dstack by Claude Code via a genesis prompt and tailored to this solution | Conversation threading, history storage, context windowing | Personal/proprietary |

---

## 6. Known limitations & next steps
What we would build next, and the weak spots we already know about. Naming these honestly is a strength, not a flaw.

-
-
-
