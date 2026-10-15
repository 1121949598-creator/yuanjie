from __future__ import annotations

import math
from collections import Counter


def shannon_entropy(value: str) -> float:
    """Bits per character; an auxiliary signal, never a secret classifier."""
    if not value:
        return 0.0
    return -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in Counter(value).values()
    )
