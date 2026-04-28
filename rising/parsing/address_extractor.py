import re
from typing import List, Optional

# Solana base58 addresses: 32-44 chars, excludes 0/O/I/l
SOLANA_ADDRESS_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")

# Token symbol pattern from phanes_bot replies: $SYMBOL or **Symbol Name**
TOKEN_SYMBOL_RE = re.compile(r'\$([A-Za-z]+)|\*{2,}([A-Za-z]+)')
TOKEN_NAME_RE = re.compile(r'\*\*([A-Z][A-Za-z\s]+)\*\*')

def extract_solana_addresses(text: str) -> List[str]:
    """Extract all Solana addresses from any text."""
    if not text:
        return []
    seen = []
    for m in SOLANA_ADDRESS_RE.findall(text):
        if m not in seen:
            seen.append(m)
    return seen

def is_signal_address(text: str) -> bool:
    """Return True if the message is ONLY a Solana address (no other content)."""
    if not text:
        return False
    stripped = text.strip()
    addrs = SOLANA_ADDRESS_RE.findall(stripped)
    if not addrs:
        return False
    # Must be exactly one address and nothing else
    if len(addrs) == 1:
        # The entire message (minus whitespace) should equal the address
        return stripped.replace(addrs[0], '').strip() == ''
    return False

def extract_token_symbol(text: str) -> Optional[str]:
    """Extract token symbol from phanes_bot reply text."""
    if not text:
        return None
    m = TOKEN_SYMBOL_RE.search(text)
    if m:
        return m.group(1) or m.group(2)
    # Fallback: look for **Name** pattern
    m2 = TOKEN_NAME_RE.search(text)
    if m2:
        return m2.group(1).split()[0] if ' ' in m2.group(1) else m2.group(1)
    return None
