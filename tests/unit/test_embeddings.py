"""Offline embedder guarantees that the CI benchmark relies on (§18, §25)."""

from __future__ import annotations

import math

import pytest

from enterprise_knowledge.embeddings import DeterministicEmbedder, Embedder, build_embedder
from enterprise_knowledge.errors import ConfigurationError


def test_deterministic_across_calls_and_processes() -> None:
    a = DeterministicEmbedder(dim=64).embed_query("annual leave")
    b = DeterministicEmbedder(dim=64).embed_query("annual leave")
    assert a == b


def test_vectors_are_unit_norm_and_correct_width() -> None:
    vec = DeterministicEmbedder(dim=1536).embed_query("x")
    assert len(vec) == 1536
    assert math.sqrt(sum(v * v for v in vec)) == pytest.approx(1.0)


def test_documents_and_query_share_the_space() -> None:
    embedder = DeterministicEmbedder(dim=64)
    (doc,) = embedder.embed_documents(["annual leave"])
    assert doc == embedder.embed_query("annual leave")


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ConfigurationError):
        build_embedder("word2vec", dim=64, model="x")


def test_openai_requires_a_key() -> None:
    with pytest.raises(ConfigurationError):
        build_embedder("openai", dim=1536, model="text-embedding-3-small", api_key=None)


def test_implements_the_protocol() -> None:
    assert isinstance(DeterministicEmbedder(dim=64), Embedder)
