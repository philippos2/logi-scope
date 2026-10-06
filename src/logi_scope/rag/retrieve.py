"""Exact cosine retrieval through SQLAlchemy/pgvector with read-only access."""

import asyncio

from sqlalchemy import select

from logi_scope.db.models import Chunk
from logi_scope.rag.embeddings import EMBEDDING_ID


async def retrieve(sessions, embedder, args):
    # CPU embedding finishes before checking out a DB connection.
    vector = (await asyncio.to_thread(embedder.encode, [args.query], query=True))[0]
    async with sessions() as session:
        mismatch = await session.scalar(select(Chunk.id).where(Chunk.embedding_id != EMBEDDING_ID).limit(1))
        if mismatch is not None:
            raise ValueError("embedding_index_mismatch")
        distance = Chunk.embedding.cosine_distance(vector)
        query = select(Chunk, distance.label("distance")).where(Chunk.embedding_id == EMBEDDING_ID)
        if args.kind is not None:
            query = query.where(Chunk.kind == args.kind)
        if args.reference_id is not None:
            query = query.where(Chunk.reference_ids.contains([args.reference_id]))
        rows = (await session.execute(query.order_by(distance, Chunk.id).limit(args.limit + 1))).all()
        records = [{"chunk_id": c.id, "kind": c.kind, "source_key": c.source_key,
            "document_path": c.document_path, "inquiry_id": c.inquiry_id,
            "chunk_number": c.chunk_number, "title": c.title, "text": c.body,
            "source_revision": c.source_revision, "embedding_id": c.embedding_id,
            "score": round(1 - float(d), 6)}
            for c, d in rows[:args.limit]]
    return records, len(rows) > args.limit
