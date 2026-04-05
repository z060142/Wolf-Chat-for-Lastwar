# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (including dev extras)
uv sync --extra dev

# Run the API server
uv run uvicorn api.app:app --reload

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_proposals.py

# Run a single test by name
uv run pytest tests/test_proposals.py::test_name -v
```

## Architecture

This is a **FastAPI + SQLAlchemy async** application. The DB auto-creates on startup (no Alembic migrations needed yet — `Base.metadata.create_all` runs in the lifespan hook).

### Layer structure

```
core/           — domain logic, no FastAPI imports
  models/       — SQLAlchemy ORM (Page, EditProposal, ProposalReview, PageRelation, PageVersion)
  schemas/      — Pydantic request/response models
  services/     — business logic (page_service, proposal_service, version_service, plugin_service)
  events/       — fire-and-forget async EventBus (singleton `event_bus`)
  settings.py   — Pydantic-settings (reads .env); key config: database_url, min_reviewers
api/
  app.py        — create_app() factory; exception handlers; router registration
  deps.py       — FastAPI dependency: get_db (yields AsyncSession)
  routers/      — thin HTTP layer; delegates all logic to core/services
plugins/
  base_plugin.py — BasePlugin ABC: on_load(event_bus), on_unload(), name, version, capabilities
```

### Proposal workflow (multi-agent governance)

The core feature. Changes to wiki pages go through: **propose → review → apply**.

Role-separation rules enforced in `proposal_service`:
- Proposer ≠ Reviewer
- Executor ≠ Proposer AND Executor ≠ any Reviewer
- A reviewer cannot vote twice on the same proposal
- An agent can only have one `pending` proposal per page at a time

`min_reviewers` (default 1) controls how many `approve` votes are needed before a proposal becomes `approved`. Any `reject` vote immediately rejects it.

`apply_proposal` uses `SELECT ... FOR UPDATE` to serialize concurrent apply attempts.

**Idempotency**: `ProposalCreate` accepts an optional `idempotency_key`; re-submitting the same key returns the existing proposal without creating a duplicate (safe for agent retries).

**Batch traceability**: proposals carry optional `batch_id` and `source_session_id` for grouping multi-proposal reasoning runs.

### Event bus

`core/events/event_bus.py` exposes a module-level singleton `event_bus`. Services call `event_bus.emit(Event(...))` after mutations. Handlers run as independent `asyncio.ensure_future` tasks — they never block the request path. Plugins subscribe in `on_load` and unsubscribe in `on_unload`.

### Plugin system

Plugins subclass `BasePlugin` and are registered via `plugin_service`. The core system never imports concrete plugin classes directly. Plugin failures are isolated from core request handling.

### Testing

Tests use in-memory SQLite. The `client` fixture in `conftest.py` overrides `api.deps.get_db` with a test session factory. All tests are async (`asyncio_mode = "auto"` in pyproject.toml).
