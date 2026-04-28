import re
from typing import List

# Solana base58 addresses are usually 32-44 chars and exclude 0/O/I/l.
SOLANA_ADDRESS_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")

def extract_solana_addresses(text: str) -> List[str]:
    if not text:
        return []
    seen = []
    for m in SOLANA_ADDRESS_RE.findall(text):
        if m not in seen:
            seen.append(m)
    return seen
