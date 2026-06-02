"""
CLIP-based image embedder.

Default model: `openai/clip-vit-base-patch32` via sentence-transformers
(512-dim vectors). Smaller than ViT-L/14 (768-dim) but plenty good
for "same design across marketplaces" detection while being CPU-fast.

The model is lazy-loaded on first embed call to keep cold-start cheap.
If sentence-transformers / torch aren't installed, we fall back to a
deterministic stub embedder so unit tests and CI don't need GPU/torch.

Production deploy notes:
- This DOES NOT run on Cloudflare Workers (no torch). For prod, host
  the FastAPI worker as a regular Python service (Fly.io, Railway,
  Modal, RunPod) and have the Cloudflare Worker proxy /api/v1/spy/*
  to that backend.
- A future Phase will swap this for an HTTP call to a dedicated
  CLIP-serving microservice (Modal / Banana / Replicate) and remove
  the torch dep from the main API process.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
from typing import ClassVar, cast

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.ports import EmbeddingResult, ImageEmbedder
from scalemyprints.infrastructure.image_search.phash import compute_phash

logger = get_logger(__name__)


class CLIPImageEmbedder(ImageEmbedder):
    """
    Production CLIP embedder using sentence-transformers.

    Model and preprocessor are cached at the class level so multiple
    instances share them.
    """

    _model: ClassVar[object | None] = None
    _model_name: ClassVar[str] = "clip-ViT-B-32"
    _dim: ClassVar[int] = 512
    _lock: ClassVar[asyncio.Lock | None] = None

    def __init__(self, model_name: str | None = None) -> None:
        if model_name:
            CLIPImageEmbedder._model_name = model_name

    @property
    def embedding_dim(self) -> int:
        return self._dim

    async def embed(self, image_bytes: bytes) -> EmbeddingResult:
        start = time.monotonic()
        sha = hashlib.sha256(image_bytes).hexdigest()

        try:
            from PIL import Image  # local import: heavy dep
        except ImportError as e:
            logger.warning("clip_pillow_missing", error=str(e))
            return _stub_embedding(image_bytes, sha, error="pillow_not_installed")

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            return EmbeddingResult(
                sha256=sha,
                phash=0,
                clip_embedding=[0.0] * self._dim,
                width=1,
                height=1,
                bytes_size=len(image_bytes),
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"image_decode_failed: {e}",
            )

        # ---- pHash (fast, CPU-only) ------------------------------------------
        try:
            phash = compute_phash(image)
        except Exception as e:
            logger.warning("phash_failed_falling_back_zero", error=str(e))
            phash = 0

        # ---- CLIP (lazy-load model) ------------------------------------------
        try:
            model = await self._ensure_model()
        except Exception as e:
            logger.warning("clip_model_load_failed_using_stub", error=str(e))
            return _stub_embedding(
                image_bytes,
                sha,
                phash=phash,
                width=image.width,
                height=image.height,
                error=None,
            )

        try:
            vector = await asyncio.to_thread(_encode, model, image)
        except Exception as e:
            return EmbeddingResult(
                sha256=sha,
                phash=phash,
                clip_embedding=[0.0] * self._dim,
                width=image.width,
                height=image.height,
                bytes_size=len(image_bytes),
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"clip_encode_failed: {e}",
            )

        return EmbeddingResult(
            sha256=sha,
            phash=phash,
            clip_embedding=vector,
            width=image.width,
            height=image.height,
            bytes_size=len(image_bytes),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def _ensure_model(self) -> object:
        # Class-level lazy init guarded by an asyncio lock
        if CLIPImageEmbedder._model is not None:
            return CLIPImageEmbedder._model
        if CLIPImageEmbedder._lock is None:
            CLIPImageEmbedder._lock = asyncio.Lock()

        async with CLIPImageEmbedder._lock:
            if CLIPImageEmbedder._model is not None:
                return CLIPImageEmbedder._model
            from sentence_transformers import SentenceTransformer  # heavy

            logger.info("clip_model_loading", model=CLIPImageEmbedder._model_name)
            model = await asyncio.to_thread(SentenceTransformer, CLIPImageEmbedder._model_name)
            CLIPImageEmbedder._model = model
            logger.info("clip_model_loaded", model=CLIPImageEmbedder._model_name)
            return model


def _encode(model: object, image: object) -> list[float]:
    encode = cast("object", model).encode  # type: ignore[attr-defined]
    vec = encode([image], convert_to_numpy=True, normalize_embeddings=True)[0]
    return [float(x) for x in vec]


class StubImageEmbedder(ImageEmbedder):
    """
    Test / fallback embedder — deterministic vector derived from SHA-256.

    Useful in CI where we don't want to download CLIP weights. The output
    is reproducible (same bytes → same vector) so tests can assert hits.
    """

    def __init__(self, dim: int = 512) -> None:
        self._dim = dim

    @property
    def embedding_dim(self) -> int:
        return self._dim

    async def embed(self, image_bytes: bytes) -> EmbeddingResult:
        start = time.monotonic()
        sha = hashlib.sha256(image_bytes).hexdigest()
        # Stretch sha bytes into a [-1, 1] vector of length self._dim
        vec = _deterministic_vector(sha, self._dim)
        # Try to compute pHash from image; if Pillow missing, just use first 64 bits
        phash = _phash_or_fallback(image_bytes, sha)
        return EmbeddingResult(
            sha256=sha,
            phash=phash,
            clip_embedding=vec,
            width=1,
            height=1,
            bytes_size=len(image_bytes),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _stub_embedding(
    image_bytes: bytes,
    sha: str,
    *,
    phash: int | None = None,
    width: int = 1,
    height: int = 1,
    error: str | None = None,
) -> EmbeddingResult:
    return EmbeddingResult(
        sha256=sha,
        phash=phash or _phash_or_fallback(image_bytes, sha),
        clip_embedding=_deterministic_vector(sha, 512),
        width=width,
        height=height,
        bytes_size=len(image_bytes),
        duration_ms=0,
        error=error,
    )


def _phash_or_fallback(image_bytes: bytes, sha: str) -> int:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return compute_phash(img)
    except Exception:
        return int.from_bytes(bytes.fromhex(sha[:16]), "big")


def _deterministic_vector(seed_hex: str, dim: int) -> list[float]:
    """Produce a unit-norm float vector seeded by `seed_hex`."""
    import math

    raw = bytes.fromhex(seed_hex)
    # Tile / expand to `dim` bytes
    repeats = (dim + len(raw) - 1) // len(raw)
    expanded = (raw * repeats)[:dim]
    # Map bytes 0..255 to -1.0..1.0
    vec = [(b / 127.5) - 1.0 for b in expanded]
    # Normalize to unit length
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]
