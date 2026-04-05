"""Tests for the Proposal → Review → Apply governance workflow."""

import pytest
from httpx import AsyncClient

PROPOSER = "proposer-agent"
REVIEWER = "reviewer-agent"
EXECUTOR = "executor-agent"

PROPOSER_H = {"X-Agent-ID": PROPOSER}
REVIEWER_H = {"X-Agent-ID": REVIEWER}
EXECUTOR_H = {"X-Agent-ID": EXECUTOR}


async def _create_page(client: AsyncClient) -> dict:
    resp = await client.post(
        "/pages",
        json={"title": "Original", "slug": "original-page", "content": "v1", "summary": "s1", "creator_agent_id": PROPOSER},
        headers=PROPOSER_H,
    )
    assert resp.status_code == 201
    return resp.json()


async def _submit_proposal(client: AsyncClient, page_id: str, content: str = "v2", **extra) -> dict:
    payload = {
        "target_page_id": page_id,
        "proposed_title": "Updated Title",
        "proposed_content": content,
        "proposed_summary": "s2",
        "rationale": "Improving content",
        "proposer_agent_id": PROPOSER,
        **extra,
    }
    resp = await client.post("/proposals", json=payload, headers=PROPOSER_H)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _approve(client: AsyncClient, proposal_id: str) -> dict:
    resp = await client.post(
        f"/proposals/{proposal_id}/review",
        json={"reviewer_agent_id": REVIEWER, "decision": "approve"},
        headers=REVIEWER_H,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _apply(client: AsyncClient, proposal_id: str) -> dict:
    resp = await client.post(
        f"/proposals/{proposal_id}/apply",
        json={"executor_agent_id": EXECUTOR},
        headers=EXECUTOR_H,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_happy_path_propose_review_apply(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])
    assert proposal["status"] == "pending"

    reviewed = await _approve(client, proposal["id"])
    assert reviewed["status"] == "approved"

    applied = await _apply(client, proposal["id"])
    assert applied["status"] == "applied"

    # Page content should be updated.
    resp = await client.get(f"/pages/{page['id']}", headers=PROPOSER_H)
    assert resp.json()["content"] == "v2"


@pytest.mark.asyncio
async def test_version_history_recorded_after_apply(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])
    await _approve(client, proposal["id"])
    await _apply(client, proposal["id"])

    resp = await client.get(f"/pages/{page['id']}/history", headers=PROPOSER_H)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 1
    assert versions[0]["editor_agent_id"] == EXECUTOR


@pytest.mark.asyncio
async def test_reviewer_cannot_be_proposer(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])

    resp = await client.post(
        f"/proposals/{proposal['id']}/review",
        json={"reviewer_agent_id": PROPOSER, "decision": "approve"},
        headers=PROPOSER_H,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_executor_cannot_be_proposer(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])
    await _approve(client, proposal["id"])

    resp = await client.post(
        f"/proposals/{proposal['id']}/apply",
        json={"executor_agent_id": PROPOSER},
        headers=PROPOSER_H,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_executor_cannot_be_reviewer(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])
    await _approve(client, proposal["id"])

    resp = await client.post(
        f"/proposals/{proposal['id']}/apply",
        json={"executor_agent_id": REVIEWER},
        headers=REVIEWER_H,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_apply_pending_proposal(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])

    resp = await client.post(
        f"/proposals/{proposal['id']}/apply",
        json={"executor_agent_id": EXECUTOR},
        headers=EXECUTOR_H,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reject_proposal(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])

    resp = await client.post(
        f"/proposals/{proposal['id']}/review",
        json={"reviewer_agent_id": REVIEWER, "decision": "reject", "feedback": "Not accurate"},
        headers=REVIEWER_H,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_cannot_apply_rejected_proposal(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])
    await client.post(
        f"/proposals/{proposal['id']}/review",
        json={"reviewer_agent_id": REVIEWER, "decision": "reject"},
        headers=REVIEWER_H,
    )

    resp = await client.post(
        f"/proposals/{proposal['id']}/apply",
        json={"executor_agent_id": EXECUTOR},
        headers=EXECUTOR_H,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reviewer_cannot_review_twice(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])
    await _approve(client, proposal["id"])

    resp = await client.post(
        f"/proposals/{proposal['id']}/review",
        json={"reviewer_agent_id": REVIEWER, "decision": "approve"},
        headers=REVIEWER_H,
    )
    # Already approved → proposal is no longer pending, expect 422 (invalid transition)
    assert resp.status_code in (409, 422)


