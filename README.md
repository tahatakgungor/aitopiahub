# aitopiahub

> AI-powered content automation platform — generates, schedules, and publishes multi-format content (video, posts, stories) to social channels using LLMs, TTS, and trend intelligence.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![Groq](https://img.shields.io/badge/LLM-Groq%20%7C%20Ollama-orange)
![Celery](https://img.shields.io/badge/Queue-Celery%20%2B%20Redis-red?logo=redis)
![PostgreSQL](https://img.shields.io/badge/DB-PostgreSQL%20%2B%20pgvector-336791?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

---

## Overview

aitopiahub eliminates manual content workflows. Given a set of topics and publishing schedules, it autonomously:

1. **Detects trending topics** (Google Trends, Reddit, RSS feeds)
2. **Generates scripts** using LLMs (Groq Llama 3.3 70B for quality, 8B for speed — automatic Ollama fallback)
3. **Synthesizes voice** (Edge-TTS / Piper-TTS with multilingual support)
4. **Assembles video** (MoviePy — script + voice + visuals → MP4)
5. **Applies safety checks** before publishing (content quality gates, deduplication via pgvector)
6. **Publishes to channels** (YouTube uploads via Google API, cross-platform posting)
7. **Monitors** production health (Prometheus metrics, structured logging)

Designed for teams managing multiple content channels at scale without per-post manual work.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Backend                      │
│  /episodes  /schedules  /analytics  /health              │
└────────────────────────┬────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │    Celery Workers    │   ← Redis broker
              │  ┌───────────────┐  │
              │  │ content_tasks │  │   Episode generation
              │  │ youtube_tasks │  │   Upload & publish
              │  │ trend_tasks   │  │   Topic discovery
              │  │ publish_tasks │  │   Cross-platform post
              │  │ ops_tasks     │  │   Monitoring, cleanup
              │  └───────────────┘  │
              └──────────┬──────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
  ┌─────▼─────┐  ┌───────▼──────┐  ┌────▼────────┐
  │  LLMClient │  │  VideoEngine │  │  PostgreSQL  │
  │  Groq 70B  │  │  Edge-TTS    │  │  + pgvector  │
  │  Groq  8B  │  │  Piper-TTS   │  │  + Alembic   │
  │  Ollama ↩  │  │  MoviePy     │  │  migrations  │
  └────────────┘  └──────────────┘  └─────────────┘
```

**LLM fallback chain:** Groq 70B → Groq 8B → Ollama (local) — zero downtime on API rate limits.

---

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| **API** | FastAPI + Uvicorn | Async REST endpoints |
| **Task Queue** | Celery + Redis + RedBeat | Distributed job scheduling |
| **LLM** | Groq (Llama 3.3 70B / 3.1 8B) + Ollama | Script & post generation |
| **TTS** | Edge-TTS, Piper-TTS | Multilingual voice synthesis |
| **Video** | MoviePy + FFmpeg | Script → narrated video assembly |
| **Image Gen** | Pollinations API | Scene thumbnails & visuals |
| **Database** | PostgreSQL + SQLAlchemy (async) + pgvector | Persistence + semantic dedup |
| **Migrations** | Alembic | Schema versioning |
| **Embeddings** | sentence-transformers | Content similarity / dedup |
| **Trends** | pytrends + PRAW + feedparser | Topic discovery |
| **Publishing** | Google API (YouTube) | Automated video uploads |
| **Monitoring** | Prometheus + structlog | Metrics + structured logs |
| **Config** | pydantic-settings | Type-safe environment config |
| **Testing** | pytest + pytest-asyncio | Async test suite |

---

## Key Features

- **Multilingual content** — generates and narrates in any language supported by Edge-TTS
- **Cost-aware LLM routing** — 70B for episode scripts, 8B for fast classification tasks
- **Semantic deduplication** — pgvector embeddings prevent near-duplicate content
- **Quality gates** — audio/visual scoring thresholds block low-quality episodes before publish
- **Content calendar** — recurring schedule management with Celery Beat
- **Hashtag optimizer** — data-driven hashtag selection per platform
- **Structured observability** — Prometheus metrics + JSON-structured logging in prod

---

## Getting Started

### Prerequisites
- Python 3.11+, Docker, Docker Compose
- Groq API key ([console.groq.com](https://console.groq.com))
- Google Cloud credentials (YouTube Data API v3)

### Setup

```bash
git clone https://github.com/tahatakgungor/aitopiahub
cd aitopiahub

# Copy and fill environment variables
cp .env.example .env

# Install dependencies
pip install poetry
poetry install

# Start infrastructure (PostgreSQL + Redis)
docker compose -f docker/docker-compose.yml up -d postgres redis

# Run database migrations
alembic upgrade head

# Start API server
uvicorn src.aitopiahub.main:app --reload

# Start Celery worker (separate terminal)
celery -A src.aitopiahub.tasks.celery_app worker --loglevel=info

# Start Celery beat scheduler (separate terminal)
celery -A src.aitopiahub.tasks.celery_app beat --scheduler celery_redbeat.RedBeatScheduler
```

---

## Project Structure

```
aitopiahub/
├── src/
│   ├── aitopiahub/
│   │   ├── content_engine/     # LLM client, episode manager, content calendar
│   │   │   ├── llm_client.py   # Groq/Ollama wrapper with automatic fallback
│   │   │   ├── episode_manager.py
│   │   │   ├── content_calendar.py
│   │   │   ├── safety_checker.py
│   │   │   └── hashtag_optimizer.py
│   │   ├── tasks/              # Celery task definitions
│   │   │   ├── content_tasks.py
│   │   │   ├── youtube_tasks.py
│   │   │   ├── trend_tasks.py
│   │   │   └── beat_schedule.py
│   │   └── core/               # Config, DB, logging, constants
│   ├── summarizer.py           # LLM summarization utilities
│   └── trends.py               # Google Trends + Reddit scraping
├── alembic/                    # Database migration scripts
├── configs/                    # Environment-specific configuration
├── docker/                     # Docker Compose for local dev
├── monitoring/                 # Prometheus config
├── tests/                      # Async test suite
└── pyproject.toml              # Dependencies (Poetry)
```

---

## License

MIT — see [LICENSE](LICENSE)
