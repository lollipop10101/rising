from __future__ import annotations

from rising.settings import EnvSettings
from rising.storage.database import Database


def main() -> None:
    db = Database(EnvSettings().database_url)
    print(db.summary())


if __name__ == "__main__":
    main()
