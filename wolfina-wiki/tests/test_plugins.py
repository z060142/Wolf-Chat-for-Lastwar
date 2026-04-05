"""Tests for plugin registration, lifecycle, and event bus isolation."""

import asyncio

import pytest
from httpx import AsyncClient

AGENT = "admin-agent"
HEADERS = {"X-Agent-ID": AGENT}

PLUGIN_PAYLOAD = {
    "name": "test-plugin",
    "display_name": "Test Plugin",
    "description": "A plugin for testing",
    "version": "1.0.0",
    "capabilities": ["observe:pages"],
}


@pytest.mark.asyncio
async def test_register_plugin(client):
    resp = await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-plugin"
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_register_plugin_duplicate(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    resp = await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_enable_disable_plugin(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)

    resp = await client.post("/plugins/test-plugin/enable", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True

    resp = await client.post("/plugins/test-plugin/disable", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_get_plugin_status(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    resp = await client.get("/plugins/test-plugin/status", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_plugin_capabilities(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    resp = await client.get("/plugins/test-plugin/capabilities", headers=HEADERS)
    assert resp.status_code == 200
    assert "observe:pages" in resp.json()["capabilities"]


@pytest.mark.asyncio
async def test_remove_plugin(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    resp = await client.delete("/plugins/test-plugin", headers=HEADERS)
    assert resp.status_code == 204

    resp = await client.get("/plugins/test-plugin/status", headers=HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_plugins(client):
    for i in range(3):
        await client.post(
            "/plugins",
            json={**PLUGIN_PAYLOAD, "name": f"plugin-{i}", "display_name": f"Plugin {i}"},
            headers=HEADERS,
        )
    resp = await client.get("/plugins", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_emit_event_from_enabled_plugin(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    await client.post("/plugins/test-plugin/enable", headers=HEADERS)

    resp = await client.post(
        "/events/emit",
        json={"event_type": "custom", "payload": {"key": "value"}, "source_plugin": "test-plugin"},
        headers=HEADERS,
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_emit_event_from_disabled_plugin_rejected(client):
    await client.post("/plugins", json=PLUGIN_PAYLOAD, headers=HEADERS)
    # Plugin is disabled by default.
    resp = await client.post(
        "/events/emit",
        json={"event_type": "custom", "payload": {}, "source_plugin": "test-plugin"},
        headers=HEADERS,
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_crashing_plugin_handler_does_not_affect_core(client):
    """A crashing event handler must not leak exceptions into the calling request."""
    from core.events.event_bus import event_bus
    from core.events.event_types import Event, EventType

    async def bad_handler(event: Event) -> None:
        raise RuntimeError("simulated plugin crash")

    event_bus.subscribe(EventType.page_created, bad_handler)
    try:
        resp = await client.post(
            "/pages",
            json={"title": "Crash Test", "slug": "crash-test", "creator_agent_id": AGENT},
            headers=HEADERS,
        )
        # Even with a crashing handler, the page creation must succeed.
        assert resp.status_code == 201
        # Allow event loop to process pending tasks.
        await asyncio.sleep(0.05)
    finally:
        event_bus.unsubscribe(EventType.page_created, bad_handler)
