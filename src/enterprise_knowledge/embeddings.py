"""Embedding providers (§25: no single-vendor lock-in).

`Embedder` is the contract. Two implementations ship:

* `DeterministicEmbedder` -- offline, stdlib-only, reproducible. Default for
  tests, CI and the offline benchmark (§18), so a regression run costs no API
  calls and produces identical vectors on every machine.
* `OpenAIEmbedder` -- `text-embedding-3-small`, the production provider from the
  original specification.

Both emit unit-norm vectors of `dim` floats, so cosine distance and inner
product agree and the same schema serves either provider.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol, runtime_checkable

from .errors import ConfigurationError, EmbeddingError

__all__ = ["Embedder", "DeterministicEmbedder", "OpenAIEmbedder", "build_embedder"]

Vector = list[float]


@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors. Implementations must be thread-safe."""

    model: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        """Embed a batch for indexing."""

    def embed_query(self, text: str) -> Vector:
        """Embed a single query. Providers with asymmetric models override this."""


def _l2_normalize(vec: Vector) -> Vector:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        raise EmbeddingError("refusing to emit a zero vector: cosine distance is undefined")
    return [x / norm for x in vec]


class DeterministicEmbedder:
    """Hash-based embedder: same text -> same vector, forever, with no network.

    This is a *test double with real arithmetic*, not a semantic model. It gives
    the offline benchmark a stable, zero-cost backend for comparing retrieval
    strategies (dense vs hybrid vs reranked) against a fixture corpus. It has no
    semantic understanding, so absolute Hit@K numbers from an offline run are
    only meaningful relative to other offline runs -- never quote them as
    production retrieval quality (§18).
    """

    def __init__(self, dim: int = 1536, model: str = "deterministic-sha256") -> None:
        if dim < 8:
            raise ConfigurationError("embedding dim must be >= 8")
        self.dim = dim
        self.model = model

    def _vector(self, text: str) -> Vector:
        # Expand a SHA-256 chain into `dim` floats: cheap, deterministic, and
        # dependency-free. Note this hashes the *whole* string, so near-identical
        # texts get unrelated vectors -- there is no lexical or semantic
        # neighbourhood here by construction.
        out: Vector = []
        seed = text.strip().lower().encode("utf-8")
        counter = 0
        while len(out) < self.dim:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for i in range(0, len(digest), 4):
                if len(out) >= self.dim:
                    break
                (raw,) = struct.unpack(">I", digest[i : i + 4])
                out.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            counter += 1
        return _l2_normalize(out)

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> Vector:
        return self._vector(text)


class OpenAIEmbedder:
    """`text-embedding-3-small` via the OpenAI SDK.

    The SDK is an optional extra (`pip install -e '.[openai]'`) and is imported
    lazily so the core contract stays installable without it.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
    ) -> None:
        self.model = model
        self.dim = dim
        self._api_key = api_key
        self._client = None  # lazily constructed

    def _ensure_client(self) -> object:
        raise NotImplementedError(
            "Phase 1: wire the OpenAI client here (batching, retry/backoff, "
            "dimension assertion against EK_EMBEDDING_DIM)"
        )

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        raise NotImplementedError("Phase 1")

    def embed_query(self, text: str) -> Vector:
        raise NotImplementedError("Phase 1")


def build_embedder(name: str, *, dim: int, model: str, api_key: str | None = None) -> Embedder:
    """Factory used by the service so no call site imports a provider directly."""
    if name == "deterministic":
        return DeterministicEmbedder(dim=dim)
    if name == "openai":
        if not api_key:
            raise ConfigurationError("OpenAI embedder requires an API key")
        return OpenAIEmbedder(api_key=api_key, model=model, dim=dim)
    raise ConfigurationError(f"unknown embedder {name!r}: expected 'deterministic' or 'openai'")
