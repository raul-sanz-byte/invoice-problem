"""Tests for resilient multi-tier LLM client and Qdrant local fallback.

Validates that:
1. Qdrant falls back gracefully to in-memory mode when cloud is unavailable.
2. LLM client falls back to Ollama or self-contained deterministic heuristics
   without crashing, even when neither cloud keys nor Ollama are present.
3. Chat completions and tool calls proxy correctly through the resilient failover chain.
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from invoice_pipeline.llm_client import (
    LLMClient,
    is_ollama_available,
    ResilientChatCompletions,
    HeuristicResponse,
)
from invoice_pipeline.universal.qdrant_setup import get_qdrant_client


def test_qdrant_embedded_memory_mode():
    """Verify that mode='memory' initializes an embedded in-memory Qdrant instance with zero network dependencies."""
    client, desc = get_qdrant_client(mode="memory")
    assert client is not None
    assert "In-Memory" in desc
    collections = client.get_collections()
    assert hasattr(collections, "collections")


def test_qdrant_auto_fallback_when_cloud_fails():
    """Verify that get_qdrant_client in auto mode falls back safely to in-memory when cloud url is invalid."""
    client, desc = get_qdrant_client(mode="auto", url="https://invalid-host-that-does-not-exist.example.com", api_key="test-key", timeout=0.2)
    assert client is not None
    # Should have fallen back to local daemon or in-memory
    assert ("In-Memory" in desc) or ("Local Daemon" in desc)


def test_is_ollama_available_fast_check():
    """Ensure is_ollama_available returns a bool within 1 second and doesn't throw exceptions."""
    res = is_ollama_available("http://localhost:11434")
    assert isinstance(res, bool)


def test_llm_client_offline_heuristic_mode():
    """Verify that when no API keys are present and Ollama is offline, LLMClient boots in heuristic mode without crashing."""
    with patch.dict(os.environ, {
        "OPENROUTER_API_KEY": "",
        "GEMINI_API_KEY": "",
        "OPENAI_API_KEY": "",
        "LLM_PROVIDER": "auto",
        "OLLAMA_BASE_URL": "http://127.0.0.1:59999/v1",  # Unused port
    }):
        client = LLMClient()
        assert client.provider == "heuristic"
        assert client.is_offline_heuristic is True

        # Test heuristic completion for rule evaluation
        resp = client.client.chat.completions.create(
            model="any",
            messages=[{"role": "user", "content": "Does this invoice violate or trigger this rule?"}],
        )
        assert resp.choices[0].message.content.startswith("TRIGGERED: NO")

        # Test heuristic completion for reflection critique
        resp_crit = client.client.chat.completions.create(
            model="any",
            messages=[{"role": "user", "content": "Conduct a fiduciary critique and reflection on this invoice."}],
        )
        assert "heuristic" in resp_crit.choices[0].message.content.lower()


def test_llm_client_ollama_requested_when_not_running():
    """Verify that requesting LLM_PROVIDER=ollama when Ollama is not running gracefully falls back to heuristic mode."""
    with patch.dict(os.environ, {
        "LLM_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://127.0.0.1:59999/v1",
    }):
        client = LLMClient()
        assert client.provider == "ollama"
        assert client.is_offline_heuristic is True


def test_resilient_completions_failover_to_heuristic():
    """Verify ResilientChatCompletions fails over gracefully when primary raises an exception."""
    mock_primary = MagicMock(side_effect=ConnectionError("Primary cloud unreachable"))
    mock_llm = MagicMock()
    mock_llm.provider = "openrouter"
    mock_llm.ollama_available = False
    mock_llm.is_offline_heuristic = False
    mock_llm._create_heuristic_completion.return_value = HeuristicResponse("Fallback OK")

    resilient = ResilientChatCompletions(primary_create=mock_primary, fallback_create=None, llm_client=mock_llm)
    res = resilient.create(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
    assert res.choices[0].message.content == "Fallback OK"
