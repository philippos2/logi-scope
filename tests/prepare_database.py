"""Deterministic index for a disposable CI database, never semantic model evaluation."""

import os
from pathlib import Path

from sqlalchemy.orm import Session

from logi_scope.rag.embeddings import DIMENSIONS
from logi_scope.rag.ingest import IngestSettings, load_sources, prepare_index, replace_index


class TestEmbedder:
    def encode(self, texts, *, query=False):
        return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]


def main():
    if os.environ.get("LOGISCOPE_DB_TESTS") != "1":
        raise SystemExit("LOGISCOPE_DB_TESTS=1 required; use only a disposable test database")
    engine = IngestSettings().engine()
    try:
        rows = prepare_index(load_sources(engine, Path(".")), TestEmbedder())
        with Session(engine) as session, session.begin():
            replace_index(session, rows)
        print(f"Prepared {len(rows)} deterministic test chunks; no model downloaded")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
