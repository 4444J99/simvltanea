"""Stateless seeded draws and the integer softmax shared by every play mode.

All randomness is a SHA-256 counter map (like the repository's ``sha256-counter-v1``) and all
selection arithmetic is integer, so identical inputs give identical output in any process,
whatever ``PYTHONHASHSEED`` is. No float is involved in a draw or a pick.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GRAVITY_RNG = "gravity-sha256-v1"       # kept as is: changing it would change every generated state
BITS_PER_UNIT = 8                       # a full 1.0 score difference = 8 bits of odds at T=1
# round(2**30 * 2**(r/16)), r = 0..15: integer base-2 softmax, no exp().
MANTISSA = (1073741824, 1121280436, 1170923762, 1222764986, 1276901417, 1333434672, 1392470869,
            1454120821, 1518500250, 1585730000, 1655936265, 1729250827, 1805811301, 1885761398,
            1969251188, 2056437387)
_MASK = (1 << 64) - 1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def draw64(seed: Any, *domain: Any) -> int:
    return int.from_bytes(hashlib.sha256(_canonical([GRAVITY_RNG, seed, *domain])).digest()[:8], "big")


def weighted_pick(items: list[str], n16: list[int], u: int) -> str:
    """Base-2 softmax over logits given in 1/16-bit steps, using integers only."""
    top = max(n16)
    weights = []
    for n in n16:
        q, r = divmod(n - top, 16)           # n - top = 16q + r, q <= 0
        weights.append(MANTISSA[r] >> (-q) if -q <= 62 else 0)
    total = sum(weights)
    target = (u * total) >> 64
    for item, w in zip(items, weights):
        if target < w:
            return item
        target -= w
    raise AssertionError("unreachable")


def splitmix64(state: int) -> tuple[int, int]:
    """One step of splitmix64: (next_state, output). Pure integer arithmetic (JS port: BigInt)."""
    state = (state + 0x9E3779B97F4A7C15) & _MASK
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
    return state, z ^ (z >> 31)


def sample_indices(seed64: int, size: int, count: int) -> list[int]:
    """``count`` distinct indices of range(size), seeded and order-stable (sorted ascending)."""
    if count >= size:
        return list(range(size))
    chosen: set[int] = set()
    state = seed64 & _MASK
    while len(chosen) < count:
        state, out = splitmix64(state)
        chosen.add(out % size)
    return sorted(chosen)


def shuffled(items: list[str], seed: Any, *domain: Any) -> list[str]:
    """Deterministic shuffle by sorting on a per-item hash (ties broken by the item)."""
    return sorted(items, key=lambda item: (draw64(seed, *domain, item), item))
