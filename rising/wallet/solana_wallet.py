from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from solders.keypair import Keypair
from solders.pubkey import Pubkey


@dataclass(slots=True)
class WalletConfig:
    """Configuration for the isolated real-trading hot wallet.

    Supported private key formats:
    1) SOLANA_PRIVATE_KEY_JSON='[12,34,...]'
    2) SOLANA_PRIVATE_KEY_PATH='/secure/path/keypair.json'

    Do NOT commit this key. Use a small hot wallet only.
    """
    private_key_json: str | None = None
    private_key_path: str | None = None


def load_keypair(cfg: WalletConfig | None = None) -> Keypair:
    cfg = cfg or WalletConfig(
        private_key_json=os.getenv("SOLANA_PRIVATE_KEY_JSON"),
        private_key_path=os.getenv("SOLANA_PRIVATE_KEY_PATH"),
    )

    raw: str | None = None
    if cfg.private_key_json:
        raw = cfg.private_key_json
    elif cfg.private_key_path:
        raw = Path(cfg.private_key_path).read_text(encoding="utf-8")

    if not raw:
        raise RuntimeError(
            "Real trading requires SOLANA_PRIVATE_KEY_JSON or SOLANA_PRIVATE_KEY_PATH. "
            "Use a dedicated small hot wallet only."
        )

    raw = raw.strip()
    if raw.startswith("["):
        values = json.loads(raw)
        return Keypair.from_bytes(bytes(values))

    # Optional base64 format for deployments that store key material as base64.
    try:
        return Keypair.from_bytes(base64.b64decode(raw))
    except Exception as exc:
        raise ValueError("Unsupported SOLANA private key format") from exc


def wallet_pubkey(keypair: Keypair) -> Pubkey:
    return keypair.pubkey()
