![](./banner.png)

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-37814A?style=flat-square&logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-FF4438?style=flat-square&logo=redis&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=flat-square&logo=duckdb&logoColor=black)
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat-square&logo=langchain&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat-square&logo=openai&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-FF5533?style=flat-square&logo=qdrant&logoColor=white)
![MinIO](https://img.shields.io/badge/MinIO-C72E49?style=flat-square&logo=minio&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)

CityPilot is a conversational agent for anyone who works with urban data but does not want to live inside terminals, dashboards, or log systems. It turns city data into answers, briefings, maps, comparisons, and decisions — in plain language.

## Who it is for

**Policymakers** who need to justify decisions with evidence, compare options, and produce briefings for stakeholders — without touching a GIS tool or writing a SQL query.

**City administrators** who need to understand what is happening across departments, track service delivery, and flag problems before they escalate.

**Urban planners** who need to combine land use, transport, demographics, and environment data to model scenarios and assess impact.

**Researchers and analysts** who need to explore city datasets, run cross-domain queries, and produce summaries quickly.

**Journalists and civic advocates** who want to ask hard questions about public data and get answers they can verify and cite.

**Citizens** who want to understand what their city is doing and why.

The common thread: they all have questions about the city. CityPilot answers them.

## The problem it solves

Working with city data today is slow, manual, and fragmented — spreadsheets, GIS platforms, departmental reports, consultation documents, and budget tables that do not talk to each other. Getting a single coherent answer often takes days of coordination across teams.

CityPilot collapses that into a single interface.

## What policymakers can do with it

### Policy briefing

Ask a question like:

> "Why are bus delays increasing in the eastern districts and what are our options?"

Get back: what changed, where, likely causes, affected groups, historical trend, policy options with cost/risk/impact tradeoffs, evidence sources, and gaps in the data.

### Spatial analysis

Ask:

> "Which districts combine high elderly population, poor clinic access, high heat exposure, and low public transport coverage?"

CityPilot joins geospatial, demographic, health, transport, and climate layers to produce a ranked, mappable answer — without requiring the policymaker to touch a GIS tool.

### Public consultation summarizer

Given a set of consultation submissions, CityPilot surfaces:

- Main public concerns
- Recurring objections
- Stakeholder groups and their positions
- Regional differences in sentiment
- Issues flagged repeatedly by citizens

This compresses weeks of manual review into minutes.

### Policy option comparison

Ask:

> "Compare congestion pricing, bus priority lanes, and dynamic parking pricing for reducing traffic in the central business district."

Get a structured comparison of impact, cost, risk, timeframe, and political difficulty — with the assumptions made explicit so they can be challenged.

### Budget prioritization

Ask:

> "If we have a fixed budget for district-level climate resilience, where should we invest first?"

CityPilot ranks candidate projects by vulnerability, exposure, cost, implementation time, equity impact, and maintenance burden.

### Document and regulatory review

Ask questions across long policy documents:

> "What changed between the 2024 and 2025 version of this proposal?"
> "Which stakeholders objected to this clause?"
> "What are the implementation risks?"

## Architecture

CityPilot is built on the **dstack** — a personal hackathon-grade tech stack designed for fast deployment of full-featured web applications.

- **Backend**: FastAPI (Python)
- **Frontend**: Vite SPA
- **Task queue**: Celery + Redis
- **Database**: PostgreSQL
- **Object storage**: MinIO (S3-compatible)
- **Agent sandbox**: Daytona (isolated code execution per session)
- **Deployment**: Railway (fully Dockerized)

The agent runs as a background worker job with its own isolated execution environment. Each session gets a sandboxed copy of the relevant data, filtered by access rules before it reaches the agent. This means even an adversarial instruction to the agent cannot surface data it was not given — isolation is at the infrastructure layer, not the prompt layer.

## Live deployment

https://citypilot.up.railway.app
