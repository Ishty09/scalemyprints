"""
Perceptual hashing helpers.

We use the open-source `imagehash` library. The 64-bit pHash is good
for "is this the same artwork?" Hamming-distance lookups: Hamming 0-4
== effectively identical, 5-12 == near-duplicate, 13+ == different
design.

64-bit pHash is stored in Postgres as `bigint`. Hamming distance is
computed as popcount(a XOR b) and supported natively by pgvector's
`vector_bit_ops` (or computed in Python for memory stores).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image


def compute_phash(image: Image) -> int:
    """
    Return the 64-bit perceptual hash of an image as a Python int.

    `image` must be a PIL Image (caller is responsible for opening
    bytes via PIL.Image.open(BytesIO(bytes))).
    """
    import imagehash  # local import: heavy dep

    h = imagehash.phash(image, hash_size=8)  # 8x8 = 64-bit
    # `imagehash.ImageHash.hash` is a numpy bool array. Pack to int.
    bits = 0
    for row in h.hash:
        for bit in row:
            bits = (bits << 1) | int(bool(bit))
    return bits


def hamming_distance(a: int, b: int) -> int:
    """Population count of XOR — the number of differing bits."""
    return (a ^ b).bit_count()
