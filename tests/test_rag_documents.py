"""Document source tracking and bounded deterministic chunk preparation."""

from pathlib import Path

import pytest

from logi_scope.rag.documents import SourceDocument, chunk_document, read_documents


def test_repository_documents_keep_original_paths_and_incident_ids():
    docs = read_documents(Path("."))
    incident = next(d for d in docs if d.path == "seed/docs/incident-demo-001.md")
    chunks = chunk_document(incident)
    assert any("INC-DEMO-001" in c.text for c in chunks)
    assert all(c.source.key == "document:seed/docs/incident-demo-001.md" for c in chunks)
    assert [c.number for c in chunks] == list(range(len(chunks)))


def test_long_paragraph_is_split_without_losing_text():
    source = SourceDocument(kind="document", title="架空", text="あ" * 1000, path="seed/docs/test.md")
    chunks = chunk_document(source, max_chars=100)
    assert all(0 < len(c.text) <= 100 for c in chunks)
    assert "".join(c.text for c in chunks) == source.text
    assert chunks == chunk_document(source, max_chars=100)


def test_changed_source_text_changes_revision():
    before = SourceDocument(kind="inquiry", title="架空問い合わせ", text="旧回答", inquiry_id=501)
    after = SourceDocument(kind="inquiry", title="架空問い合わせ", text="新回答", inquiry_id=501)
    assert before.key == after.key == "inquiry:501"
    assert before.revision != after.revision


@pytest.mark.parametrize("kwargs", [
    {"kind": "document", "path": None},
    {"kind": "document", "path": "seed/docs/test.md", "inquiry_id": 1},
    {"kind": "inquiry", "inquiry_id": None},
    {"kind": "inquiry", "inquiry_id": 0},
    {"kind": "inquiry", "inquiry_id": 1, "path": "seed/docs/test.md"},
])
def test_source_cannot_mix_document_and_inquiry_origins(kwargs):
    with pytest.raises(ValueError):
        SourceDocument(title="架空", text="本文", **kwargs)


def test_document_symlink_cannot_read_outside_source_directory(tmp_path):
    root = tmp_path / "repository"
    docs = root / "seed/docs"
    docs.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (docs / "linked.md").symlink_to(outside)
    with pytest.raises(ValueError):
        read_documents(root)
