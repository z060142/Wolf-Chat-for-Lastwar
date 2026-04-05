"""Tests for page management endpoints and services."""

from datetime import datetime, timezone
from urllib.parse import quote

import pytest
from httpx import AsyncClient


AGENT = "agent-alpha"
HEADERS = {"X-Agent-ID": AGENT}


async def _create_page(client: AsyncClient, slug: str = "test-page", title: str = "Test Page") -> dict:
    resp = await client.post(
        "/pages",
        json={"title": title, "slug": slug, "content": "Hello world", "summary": "A test page", "creator_agent_id": AGENT},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_page(client):
    page = await _create_page(client)
    assert page["title"] == "Test Page"
    assert page["slug"] == "test-page"
    assert page["status"] == "active"


@pytest.mark.asyncio
async def test_create_page_duplicate_slug(client):
    await _create_page(client)
    resp = await client.post(
        "/pages",
        json={"title": "Other", "slug": "test-page", "creator_agent_id": AGENT},
        headers=HEADERS,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_page(client):
    created = await _create_page(client)
    resp = await client.get(f"/pages/{created['id']}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["slug"] == "test-page"


@pytest.mark.asyncio
async def test_get_page_not_found(client):
    resp = await client.get("/pages/nonexistent-id", headers=HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_page_by_slug(client):
    await _create_page(client, slug="known-slug", title="Known")
    resp = await client.get("/pages/by-slug/known-slug", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Known"


@pytest.mark.asyncio
async def test_get_page_by_slug_not_found(client):
    resp = await client.get("/pages/by-slug/does-not-exist", headers=HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_archive_page(client):
    created = await _create_page(client)
    resp = await client.post(f"/pages/{created['id']}/archive", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_search_pages(client):
    await _create_page(client, slug="alpha-page", title="Alpha")
    await _create_page(client, slug="beta-page", title="Beta")
    resp = await client.get("/pages/search?q=alpha", headers=HEADERS)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["slug"] == "alpha-page"


@pytest.mark.asyncio
async def test_search_pages_empty_query_returns_all(client):
    await _create_page(client, slug="page-one", title="One")
    await _create_page(client, slug="page-two", title="Two")
    resp = await client.get("/pages/search", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_search_sort_by_title_asc(client):
    await _create_page(client, slug="z-page", title="Zebra")
    await _create_page(client, slug="a-page", title="Apple")
    resp = await client.get("/pages/search?sort_by=title&sort_order=asc", headers=HEADERS)
    titles = [p["title"] for p in resp.json()]
    assert titles == sorted(titles)


@pytest.mark.asyncio
async def test_search_updated_after_filter(client):
    before = datetime.now(timezone.utc)
    await _create_page(client, slug="new-page", title="New")

    iso = quote(before.isoformat())
    resp = await client.get(f"/pages/search?updated_after={iso}", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["slug"] == "new-page"


@pytest.mark.asyncio
async def test_add_and_query_relation(client):
    parent = await _create_page(client, slug="parent-page", title="Parent")
    child = await _create_page(client, slug="child-page", title="Child")

    resp = await client.post(
        "/pages/relations",
        json={
            "source_page_id": parent["id"],
            "target_page_id": child["id"],
            "relation_type": "child",
            "created_by_agent": AGENT,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201

    resp = await client.get(f"/pages/{parent['id']}/children", headers=HEADERS)
    assert resp.status_code == 200
    children = resp.json()
    assert len(children) == 1
    assert children[0]["id"] == child["id"]


@pytest.mark.asyncio
async def test_add_relation_duplicate_raises_conflict(client):
    a = await _create_page(client, slug="page-a", title="A")
    b = await _create_page(client, slug="page-b", title="B")
    payload = {
        "source_page_id": a["id"],
        "target_page_id": b["id"],
        "relation_type": "related_to",
        "created_by_agent": AGENT,
    }
    await client.post("/pages/relations", json=payload, headers=HEADERS)
    resp = await client.post("/pages/relations", json=payload, headers=HEADERS)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_missing_agent_header_rejected(client):
    resp = await client.post(
        "/pages",
        json={"title": "T", "slug": "t", "creator_agent_id": AGENT},
    )
    assert resp.status_code == 422
