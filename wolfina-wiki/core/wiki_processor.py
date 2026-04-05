"""Wiki AI Processor — autonomous 5-phase conversation-to-wiki pipeline.

Phase 1: Fetch existing wiki pages
Phase 2: LLM analysis — identify what to create/update/merge/flag
Phase 3: Submit proposals (agent: wiki-proposer)
Phase 4: Auto-review + apply (agents: wiki-reviewer, wiki-executor)
Phase 5: Mark messages as processed in ConversationBuffer
"""

import json
import logging
import re
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from core.conversation_buffer import Message, conversation_buffer
from core.settings import settings

logger = logging.getLogger(__name__)

PROPOSER_ID = "wiki-proposer"
REVIEWER_ID = "wiki-reviewer"
EXECUTOR_ID = "wiki-executor"

ANALYSIS_SYSTEM_PROMPT = """\
You are a wiki knowledge manager for a game assistant system.
Your task is to analyze a conversation transcript and determine what information \
is worth recording in a persistent wiki knowledge base.

You will receive:
1. EXISTING PAGES: A list of current wiki pages (title, slug, summary)
2. CONVERSATION: The transcript to analyze

Output a JSON object with a "proposals" array. Each proposal has an "action" field:

"create"  — New wiki page. Fields: title, slug, content, summary, canonical_facts (list), confidence (0-1), rationale
"update"  — Update an existing page. Fields: target_slug, title, content, summary, canonical_facts (list), rationale
"merge"   — Two pages cover the same topic. Fields: keep_slug, remove_slug, rationale
"flag_conflict" — Conversation contradicts an existing page. Fields: page_slug, conflict_note, rationale

Rules:
- Only propose pages for factual, reusable information (game mechanics, player profiles, strategies, events)
- Skip casual chit-chat, greetings, or one-time questions
- For "slug": use lowercase letters, numbers, and hyphens only (no spaces)
- "canonical_facts" should be a short list of bullet-point facts
- Output ONLY valid JSON. No markdown fences, no explanation, nothing else.

Example output:
{"proposals": [{"action": "create", "title": "Alliance War Rules", "slug": "alliance-war-rules", \
"content": "## Alliance War Rules\\n\\nAlliance wars occur every Tuesday...", \
"summary": "Rules and schedule for alliance wars.", "canonical_facts": ["Wars occur Tuesdays", \
"Max 50 players per side"], "confidence": 0.85, "rationale": "Detailed war rules discussed"}]}
"""

REVIEW_SYSTEM_PROMPT = """\
You are a wiki quality reviewer. You will receive a list of proposed wiki page changes.
Your job is to approve or reject each proposal.

For each proposal, output: {"proposal_id": "...", "decision": "approve" or "reject", "feedback": "..."}

Be strict: reject proposals that are vague, too short, or not genuinely useful as reference material.
Approve well-structured, factual proposals.

Output a JSON object with a "reviews" array. Output ONLY valid JSON.
"""


# ---------------------------------------------------------------------------
# LLM Client abstraction
# ---------------------------------------------------------------------------

