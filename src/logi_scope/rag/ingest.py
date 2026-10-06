"""Regenerate the derived index, then replace it in one short transaction."""

import argparse
from hashlib import sha256
from pathlib import Path
import re

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, create_engine, delete, select
from sqlalchemy.orm import Session

from logi_scope.db.models import Chunk, Inquiry
from logi_scope.rag.documents import SourceDocument, chunk_document, read_documents
from logi_scope.rag.embeddings import EMBEDDING_ID, E5Embedder


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INGEST_DATABASE_", extra="ignore")
    host: str = "db"
    port: int = 5432
    name: str = "logi_scope"
    password: SecretStr

    def engine(self):
        return create_engine(URL.create("postgresql+psycopg", username="logi_scope_ingest",
            password=self.password.get_secret_value(), host=self.host, port=self.port, database=self.name),
            hide_parameters=True, connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"})


def inquiry_document(row: Inquiry) -> SourceDocument:
    return SourceDocument(kind="inquiry", title=row.subject, inquiry_id=row.id,
        text=f"問い合わせID: {row.id}\n顧客ID: {row.customer_id}\n荷物ID: {row.shipment_id or 'なし'}\n"
             f"受付日時: {row.created_at.isoformat()}\n\n{row.body}\n\n対応内容: {row.resolution}")


def load_sources(engine, root: Path) -> list[SourceDocument]:
    documents = read_documents(root)
    with Session(engine) as session:
        documents.extend(inquiry_document(row) for row in session.scalars(select(Inquiry).order_by(Inquiry.id)))
    return documents


def prepare_index(documents: list[SourceDocument], embedder) -> list[Chunk]:
    drafts = [chunk for source in documents for chunk in chunk_document(source)]
    # All CPU work completes before starting a write transaction.
    vectors = embedder.encode([c.source.title + "\n" + c.text for c in drafts])
    if len(vectors) != len(drafts):
        raise ValueError("embedding_count_mismatch")
    rows = []
    for draft, vector in zip(drafts, vectors, strict=True):
        source = draft.source
        identity = f"{source.key}:{source.revision}:{draft.number}:{EMBEDDING_ID}"
        references = sorted(set(re.findall(r"(?<![A-Za-z0-9-])(?:INC|SHP)-[A-Za-z0-9-]+", source.text)))
        rows.append(Chunk(id=sha256(identity.encode()).hexdigest(), source_key=source.key,
            kind=source.kind, document_path=source.path, inquiry_id=source.inquiry_id,
            chunk_number=draft.number, title=source.title, body=draft.text,
            source_revision=source.revision, embedding_id=EMBEDDING_ID,
            reference_ids=references, embedding=vector))
    return rows


def replace_index(session: Session, rows: list[Chunk]) -> None:
    session.execute(delete(Chunk))
    session.add_all(rows)
    session.flush()


def main():
    parser = argparse.ArgumentParser(description="Regenerate LogiScope search data")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    engine = IngestSettings().engine()
    try:
        documents = load_sources(engine, args.root)
        if not documents:
            raise ValueError("no_source_documents")
        rows = prepare_index(documents, E5Embedder())
        with Session(engine) as session, session.begin():
            replace_index(session, rows)
        print(f"Rebuilt {len(rows)} chunks from {len(documents)} sources with {EMBEDDING_ID}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
