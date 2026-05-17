"""Unit tests for the in-memory session store.

Coverage targets:
  - ConversationHistory  sliding-window eviction, system-prompt pinning, serialisation
  - ProjectMetadata      Pydantic validation and default values
  - Session              construction defaults
  - SessionStore         create / get lifecycle
"""
from __future__ import annotations

import pytest

from app.services.sessions import (
    MAX_CONVERSATION_TURNS,
    ConversationHistory,
    ProjectMetadata,
    Session,
    SessionStore,
)


# ---------------------------------------------------------------------------
# ConversationHistory
# ---------------------------------------------------------------------------


class TestConversationHistoryEmpty:
    def test_empty_history_returns_no_messages(self):
        history = ConversationHistory()
        assert history.messages() == []

    def test_len_is_zero_when_empty(self):
        history = ConversationHistory()
        assert len(history) == 0

    def test_as_dicts_returns_empty_list(self):
        history = ConversationHistory()
        assert history.as_dicts() == []


class TestConversationHistorySystemPrompt:
    def test_system_prompt_at_construction_is_first_message(self):
        history = ConversationHistory(system_prompt="Be helpful.")
        msgs = history.messages()
        assert len(msgs) == 1
        assert msgs[0].role == "system"
        assert msgs[0].content == "Be helpful."

    def test_system_prompt_counted_in_len(self):
        history = ConversationHistory(system_prompt="Be helpful.")
        assert len(history) == 1

    def test_add_system_message_replaces_pinned_prompt(self):
        history = ConversationHistory(system_prompt="Old prompt.")
        history.add("system", "New prompt.")
        msgs = history.messages()
        assert len(msgs) == 1
        assert msgs[0].content == "New prompt."

    def test_system_prompt_stays_first_after_user_messages(self):
        history = ConversationHistory(system_prompt="You are an estimator.")
        history.add("user", "Hello")
        history.add("assistant", "Hi")
        assert history.messages()[0].role == "system"


class TestConversationHistoryOrdering:
    def test_messages_in_insertion_order(self):
        history = ConversationHistory()
        history.add("user", "first")
        history.add("assistant", "second")
        history.add("user", "third")
        roles = [m.role for m in history.messages()]
        contents = [m.content for m in history.messages()]
        assert roles == ["user", "assistant", "user"]
        assert contents == ["first", "second", "third"]

    def test_as_dicts_format_matches_llm_api(self):
        history = ConversationHistory(system_prompt="sys")
        history.add("user", "hello")
        result = history.as_dicts()
        assert result == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]


class TestConversationHistorySlidingWindow:
    def test_oldest_turns_evicted_when_limit_exceeded(self):
        history = ConversationHistory(max_turns=4)
        for i in range(5):
            history.add("user", f"msg-{i}")
        contents = [m.content for m in history.messages()]
        assert "msg-0" not in contents
        assert "msg-4" in contents

    def test_system_prompt_never_evicted_during_overflow(self):
        history = ConversationHistory(system_prompt="Keep me.", max_turns=2)
        for i in range(5):
            history.add("user", f"msg-{i}")
        first = history.messages()[0]
        assert first.role == "system"
        assert first.content == "Keep me."

    def test_window_does_not_grow_beyond_max_turns(self):
        max_turns = 6
        history = ConversationHistory(max_turns=max_turns)
        for i in range(max_turns + 10):
            history.add("user", f"msg-{i}")
        # only non-system messages counted against the window
        non_system = [m for m in history.messages() if m.role != "system"]
        assert len(non_system) == max_turns

    def test_default_max_turns_matches_module_constant(self):
        history = ConversationHistory()
        for i in range(MAX_CONVERSATION_TURNS + 1):
            history.add("user", f"msg-{i}")
        non_system = [m for m in history.messages() if m.role != "system"]
        assert len(non_system) == MAX_CONVERSATION_TURNS


# ---------------------------------------------------------------------------
# ProjectMetadata
# ---------------------------------------------------------------------------


class TestProjectMetadataDefaults:
    def test_all_fields_default_to_none_or_empty(self):
        meta = ProjectMetadata()
        assert meta.project_name is None
        assert meta.assumed_team_size is None
        assert meta.mentioned_technologies == []
        assert meta.agreed_scope is None

    def test_mentioned_technologies_default_is_independent_across_instances(self):
        meta1 = ProjectMetadata()
        meta2 = ProjectMetadata()
        meta1.mentioned_technologies.append("Django")
        assert meta2.mentioned_technologies == []


class TestProjectMetadataValidation:
    def test_team_size_must_be_at_least_one(self):
        with pytest.raises(Exception):
            ProjectMetadata(assumed_team_size=0)

    def test_valid_full_metadata_is_accepted(self):
        meta = ProjectMetadata(
            project_name="LIDR Platform",
            assumed_team_size=5,
            mentioned_technologies=["FastAPI", "Angular", "PostgreSQL"],
            agreed_scope="MVP with auth and estimation module.",
        )
        assert meta.project_name == "LIDR Platform"
        assert meta.assumed_team_size == 5
        assert len(meta.mentioned_technologies) == 3


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class TestSession:
    def test_session_has_empty_history_by_default(self):
        session = Session(session_id="abc-123")
        assert len(session.history) == 0

    def test_session_has_default_metadata(self):
        session = Session(session_id="abc-123")
        assert session.metadata.project_name is None

    def test_session_id_is_stored(self):
        session = Session(session_id="test-id")
        assert session.session_id == "test-id"


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class TestSessionStoreCreate:
    def test_create_returns_session_with_uuid_id(self):
        store = SessionStore()
        session = store.create()
        import re
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(session.session_id)

    def test_each_create_produces_unique_session_id(self):
        store = SessionStore()
        ids = {store.create().session_id for _ in range(50)}
        assert len(ids) == 50

    def test_store_len_grows_with_each_create(self):
        store = SessionStore()
        store.create()
        store.create()
        assert len(store) == 2


class TestSessionStoreGet:
    def test_get_returns_session_after_create(self):
        store = SessionStore()
        session = store.create()
        retrieved = store.get(session.session_id)
        assert retrieved is session

    def test_get_returns_none_for_unknown_id(self):
        store = SessionStore()
        assert store.get("does-not-exist") is None

    def test_get_returns_same_object_identity(self):
        store = SessionStore()
        s1 = store.create()
        s2 = store.get(s1.session_id)
        assert s1 is s2

    def test_mutations_via_get_are_persisted(self):
        store = SessionStore()
        session = store.create()
        store.get(session.session_id).metadata.project_name = "Updated"
        assert store.get(session.session_id).metadata.project_name == "Updated"
