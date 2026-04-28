from __future__ import annotations

import sys
from rising.parsing.address_extractor import extract_solana_addresses


def main() -> None:
    text = " ".join(sys.argv[1:])
    for addr in extract_solana_addresses(text):
        print(addr)


if __name__ == "__main__":
    main()
