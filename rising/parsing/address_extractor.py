from __future__ import annotations

import re

# Solana base58 public keys are normally 32 bytes encoded as 32-44 chars.
SOLANA_ADDRESS_RE = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")


def extract_solana_addresses(text: str) -> list[str]:
    """Extract likely Solana token addresses while preserving order and removing duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for match in SOLANA_ADDRESS_RE.findall(text or ""):
        if match not in seen:
            seen.add(match)
            out.append(match)
    return out
