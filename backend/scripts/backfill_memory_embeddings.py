"""Calcula el embedding de las memorias que no lo tienen (creadas antes de
agregar app/embeddings/, o guardadas cuando el provider falló). Correr una
sola vez después de activar EMBEDDING_PROVIDER=fastembed en .env:

    cd backend
    python scripts/backfill_memory_embeddings.py

Sin esto, las memorias viejas siguen funcionando (búsqueda por LIKE) pero
no entran en el ranking semántico de search_memories().
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.memory.service import _embed_text  # noqa: E402
from app.memory.models import MemoryEntry  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        pending = db.query(MemoryEntry).filter(MemoryEntry.embedding.is_(None)).all()
        if not pending:
            print("Nada para procesar: todas las memorias ya tienen embedding.")
            return

        updated = 0
        failed = 0
        for entry in pending:
            vector = _embed_text(entry.content)
            if vector is None:
                failed += 1
                continue
            entry.embedding = vector
            updated += 1
        db.commit()
        print(f"Listo: {updated} memoria(s) actualizadas, {failed} fallaron.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
