# Lattices API

**Hierarchical Task Management System Backend**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Code style: Ruff](https://img.shields.io/badge/Code_style-Ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

RESTful API for managing hierarchical tasks with infinite nesting, customizable tags, and tree-based organization. Built with Clean Architecture principles for maintainability and testability.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Linting & Formatting](#linting--formatting)
- [Deployment](#deployment)
- [License](#license)

---

## Features

- **Hierarchical Tasks** -- Create tasks with unlimited nesting depth using an adjacency list model
- **Flat Fetch** -- Retrieve all tasks in a single query; frontend assembles the tree via `parent_id`
- **Tag System** -- Organize tasks with customizable color-coded tags (many-to-many)
- **JWT Authentication** -- Secure endpoints with token-based auth via an abstracted provider
- **Rate Limiting** -- Per-IP rate limits (30/min reads, 10/min writes) with proper `429` responses
- **Structured Logging** -- JSON logs in production, pretty console in development (structlog)
- **Security Headers** -- X-Content-Type-Options, X-Frame-Options, HSTS, Request ID tracking
- **Child Progress Counts** -- Backend-computed `child_count` and `completed_child_count` on every task response
- **Batch Optimized** -- N+1 query elimination with batch tag and child count fetching
- **GZip + ORJSON** -- Compressed responses and fast JSON serialization

---

## Tech Stack

| Category | Technology |
|---|---|
| **Framework** | FastAPI 0.109+ |
| **Language** | Python 3.11+ |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Database** | PostgreSQL (asyncpg) |
| **Migrations** | Alembic |
| **Validation** | Pydantic v2 |
| **Auth** | JWT (python-jose) |
| **Logging** | structlog |
| **Rate Limiting** | slowapi |
| **Serialization** | orjson |
| **Testing** | pytest + pytest-asyncio + aiosqlite |
| **Linting** | Ruff |
| **Type Checking** | mypy (strict) |

---

## Architecture

The project follows **Clean Architecture** with four distinct layers:

```
src/
├── api/            # Presentation layer (routes, schemas, middleware)
├── core/           # Application config, exceptions, cross-cutting concerns
├── domain/         # Business logic (entities, services, repository protocols)
└── infrastructure/ # External adapters (database, auth providers)
```

**Key patterns:**

- **Repository Pattern** -- Protocol-based interfaces (`ITodoRepository`, `ITagRepository`) with SQLAlchemy implementations
- **Unit of Work** -- Transaction management via `SQLAlchemyUnitOfWork` context manager
- **Dependency Injection** -- FastAPI's `Depends()` with factory functions
- **Domain Entities** -- Pure Python dataclasses, independent of ORM

```
Request → Middleware → Route → Service → UoW → Repository → Database
                        ↓
                    Pydantic Schema (validation + serialization)
```

---

## Prerequisites

- **Python 3.11** or higher
- **PostgreSQL 14+** (for production) or SQLite (for testing)
- **Git**

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-org/lattices-services.git
cd lattices-services
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your database credentials and JWT secret
```

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Start the development server from inside `src`

```bash
uvicorn src.main:app --reload --port 8000
```

Or just from the root dir:

```bash
uvicorn main:app --reload --port 8000 --app-dir src
```

The API is now running at `http://localhost:8000`.

---

## Configuration

All configuration is loaded from environment variables (or `.env` file). See `.env.example` for a complete template.

| Variable | Description | Default | Required |
|---|---|---|---|
| `APP_NAME` | Application display name | `Lattices API` | No |
| `APP_ENV` | Environment (`development` / `production`) | `development` | No |
| `DEBUG` | Enable debug mode | `false` | No |
| `HOST` | Server bind address | `0.0.0.0` | No |
| `PORT` | Server port | `8000` | No |
| `DATABASE_URL` | PostgreSQL connection string | -- | **Yes** |
| `JWT_SECRET_KEY` | Secret key for JWT token signing | -- | **Yes** |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` | No |
| `JWT_EXPIRE_MINUTES` | Token expiration in minutes | `30` | No |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000` | No |
| `RATE_LIMIT_ENABLED` | Enable/disable rate limiting | `true` | No |
| `SUPABASE_URL` | Supabase project URL | -- | **Yes** |
| `SUPABASE_ANON_KEY` | Supabase anonymous/public key | -- | **Yes** |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | -- | **Yes** |
| `SUPABASE_JWKS_URL` | Supabase JWKS endpoint for ES256 JWT validation | -- | No |

> **Note:** `DATABASE_URL` accepts both `postgresql://` and `postgresql+asyncpg://` schemes. The app auto-converts to `postgresql+asyncpg://` at runtime via the `async_database_url` computed property.

---

## API Documentation

Once the server is running, interactive API docs are available at:

| Interface | URL |
|---|---|
| **Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **ReDoc** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| **OpenAPI JSON** | [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json) |

### Endpoints Overview

| Method | Endpoint | Description | Rate Limit |
|---|---|---|---|
| `GET` | `/health` | Basic health check | -- |
| `GET` | `/health/detailed` | Health check with DB status | -- |
| `GET` | `/api/v1/todos` | List all tasks | 30/min |
| `POST` | `/api/v1/todos` | Create a task | 10/min |
| `GET` | `/api/v1/todos/{id}` | Get a task | 30/min |
| `PATCH` | `/api/v1/todos/{id}` | Update a task | 10/min |
| `DELETE` | `/api/v1/todos/{id}` | Delete a task (cascade) | 10/min |
| `GET` | `/api/v1/tags` | List all tags | 30/min |
| `POST` | `/api/v1/tags` | Create a tag | 10/min |
| `PATCH` | `/api/v1/tags/{id}` | Update a tag | 10/min |
| `DELETE` | `/api/v1/tags/{id}` | Delete a tag | 10/min |
| `GET` | `/api/v1/todos/{id}/tags` | Get tags for a task | 30/min |
| `POST` | `/api/v1/todos/{id}/tags` | Attach a tag to a task | 10/min |
| `DELETE` | `/api/v1/todos/{id}/tags/{tag_id}` | Detach a tag from a task | 10/min |

### Authentication

All endpoints except `/health` require a JWT token:

```
Authorization: Bearer <your_token>
```

### Example Requests

**Create a task:**

```bash
curl -X POST http://localhost:8000/api/v1/todos \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy groceries", "description": "Weekly shopping"}'
```

**Create a child task:**

```bash
curl -X POST http://localhost:8000/api/v1/todos \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy milk", "parent_id": "<parent_task_id>"}'
```

**Create and attach a tag:**

```bash
# Create tag
curl -X POST http://localhost:8000/api/v1/tags \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "urgent", "color_hex": "#EF4444"}'

# Attach to task
curl -X POST http://localhost:8000/api/v1/todos/<todo_id>/tags \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"tag_id": "<tag_id>"}'
```

---

## Project Structure

```
lattices-services/
├── src/
│   ├── main.py                          # FastAPI app factory & entry point
│   ├── api/
│   │   ├── exception_handlers.py        # Global exception handlers
│   │   ├── dependencies/
│   │   │   └── auth.py                  # Auth dependencies (get_current_user)
│   │   ├── middleware/
│   │   │   ├── logging.py               # Request logging with timing
│   │   │   ├── request_id.py            # X-Request-ID tracking
│   │   │   └── security.py              # Security headers
│   │   ├── routes/
│   │   │   └── health.py                # Health check endpoints
│   │   └── v1/
│   │       ├── dependencies.py          # DI factories (services, UoW)
│   │       ├── routes/
│   │       │   ├── todos.py             # Todo CRUD routes
│   │       │   └── tags.py              # Tag CRUD + Todo-Tag routes
│   │       └── schemas/
│   │           ├── common.py            # Shared response schemas
│   │           ├── todo.py              # Todo request/response schemas
│   │           └── tag.py               # Tag request/response schemas
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings configuration
│   │   ├── exceptions.py                # Error codes & custom exceptions
│   │   ├── logging.py                   # structlog configuration
│   │   └── rate_limit.py                # slowapi rate limiter setup
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── todo.py                  # Todo dataclass entity
│   │   │   ├── tag.py                   # Tag dataclass entity
│   │   │   └── profile.py              # User profile entity
│   │   ├── repositories/
│   │   │   ├── todo_repository.py       # ITodoRepository protocol
│   │   │   ├── tag_repository.py        # ITagRepository protocol
│   │   │   └── unit_of_work.py          # IUnitOfWork protocol
│   │   └── services/
│   │       ├── todo_service.py          # Todo business logic
│   │       └── tag_service.py           # Tag business logic
│   └── infrastructure/
│       ├── auth/
│       │   ├── provider.py              # IAuthProvider protocol + TokenUser
│       │   └── jwt_provider.py          # JWT implementation
│       └── database/
│           ├── models.py                # SQLAlchemy ORM models
│           ├── session.py               # Async engine & session factory
│           ├── sqlalchemy_uow.py        # Unit of Work implementation
│           └── repositories/
│               ├── sqlalchemy_todo_repo.py  # Todo repository impl
│               └── sqlalchemy_tag_repo.py   # Tag repository impl
├── tests/
│   ├── conftest.py                      # Fixtures (auth, DB, test client)
│   ├── integration/api/
│   │   ├── test_health.py               # Health endpoint tests
│   │   ├── test_todos_api.py            # Todo API integration tests
│   │   └── test_tags_api.py             # Tag API integration tests
│   └── unit/services/
│       └── test_todo_service.py         # Todo service unit tests
├── migrations/                          # Alembic migration scripts
├── .env.example                         # Environment variable template
├── alembic.ini                          # Alembic configuration
├── pyproject.toml                       # Project config & dependencies
├── pyrightconfig.json                   # Pyright/Pylance IDE configuration
└── render.yaml                          # Render deployment config
```

---

## Testing

Tests use **pytest** with **pytest-asyncio** and an in-memory SQLite database.

### Run the full test suite

```bash
pytest
```

### Run with coverage report

```bash
pytest --cov=src --cov-report=term-missing
```

### Run a specific test file

```bash
pytest tests/integration/api/test_todos_api.py -v
```

### Test structure

| Test Type | Count | Location |
|---|---|---|
| **Integration** (API) | 35 | `tests/integration/api/` |
| **Unit** (Services) | 14 | `tests/unit/services/` |
| **Total** | **49** | |

The test infrastructure uses FastAPI dependency overrides to inject:
- In-memory SQLite via aiosqlite
- A fixed test user (bypasses JWT verification)
- Test-scoped service instances with the test database

---

## Linting & Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for lint errors
ruff check src/ tests/

# Auto-fix lint errors
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/
```

### Type checking

```bash
mypy src/ --strict
```

---

## Deployment

### Render

The project includes a `render.yaml` for one-click deployment to [Render](https://render.com/) using **Supabase** as the external database:

1. Connect your GitHub repository to Render
2. Render auto-detects `render.yaml` and provisions a web service
3. Set the following secret environment variables in the Render dashboard:
   - `DATABASE_URL` -- Your Supabase PostgreSQL connection string
   - `SUPABASE_URL` -- Your Supabase project URL
   - `SUPABASE_ANON_KEY` -- Your Supabase anonymous key
   - `SUPABASE_SERVICE_ROLE_KEY` -- Your Supabase service role key
   - `JWT_SECRET_KEY` -- Your JWT signing secret (Supabase JWT secret)
4. The build step automatically runs `alembic upgrade head` to apply migrations

### Docker (manual)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production checklist

- [ ] Set `APP_ENV=production`
- [ ] Set `DEBUG=false`
- [ ] Generate a strong `JWT_SECRET_KEY` (use the Supabase JWT secret)
- [ ] Configure `CORS_ORIGINS` for your frontend domain
- [ ] Set `DATABASE_URL` to your Supabase PostgreSQL connection string
- [ ] Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`
- [ ] Run `alembic upgrade head` for database migrations
- [ ] Verify `/health` returns `200`
- [ ] Verify `/health/detailed` shows `database: healthy`

---

## License

This project is licensed under the MIT License.
