"""Deterministic text preparation without loading an embedding model."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class SourceDocument:
    kind: Literal["document", "inquiry"]
    title: str
    text: str
    path: str | None = None
    inquiry_id: int | None = None

    def __post_init__(self):
        if self.kind == "document":
            if not self.path or self.inquiry_id is not None:
                raise ValueError("document requires only a document path")
        elif self.kind == "inquiry":
            if self.path is not None or self.inquiry_id is None or self.inquiry_id <= 0:
                raise ValueError("inquiry requires only a positive inquiry ID")
        else:
            raise ValueError("unknown source kind")

    @property
    def key(self) -> str:
        return f"document:{self.path}" if self.kind == "document" else f"inquiry:{self.inquiry_id}"

    @property
    def revision(self) -> str:
        return sha256((self.title + "\n" + self.text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkDraft:
    source: SourceDocument
    number: int
    text: str


def read_documents(root: Path) -> list[SourceDocument]:
    documents = []
    for path in sorted((root / "seed/docs").glob("*.md")):
        # A symlink must not import files outside the document source directory.
        path.resolve().relative_to((root / "seed/docs").resolve())
        text = path.read_text(encoding="utf-8")
        first_heading = next((line.lstrip("# ") for line in text.splitlines() if line.startswith("# ")), path.stem)
        documents.append(SourceDocument(
            kind="document", title=first_heading, text=text,
            path=path.relative_to(root).as_posix(),
        ))
    return documents


def chunk_document(source: SourceDocument, max_chars: int = 400) -> list[ChunkDraft]:
    """Split paragraphs/headings, preserving all nonblank text in source order.

    Embedding adapters must additionally check the model's token limit.
    """
    if not 32 <= max_chars <= 2000:
        raise ValueError("chunk character limit must be between 32 and 2000")
    parts = []
    current = ""
    for paragraph in source.text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if paragraph.startswith("#") and current:
            parts.append(current)
            current = ""
        while len(paragraph) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        candidate = current + "\n\n" + paragraph if current else paragraph
        if len(candidate) > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return [ChunkDraft(source=source, number=i, text=part) for i, part in enumerate(parts)]