@pytest.mark.asyncio
async def test_cancel_proposal(client):
    page = await _create_page(client)
    proposal = await _submit_proposal(client, page["id"])

    resp = await client.post(f"/proposals/{proposal['id']}/cancel", headers=PROPOSER_H)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_create_new_page_via_proposal(client):
    """A proposal with no target_page_id should create a new page on apply."""
    resp = await client.post(
        "/proposals",
        json={
            "proposed_title": "Brand New Page",
            "proposed_slug": "brand-new-page",
            "proposed_content": "content",
            "proposed_summary": "summary",
            "rationale": "Knowledge gap",
            "proposer_agent_id": PROPOSER,
        },
        headers=PROPOSER_H,
    )
    assert resp.status_code == 201
    proposal_id = resp.json()["id"]

    await _approve(client, proposal_id)
    applied = await _apply(client, proposal_id)
    assert applied["status"] == "applied"
    assert applied["target_page_id"] is not None

    page_resp = await client.get(f"/pages/{applied['target_page_id']}", headers=EXECUTOR_H)
    assert page_resp.status_code == 200
    assert page_resp.json()["title"] == "Brand New Page"


# --- Idempotency tests ---

@pytest.mark.asyncio
async def test_idempotency_key_returns_existing_proposal(client):
    page = await _create_page(client)
    key = "unique-key-abc123"

    resp1 = await client.post(
        "/proposals",
        json={
            "target_page_id": page["id"],
            "proposed_title": "T",
            "proposed_content": "c",
            "proposed_summary": "s",
            "rationale": "r",
            "proposer_agent_id": PROPOSER,
            "idempotency_key": key,
        },
        headers=PROPOSER_H,
    )
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    # Second request with same key → same proposal returned, no duplicate.
    resp2 = await client.post(
        "/proposals",
        json={
            "target_page_id": page["id"],
            "proposed_title": "Different title",
            "proposed_content": "different",
            "proposed_summary": "different",
            "rationale": "different",
            "proposer_agent_id": PROPOSER,
            "idempotency_key": key,
        },
        headers=PROPOSER_H,
    )
    assert resp2.status_code == 201
    assert resp2.json()["id"] == id1  # same proposal


@pytest.mark.asyncio
async def test_idempotency_key_stored_in_response(client):
    page = await _create_page(client)
    resp = await client.post(
        "/proposals",
        json={
            "target_page_id": page["id"],
            "proposed_title": "T",
            "proposed_content": "c",
            "proposed_summary": "s",
            "rationale": "r",
            "proposer_agent_id": PROPOSER,
            "idempotency_key": "my-key",
        },
        headers=PROPOSER_H,
    )
    assert resp.json()["idempotency_key"] == "my-key"


# --- Batch / session metadata tests ---

@pytest.mark.asyncio
async def test_batch_id_filter(client):
    page = await _create_page(client)
    await _submit_proposal(client, page["id"], batch_id="batch-001")

    # Second page for another proposal.
    resp = await client.post(
        "/pages",
        json={"title": "P2", "slug": "page-two", "creator_agent_id": PROPOSER},
        headers=PROPOSER_H,
    )
    page2_id = resp.json()["id"]

    await client.post(
        "/proposals",
        json={
            "target_page_id": page2_id,
            "proposed_title": "P2 updated",
            "proposed_content": "c",
            "proposed_summary": "s",
            "rationale": "r",
            "proposer_agent_id": PROPOSER,
            "batch_id": "batch-002",
        },
        headers=PROPOSER_H,
    )

    resp = await client.get("/proposals?batch_id=batch-001", headers=PROPOSER_H)
    results = resp.json()
    assert len(results) == 1
    assert results[0]["batch_id"] == "batch-001"


@pytest.mark.asyncio
async def test_source_session_id_stored_and_filterable(client):
    page = await _create_page(client)
    session_id = "session-xyz"
    await _submit_proposal(client, page["id"], source_session_id=session_id)

    resp = await client.get(f"/proposals?source_session_id={session_id}", headers=PROPOSER_H)
    results = resp.json()
    assert len(results) == 1
    assert results[0]["source_session_id"] == session_id


@pytest.mark.asyncio
async def test_proposer_agent_id_filter(client):
    page = await _create_page(client)
    await _submit_proposal(client, page["id"])

    resp = await client.get(f"/proposals?proposer_agent_id={PROPOSER}", headers=PROPOSER_H)
    assert len(resp.json()) == 1

    resp = await client.get("/proposals?proposer_agent_id=nobody", headers=PROPOSER_H)
    assert len(resp.json()) == 0
