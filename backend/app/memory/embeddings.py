"""Optional semantic embeddings (Embedder/Retriever, master 8.3). Lexical retrieval always works; embeddings
only augment it. Model name is stored per vector so a provider change never mixes incompatible vectors."""
from __future__ import annotations

import httpx

from ..config import get_settings


class Embedder:
    model = "none"

    def available(self) -> bool:
        return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedder not configured")


class OpenAICompatibleEmbedder(Embedder):
    def __init__(self) -> None:
        s = get_settings()
        self.base_url = (s.embedding_base_url or "").rstrip("/")
        self.api_key = s.embedding_api_key
        self.model = s.embedding_model
        self.dimensions = s.embedding_dimensions
        self.region = s.embedding_region

    def available(self) -> bool:
        return bool(self.base_url) and self.region in get_settings().allowed_region_set()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{self.base_url}/embeddings", headers=headers,
                                  json={"model": self.model, "input": texts, "dimensions": self.dimensions})
        r.raise_for_status()
        vecs = [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        for v in vecs:
            if len(v) != self.dimensions:
                raise RuntimeError("embedding dimension mismatch")
        return vecs


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = OpenAICompatibleEmbedder() if get_settings().embedding_base_url else Embedder()
    return _embedder


def set_embedder(e: Embedder | None) -> None:
    global _embedder
    _embedder = e
