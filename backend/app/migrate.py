from __future__ import annotations

from .persistence import PersistenceBackend, PersistenceSettings


def main() -> None:
    backend = PersistenceBackend(PersistenceSettings.from_environment())
    backend.initialize()
    print("RNABag PostgreSQL migrations and private object-storage bucket are ready.")


if __name__ == "__main__":
    main()