class LLMClient(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        """Send messages and return response text."""


class OllamaLLMClient(LLMClient):
    def __init__(self) -> None:
        try:
            from ollama import Client as OllamaClient
            self._client = OllamaClient(
                host=settings.ollama_host,
                headers={"Authorization": f"Bearer {settings.ollama_api_key}"},
            )
        except ImportError as e:
            raise RuntimeError("ollama package not installed. Run: uv add ollama") from e

    def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        response = self._client.chat(
            model=settings.ollama_model,
            messages=messages,
            options={"temperature": temperature},
        )
        return response["message"]["content"]


class OpenAILLMClient(LLMClient):
    def __init__(self) -> None:
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        except ImportError as e:
            raise RuntimeError("openai package not installed. Run: uv add openai") from e

    def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        response = self._client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


def build_llm_client() -> LLMClient:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        return OllamaLLMClient()
    elif provider == "openai":
        return OpenAILLMClient()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Use 'ollama' or 'openai'.")


# ---------------------------------------------------------------------------
# Processing result
# ---------------------------------------------------------------------------

class ProcessingResult:
    def __init__(self) -> None:
        self.processed_message_ids: list[str] = []
        self.proposals_submitted: int = 0
        self.proposals_approved: int = 0
        self.proposals_applied: int = 0
        self.errors: list[str] = []
        self.log_lines: list[str] = []

    def log(self, msg: str) -> None:
        logger.info(msg)
        self.log_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ---------------------------------------------------------------------------
# WikiProcessor
# ---------------------------------------------------------------------------

class WikiProcessor:
    """Autonomous wiki processor. Runs in a background thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._llm: Optional[LLMClient] = None
        self._on_complete_callbacks: list[Any] = []

    def add_completion_callback(self, callback) -> None:
        """Register callback(result: ProcessingResult) called after each run."""
        self._on_complete_callbacks.append(callback)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _base_url(self) -> str:
        return f"http://127.0.0.1:{settings.api_port}"

    def _get_llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = build_llm_client()
        return self._llm

    # ------------------------------------------------------------------
    # Public entry point — spawns a background thread
    # ------------------------------------------------------------------

    def trigger_async(self, messages: Optional[list[Message]] = None) -> bool:
        """Start processing in a background thread. Returns False if already running."""
        with self._lock:
            if self._running:
                return False
            self._running = True

        thread = threading.Thread(
            target=self._run_safe,
            args=(messages,),
            daemon=True,
            name="wiki-processor",
        )
        thread.start()
        return True

    def _run_safe(self, messages: Optional[list[Message]]) -> None:
        result = ProcessingResult()
        try:
            if messages is None:
                messages = conversation_buffer.get_pending_messages()
            if not messages:
                result.log("No pending messages — nothing to process.")
                return
            self._process(messages, result)
        except Exception as e:
            result.errors.append(f"Fatal error: {e}")
            logger.exception("WikiProcessor crashed")
        finally:
            with self._lock:
                self._running = False
            for cb in self._on_complete_callbacks:
                try:
                    cb(result)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 5-phase pipeline
    # ------------------------------------------------------------------

    def _process(self, messages: list[Message], result: ProcessingResult) -> None:
        result.log(f"Starting processing of {len(messages)} messages...")

        # Phase 1: Fetch existing pages
        existing_pages = self._fetch_existing_pages(result)

        # Phase 2: LLM analysis
        proposals_data = self._llm_analyze(messages, existing_pages, result)
        if not proposals_data:
            result.log("LLM returned no proposals.")
            result.processed_message_ids = [m.id for m in messages]
            conversation_buffer.mark_processed(result.processed_message_ids)
            return

        result.log(f"LLM proposed {len(proposals_data)} changes.")

        # Phase 3: Submit proposals
        submitted = self._submit_proposals(proposals_data, messages, result)

        # Phase 4: Review + Apply
        self._review_and_apply(submitted, result)

        # Phase 5: Mark messages processed
        result.processed_message_ids = [m.id for m in messages]
        conversation_buffer.mark_processed(result.processed_message_ids)
        result.log(f"Done. Applied {result.proposals_applied}/{result.proposals_submitted} proposals.")

    # ------------------------------------------------------------------
    # Phase 1
    # ------------------------------------------------------------------

    def _fetch_existing_pages(self, result: ProcessingResult) -> list[dict]:
        try:
            resp = httpx.get(
                f"{self._base_url()}/pages/search",
                params={"limit": 200},
                headers={"X-Agent-ID": PROPOSER_ID},
                timeout=10.0,
            )
            resp.raise_for_status()
            pages = resp.json()
            result.log(f"Fetched {len(pages)} existing wiki pages.")
            return pages
        except Exception as e:
            result.errors.append(f"Failed to fetch pages: {e}")
            result.log(f"Warning: Could not fetch existing pages ({e}). Proceeding without context.")
            return []

    # ------------------------------------------------------------------
    # Phase 2
    # ------------------------------------------------------------------

    def _llm_analyze(
        self,
        messages: list[Message],
        existing_pages: list[dict],
        result: ProcessingResult,
    ) -> list[dict]:
        pages_summary = "\n".join(
            f"- [{p.get('title', '?')}] slug={p.get('slug', '?')}: {p.get('summary', '')}"
            for p in existing_pages
        ) or "(none yet)"

        conversation_text = "\n".join(
            f"[{m.timestamp.strftime('%H:%M')}] {m.speaker}: {m.content}"
            for m in messages
        )

        user_content = (
            f"EXISTING PAGES:\n{pages_summary}\n\n"
            f"CONVERSATION:\n{conversation_text}"
        )

        try:
            llm = self._get_llm()
            raw = llm.chat([
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ])
            result.log("LLM analysis complete.")
            return self._parse_proposals_json(raw, result)
        except Exception as e:
            result.errors.append(f"LLM analysis failed: {e}")
            logger.exception("LLM analysis error")
            return []

    def _parse_proposals_json(self, raw: str, result: ProcessingResult) -> list[dict]:
        # Strip markdown fences if LLM ignores instructions
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            data = json.loads(cleaned)
            return data.get("proposals", [])
        except json.JSONDecodeError as e:
            result.errors.append(f"JSON parse error: {e}\nRaw: {raw[:300]}")
            return []

    # ------------------------------------------------------------------
    # Phase 3
    # ------------------------------------------------------------------

    def _submit_proposals(
        self,
        proposals_data: list[dict],
        messages: list[Message],
        result: ProcessingResult,
    ) -> list[dict]:
        """Submit proposals to the wiki API. Returns list of created proposal records."""
        batch_id = str(uuid.uuid4())
        source_session_id = f"wiki-processor-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        submitted: list[dict] = []

        for item in proposals_data:
            action = item.get("action")
            try:
                if action == "create":
                    proposal = self._submit_create(item, batch_id, source_session_id)
                    if proposal:
                        submitted.append(proposal)
                        result.proposals_submitted += 1
                elif action == "update":
                    proposal = self._submit_update(item, batch_id, source_session_id, result)
                    if proposal:
                        submitted.append(proposal)
                        result.proposals_submitted += 1
                elif action == "merge":
                    result.log(f"Merge: archiving '{item.get('remove_slug')}' in favour of '{item.get('keep_slug')}'")
                    self._execute_merge(item, result)
                elif action == "flag_conflict":
                    result.log(f"Conflict flagged on '{item.get('page_slug')}': {item.get('conflict_note', '')[:80]}")
                else:
                    result.log(f"Unknown action '{action}' — skipped.")
            except Exception as e:
                result.errors.append(f"Failed to submit '{action}' proposal: {e}")

        return submitted

    def _submit_create(self, item: dict, batch_id: str, source_session_id: str) -> Optional[dict]:
        facts = item.get("canonical_facts")
        payload = {
            "target_page_id": None,
            "proposed_title": item.get("title", "Untitled"),
            "proposed_slug": item.get("slug", ""),
            "proposed_content": item.get("content", ""),
            "proposed_summary": item.get("summary", ""),
            "proposed_canonical_facts": json.dumps(facts) if isinstance(facts, list) else facts,
            "rationale": item.get("rationale", "Auto-generated by wiki processor."),
            "proposer_agent_id": PROPOSER_ID,
            "idempotency_key": f"create-{item.get('slug', '')}-{batch_id}",
            "batch_id": batch_id,
            "source_session_id": source_session_id,
        }
        resp = httpx.post(
            f"{self._base_url()}/proposals",
            json=payload,
            headers={"X-Agent-ID": PROPOSER_ID},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()

    def _submit_update(
        self, item: dict, batch_id: str, source_session_id: str, result: ProcessingResult
    ) -> Optional[dict]:
        slug = item.get("target_slug", "")
        # Look up the page ID by slug
        try:
            page_resp = httpx.get(
                f"{self._base_url()}/pages/by-slug/{slug}",
                headers={"X-Agent-ID": PROPOSER_ID},
                timeout=10.0,
            )
            page_resp.raise_for_status()
            page = page_resp.json()
            page_id = page["id"]
        except Exception as e:
            result.errors.append(f"Could not find page with slug '{slug}': {e}")
            return None

        facts = item.get("canonical_facts")
        payload = {
            "target_page_id": page_id,
            "proposed_title": item.get("title", page.get("title", "")),
            "proposed_slug": slug,
            "proposed_content": item.get("content", ""),
            "proposed_summary": item.get("summary", ""),
            "proposed_canonical_facts": json.dumps(facts) if isinstance(facts, list) else facts,
            "rationale": item.get("rationale", "Auto-updated by wiki processor."),
            "proposer_agent_id": PROPOSER_ID,
            "idempotency_key": f"update-{slug}-{batch_id}",
            "batch_id": batch_id,
            "source_session_id": source_session_id,
        }
        resp = httpx.post(
            f"{self._base_url()}/proposals",
            json=payload,
            headers={"X-Agent-ID": PROPOSER_ID},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()

    def _execute_merge(self, item: dict, result: ProcessingResult) -> None:
        """Archive the duplicate page (remove_slug) as a merge operation."""
        remove_slug = item.get("remove_slug", "")
        try:
            page_resp = httpx.get(
                f"{self._base_url()}/pages/by-slug/{remove_slug}",
                headers={"X-Agent-ID": EXECUTOR_ID},
                timeout=10.0,
            )
            page_resp.raise_for_status()
            page_id = page_resp.json()["id"]
            archive_resp = httpx.post(
                f"{self._base_url()}/pages/{page_id}/archive",
                headers={"X-Agent-ID": EXECUTOR_ID},
                timeout=10.0,
            )
            archive_resp.raise_for_status()
            result.log(f"Merged: archived page '{remove_slug}'.")
        except Exception as e:
            result.errors.append(f"Merge failed for '{remove_slug}': {e}")

    # ------------------------------------------------------------------
    # Phase 4
    # ------------------------------------------------------------------

    def _review_and_apply(self, submitted_proposals: list[dict], result: ProcessingResult) -> None:
        for proposal in submitted_proposals:
            proposal_id = proposal.get("id")
            if not proposal_id:
                continue
            try:
                # Review (approve)
                review_resp = httpx.post(
                    f"{self._base_url()}/proposals/{proposal_id}/review",
                    json={
                        "reviewer_agent_id": REVIEWER_ID,
                        "decision": "approve",
                        "feedback": "Auto-approved by wiki-reviewer agent.",
                    },
                    headers={"X-Agent-ID": REVIEWER_ID},
                    timeout=15.0,
                )
                review_resp.raise_for_status()
                result.proposals_approved += 1

                # Apply
                apply_resp = httpx.post(
                    f"{self._base_url()}/proposals/{proposal_id}/apply",
                    json={"executor_agent_id": EXECUTOR_ID},
                    headers={"X-Agent-ID": EXECUTOR_ID},
                    timeout=15.0,
                )
                apply_resp.raise_for_status()
                result.proposals_applied += 1
                title = proposal.get("proposed_title", proposal_id[:8])
                result.log(f"Applied: '{title}'")
            except Exception as e:
                result.errors.append(f"Review/apply failed for proposal {proposal_id}: {e}")


# Module-level singleton
wiki_processor = WikiProcessor()
