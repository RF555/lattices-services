# Lattices API

**Multi-User Hierarchical Task Management System Backend**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Code style: Ruff](https://img.shields.io/badge/Code_style-Ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![Tests: 322](https://img.shields.io/badge/Tests-322_passing-brightgreen)](tests/)
[![Coverage: 86%](https://img.shields.io/badge/Coverage-86%25-brightgreen)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

RESTful API for managing hierarchical tasks with infinite nesting, multi-user workspaces, role-based access control, real-time notifications, and activity audit trails. Built with Clean Architecture principles for maintainability and testability.

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
- [Code Quality](#code-quality)
- [Deployment](#deployment)
- [License](#license)

---

## Features

### Task Management
- **Hierarchical Tasks** -- Create tasks with unlimited nesting depth using an adjacency list model
- **Flat Fetch** -- Retrieve all tasks in a single query; frontend assembles the tree via `parent_id`
- **Cycle Detection** -- Prevents circular parent-child relationships
- **Child Progress Counts** -- Backend-computed `child_count` and `completed_child_count` on every task response
- **Tag System** -- Organize tasks with customizable color-coded tags (many-to-many)
- **Workspace Move** -- Move a task (and its entire subtree) between workspaces or to/from personal space, with atomic parent detachment, tag stripping, and dual activity/notification logging

### Multi-User Workspaces
- **Workspace Management** -- Create shared workspaces with unique slugs for team collaboration
- **Role-Based Access Control** -- Four hierarchical roles: Viewer, Member, Admin, Owner
- **Ownership Transfer** -- Owners can transfer workspace ownership to other admins
- **Workspace-Scoped Todos & Tags** -- Tasks and tags can optionally belong to a workspace (backward-compatible with personal tasks)

### Invitations
- **Email-Based Invitations** -- Invite users by email with a secure one-time token
- **Role Assignment** -- Specify the invitee's role at invitation time
- **Token Security** -- SHA-256 hashed tokens stored in DB; raw token returned once at creation
- **Expiry & Revocation** -- Invitations expire after 7 days and can be revoked by admins

### Groups
- **Workspace Sub-Teams** -- Organize members into groups within a workspace
- **Group Roles** -- Group-level admin and member roles, separate from workspace roles
- **Dual Permission Model** -- Workspace admins bypass group-level permission checks

### Notifications
- **Event-Driven** -- Automatic notifications for task changes, member events, invitations
- **Per-User Preferences** -- Control notifications by channel (in-app, email), type, and workspace
- **Deduplication** -- 5-minute deduplication window prevents notification spam
- **Cursor-Based Pagination** -- Efficient feed retrieval for large notification volumes
- **Auto-Cleanup** -- Background task expires notifications after 90 days

### Activity Feed
- **Immutable Audit Trail** -- Every workspace action is logged with actor, entity, and change diffs
- **Entity History** -- Query the full change history of any specific entity
- **Change Diffs** -- Captures before/after values for all modified fields

### Infrastructure
- **JWT Authentication** -- Supports both HS256 (dev) and ES256/JWKS (Supabase production)
- **Rate Limiting** -- Per-IP rate limits (30/min reads, 10/min writes) with `429` responses
- **Structured Logging** -- JSON logs in production, pretty console in development (structlog)
- **Security Headers** -- X-Content-Type-Options, X-Frame-Options, HSTS, Request ID tracking
- **Batch Optimized** -- N+1 query elimination with batch tag fetching, tag usage counts, and child count fetching
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
| **Auth** | JWT (python-jose), HS256 + ES256/JWKS |
| **Logging** | structlog |
| **Rate Limiting** | slowapi |
| **Serialization** | orjson |
| **Testing** | pytest + pytest-asyncio + aiosqlite |
| **Linting** | Ruff (E, W, F, I, B, C4, UP, A, SIM, RUF) |
| **Type Checking** | mypy (strict) |
| **Pre-commit** | trailing-whitespace, ruff, mypy |
| **CI** | GitHub Actions (quality + test jobs) |
| **Task Runner** | [Just](https://just.systems/) |

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

- **Repository Pattern** -- Protocol-based interfaces with SQLAlchemy implementations
- **Unit of Work** -- Transaction management via `SQLAlchemyUnitOfWork` context manager
- **Dependency Injection** -- FastAPI's `Depends()` with factory functions
- **Domain Entities** -- Pure Python dataclasses, independent of ORM; frozen dataclass value objects (`TagWithCount`, `NotificationView`) for type-safe service returns
- **Event-Driven Side Effects** -- Services call `ActivityService.log()` and `NotificationService.notify()` within the same UoW transaction

```
Request → Middleware → Route → Auth Dependency → Service → UoW → Repository → Database
                        ↓                          ↓
                  Pydantic Schema          Activity + Notification
              (validation + response)       (audit + side effects)
```

### Workspace Role Hierarchy

```
VIEWER (10) → MEMBER (20) → ADMIN (30) → OWNER (40)
  read-only     create/edit     manage members     full control
                own content     invitations         delete workspace
                                groups              transfer ownership
```

Permission checks use `user_role >= required_role` for hierarchical enforcement.

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

> **Note:** `DATABASE_URL` accepts both `postgresql://` and `postgresql+asyncpg://` schemes. The app auto-converts to `postgresql+asyncpg://` at runtime via the `async_database_url` computed property.

---

## API Documentation

Once the server is running, interactive API docs are available at:

| Interface | URL |
|---|---|
| **Swagger UI** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **ReDoc** | [http://localhost:8000/redoc](http://localhost:8000/redoc) |
| **OpenAPI JSON** | [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json) |

### Authentication

All endpoints except `/health` require a JWT token:

```
Authorization: Bearer <your_token>
```

### Endpoints Overview

#### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Basic health check |
| `GET` | `/health/detailed` | Health check with DB status |

#### Todos

| Method | Endpoint | Description | Rate Limit |
|---|---|---|---|
| `GET` | `/api/v1/todos` | List tasks (filter by workspace, status, tag) | 30/min |
| `POST` | `/api/v1/todos` | Create a task | 10/min |
| `GET` | `/api/v1/todos/{id}` | Get a task with tags | 30/min |
| `PATCH` | `/api/v1/todos/{id}` | Update a task | 10/min |
| `DELETE` | `/api/v1/todos/{id}` | Delete a task (cascade children) | 10/min |
| `POST` | `/api/v1/todos/{id}/move` | Move task (+ subtree) to another workspace | 10/min |

#### Tags

| Method | Endpoint | Description | Rate Limit |
|---|---|---|---|
| `GET` | `/api/v1/tags` | List tags with usage counts | 30/min |
| `POST` | `/api/v1/tags` | Create a tag | 10/min |
| `PATCH` | `/api/v1/tags/{id}` | Update a tag | 10/min |
| `DELETE` | `/api/v1/tags/{id}` | Delete a tag | 10/min |
| `GET` | `/api/v1/todos/{id}/tags` | Get tags for a task | 30/min |
| `POST` | `/api/v1/todos/{id}/tags` | Attach a tag to a task | 10/min |
| `DELETE` | `/api/v1/todos/{id}/tags/{tag_id}` | Detach a tag | 10/min |

#### Workspaces

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/workspaces` | List user's workspaces |
| `POST` | `/api/v1/workspaces` | Create workspace (creator = Owner) |
| `GET` | `/api/v1/workspaces/{id}` | Get workspace details |
| `PATCH` | `/api/v1/workspaces/{id}` | Update workspace (Admin+) |
| `DELETE` | `/api/v1/workspaces/{id}` | Delete workspace (Owner only) |
| `GET` | `/api/v1/workspaces/{id}/members` | List members |
| `POST` | `/api/v1/workspaces/{id}/members` | Add member (Admin+) |
| `PATCH` | `/api/v1/workspaces/{id}/members/{uid}` | Update member role (Admin+) |
| `DELETE` | `/api/v1/workspaces/{id}/members/{uid}` | Remove member or leave |
| `POST` | `/api/v1/workspaces/{id}/transfer-ownership` | Transfer ownership (Owner only) |

#### Invitations

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/workspaces/{id}/invitations` | Create invitation (Admin+) |
| `GET` | `/api/v1/workspaces/{id}/invitations` | List workspace invitations |
| `DELETE` | `/api/v1/workspaces/{id}/invitations/{inv_id}` | Revoke invitation (Admin+) |
| `POST` | `/api/v1/invitations/accept` | Accept invitation with token |
| `GET` | `/api/v1/invitations/pending` | Get pending invitations for current user |

#### Groups

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/workspaces/{id}/groups` | List groups |
| `POST` | `/api/v1/workspaces/{id}/groups` | Create group (Admin+) |
| `PATCH` | `/api/v1/workspaces/{id}/groups/{gid}` | Update group |
| `DELETE` | `/api/v1/workspaces/{id}/groups/{gid}` | Delete group (Admin+) |
| `GET` | `/api/v1/workspaces/{id}/groups/{gid}/members` | List group members |
| `POST` | `/api/v1/workspaces/{id}/groups/{gid}/members` | Add group member |
| `DELETE` | `/api/v1/workspaces/{id}/groups/{gid}/members/{uid}` | Remove group member |

#### Notifications

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/workspaces/{id}/notifications` | List workspace notifications |
| `GET` | `/api/v1/workspaces/{id}/notifications/unread-count` | Get unread count |
| `PATCH` | `/api/v1/workspaces/{id}/notifications/{rid}/read` | Mark as read |
| `PATCH` | `/api/v1/workspaces/{id}/notifications/{rid}/unread` | Mark as unread |
| `POST` | `/api/v1/workspaces/{id}/notifications/mark-all-read` | Mark all as read |
| `DELETE` | `/api/v1/workspaces/{id}/notifications/{rid}` | Soft-delete notification |
| `GET` | `/api/v1/users/me/notifications` | List all notifications (all workspaces) |
| `GET` | `/api/v1/users/me/notifications/unread-count` | Total unread count |
| `POST` | `/api/v1/users/me/notifications/mark-all-read` | Mark all read (all workspaces) |
| `GET` | `/api/v1/users/me/notification-preferences` | Get preferences |
| `PUT` | `/api/v1/users/me/notification-preferences` | Update preference |
| `GET` | `/api/v1/users/me/notification-types` | List notification types |

#### Activity Feed

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/workspaces/{id}/activity` | Get workspace activity feed |
| `GET` | `/api/v1/workspaces/{id}/activity/{entity_type}/{entity_id}` | Get entity history |

### Example Requests

**Create a workspace:**

```bash
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Team", "description": "Team workspace"}'
```

**Invite a member:**

```bash
curl -X POST http://localhost:8000/api/v1/workspaces/<workspace_id>/invitations \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "teammate@example.com", "role": "member"}'
```

**Create a workspace-scoped task:**

```bash
curl -X POST http://localhost:8000/api/v1/todos \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -H "X-Workspace-ID: <workspace_id>" \
  -d '{"title": "Team standup notes", "workspace_id": "<workspace_id>"}'
```

**Move a task to a different workspace:**

```bash
curl -X POST http://localhost:8000/api/v1/todos/<todo_id>/move \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"target_workspace_id": "<target_workspace_id>"}'
```

> Moves the task and all its descendants to the target workspace. Tags are stripped (workspace-scoped), and the task becomes a root in the target. Set `target_workspace_id` to `null` to move to personal space.

**Create a child task:**

```bash
curl -X POST http://localhost:8000/api/v1/todos \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy milk", "parent_id": "<parent_task_id>"}'
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
│   │       │   ├── tags.py              # Tag CRUD + Todo-Tag routes
│   │       │   ├── workspaces.py        # Workspace CRUD + member management
│   │       │   ├── groups.py            # Group CRUD + group members
│   │       │   ├── invitations.py       # Invitation create/accept/revoke
│   │       │   ├── notifications.py     # Notification feed + preferences
│   │       │   └── activity.py          # Activity feed + entity history
│   │       └── schemas/
│   │           ├── common.py            # Shared response schemas
│   │           ├── todo.py              # Todo request/response schemas
│   │           ├── tag.py               # Tag schemas
│   │           ├── workspace.py         # Workspace + member schemas
│   │           ├── group.py             # Group schemas
│   │           ├── invitation.py        # Invitation schemas
│   │           ├── notification.py      # Notification + preference schemas
│   │           └── activity.py          # Activity log schemas
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings configuration
│   │   ├── exceptions.py                # Error codes & custom exceptions
│   │   ├── logging.py                   # structlog configuration
│   │   └── rate_limit.py                # slowapi rate limiter setup
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── todo.py                  # Todo dataclass entity
│   │   │   ├── tag.py                   # Tag dataclass entity + TagWithCount value object
│   │   │   ├── workspace.py             # Workspace, WorkspaceMember, WorkspaceRole
│   │   │   ├── group.py                 # Group, GroupMember, GroupRole
│   │   │   ├── invitation.py            # Invitation, InvitationStatus
│   │   │   ├── notification.py          # Notification, preferences, types + NotificationView value object
│   │   │   ├── activity.py              # ActivityLog, action constants
│   │   │   └── profile.py              # User profile entity
│   │   ├── repositories/
│   │   │   ├── unit_of_work.py          # IUnitOfWork protocol
│   │   │   ├── todo_repository.py       # ITodoRepository protocol
│   │   │   ├── tag_repository.py        # ITagRepository protocol
│   │   │   ├── workspace_repository.py  # IWorkspaceRepository protocol
│   │   │   ├── group_repository.py      # IGroupRepository protocol
│   │   │   ├── invitation_repository.py # IInvitationRepository protocol
│   │   │   ├── notification_repository.py # INotificationRepository protocol
│   │   │   └── activity_repository.py   # IActivityRepository protocol
│   │   └── services/
│   │       ├── todo_service.py          # Todo business logic
│   │       ├── tag_service.py           # Tag business logic
│   │       ├── workspace_service.py     # Workspace + member management
│   │       ├── group_service.py         # Group management
│   │       ├── invitation_service.py    # Invitation create/accept/revoke
│   │       ├── notification_service.py  # Notification dispatch + preferences
│   │       └── activity_service.py      # Activity logging + feed
│   └── infrastructure/
│       ├── auth/
│       │   ├── provider.py              # IAuthProvider protocol + TokenUser
│       │   └── jwt_provider.py          # JWT implementation (HS256 + ES256)
│       └── database/
│           ├── models.py                # SQLAlchemy ORM models (14 tables)
│           ├── session.py               # Async engine & session factory
│           ├── sqlalchemy_uow.py        # Unit of Work implementation
│           └── repositories/            # SQLAlchemy repository implementations
│               ├── sqlalchemy_todo_repo.py
│               ├── sqlalchemy_tag_repo.py
│               ├── sqlalchemy_workspace_repo.py
│               ├── sqlalchemy_group_repo.py
│               ├── sqlalchemy_invitation_repo.py
│               ├── sqlalchemy_notification_repo.py
│               └── sqlalchemy_activity_repo.py
├── tests/
│   ├── conftest.py                      # Shared fixtures (DB, auth, test user)
│   ├── integration/api/
│   │   ├── test_health.py               # Health endpoint tests
│   │   ├── test_todos_api.py            # Todo API integration tests
│   │   ├── test_tags_api.py             # Tag API integration tests
│   │   ├── test_workspaces_api.py       # Workspace API tests
│   │   ├── test_groups_api.py           # Group API tests
│   │   ├── test_invitations_api.py      # Invitation API tests
│   │   ├── test_notifications_api.py    # Notification API tests
│   │   └── test_activity_api.py         # Activity feed API tests
│   └── unit/
│       ├── conftest.py                  # Shared FakeUnitOfWork (7 repo mocks)
│       ├── services/
│       │   ├── test_todo_service.py     # Todo service unit tests
│       │   ├── test_tag_service.py      # Tag service unit tests
│       │   ├── test_workspace_service.py # Workspace service unit tests
│       │   ├── test_group_service.py    # Group service unit tests
│       │   ├── test_invitation_service.py # Invitation service unit tests
│       │   ├── test_notification_service.py # Notification service unit tests
│       │   └── test_activity_service.py # Activity service unit tests
│       ├── auth/
│       │   ├── test_auth_dependency.py  # Auth dependency tests
│       │   └── test_jwt_provider.py     # JWT provider tests (HS256 + ES256)
│       ├── api/
│       │   └── test_exception_handlers.py # Exception handler tests
│       └── middleware/
│           └── test_middleware.py        # Security headers + request ID tests
├── migrations/                          # Alembic migration scripts
├── .github/workflows/ci.yml            # GitHub Actions CI pipeline
├── .pre-commit-config.yaml             # Pre-commit hook configuration
├── .vscode/settings.json               # VS Code editor settings
├── .env.example                         # Environment variable template
├── alembic.ini                          # Alembic configuration
├── Justfile                             # Just command runner
├── pyproject.toml                       # Project config & dependencies
├── pyrightconfig.json                   # Pyright/Pylance IDE configuration
└── render.yaml                          # Render deployment config
```

---

## Testing

Tests use **pytest** with **pytest-asyncio** and an in-memory SQLite database (aiosqlite).

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

| Test Type | Count | Location | Scope |
|---|---|---|---|
| **Unit** (Services) | 201 | `tests/unit/services/` | Business logic, permissions, side effects |
| **Unit** (Auth) | 23 | `tests/unit/auth/` | JWT validation, auth dependencies |
| **Unit** (API/Middleware) | 10 | `tests/unit/api/`, `tests/unit/middleware/` | Exception handlers, security headers |
| **Integration** (API) | 88 | `tests/integration/api/` | Full request/response through all layers |
| **Total** | **322** | | **86% line coverage** |

### Coverage highlights

| Module | Coverage |
|---|---|
| Domain services | 88--100% |
| Auth (JWT provider) | 100% |
| Exception handlers | 100% |
| Middleware | 93--100% |
| API routes | 64--90% |
| Overall | **86%** |

The test infrastructure uses:
- **Unit tests:** `FakeUnitOfWork` with `AsyncMock` repos for isolated service testing
- **Integration tests:** FastAPI dependency overrides with in-memory SQLite via aiosqlite
- A fixed test user (bypasses JWT verification in integration tests)

---

## Code Quality

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting/formatting, [mypy](https://mypy-lang.org/) for type checking, and [pre-commit](https://pre-commit.com/) hooks to enforce standards automatically.

### Quick commands (via [Just](https://just.systems/))

```bash
just fmt          # Auto-fix lint errors + format code
just lint         # Run lint + type checks (read-only)
just test         # Run tests with coverage
just check        # Full pipeline: format check + lint + typecheck + tests
just pre-commit   # Run all pre-commit hooks on all files
just dev          # Start dev server
```

### Manual commands

```bash
# Lint and format
ruff check src/ tests/          # Check for lint errors
ruff check src/ tests/ --fix    # Auto-fix lint errors
ruff format src/ tests/         # Format code

# Type checking
mypy src/

# Pre-commit hooks
pre-commit run --all-files
```

### Pre-commit hooks

Installed automatically with `pre-commit install`. Runs on every commit:

| Hook | Purpose |
|------|---------|
| trailing-whitespace | Remove trailing whitespace |
| end-of-file-fixer | Ensure files end with newline |
| check-yaml / check-toml | Validate config files |
| check-added-large-files | Block files > 500KB |
| debug-statements | Catch leftover `breakpoint()` / `pdb` |
| check-merge-conflict | Detect unresolved merge markers |
| ruff (lint) | Lint with auto-fix |
| ruff (format) | Enforce consistent formatting |
| mypy | Strict type checking on `src/` |

### CI Pipeline

GitHub Actions runs on every push to `main` and every pull request:

1. **Code Quality** -- `ruff format --check` + `ruff check` + `mypy`
2. **Tests** -- `pytest` with coverage report (runs only if quality passes)

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
