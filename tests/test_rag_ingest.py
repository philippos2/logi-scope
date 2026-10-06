"""Derived index preparation uses fake vectors, no model downloads."""

import pytest

from logi_scope.rag.documents import SourceDocument
from logi_scope.rag.embeddings import DIMENSIONS, EMBEDDING_ID
from logi_scope.rag.ingest import prepare_index


class FakeEmbedder:
    def encode(self, texts, *, query=False):
        return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]


def test_derived_rows_keep_origin_revision_and_reference_ids():
    source = SourceDocument(kind="document", title="架空報告", path="seed/docs/test.md",
        text="障害INC-DEMO-001に関連するSHP-DEMO-001は遅延。")
    rows = prepare_index([source], FakeEmbedder())
    assert rows[0].document_path == source.path and rows[0].inquiry_id is None
    assert rows[0].source_revision == source.revision
    assert rows[0].embedding_id == EMBEDDING_ID
    assert rows[0].reference_ids == ["INC-DEMO-001", "SHP-DEMO-001"]
    assert rows[0].id == prepare_index([source], FakeEmbedder())[0].id


def test_inquiry_chunk_keeps_original_id():
    rows = prepare_index([SourceDocument(kind="inquiry", title="架空", text="対応内容", inquiry_id=501)], FakeEmbedder())
    assert rows[0].inquiry_id == 501 and rows[0].document_path is None


def test_bad_embedding_count_does_not_prepare_partial_index():
    class BadEmbedder:
        def encode(self, texts):
            return []
    with pytest.raises(ValueError, match="embedding_count_mismatch"):
        prepare_index([SourceDocument(kind="inquiry", title="架空", text="本文", inquiry_id=501)], BadEmbedder())
