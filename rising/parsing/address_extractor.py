from __future__ import annotations
import re
SOLANA_ADDRESS_RE = re.compile(r"(?<![A-Za-z0-9])[1-9A-HJ-NP-Za-km-z]{32,44}(?![A-Za-z0-9])")
def extract_solana_addresses(text: str) -> list[str]:
    seen=set(); out=[]
    for m in SOLANA_ADDRESS_RE.findall(text or ''):
        if m not in seen:
            seen.add(m); out.append(m)
    return out
def is_signal_address(text: str) -> bool:
    a=extract_solana_addresses(text.strip()); return len(a)==1 and text.strip()==a[0]
