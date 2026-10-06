"""CPU retrieval smoke check against fictional documents/inquiries, without LLM."""

import json
import time
from pathlib import Path

import numpy as np

from logi_scope.rag.documents import SourceDocument, chunk_document, read_documents
from logi_scope.rag.embeddings import EMBEDDING_ID, E5Embedder


def main():
    started = time.monotonic()
    embedder = E5Embedder()
    loaded = time.monotonic()
    documents = read_documents(Path("."))
    for row in json.loads(Path("seed/business.json").read_text())["inquiries"]:
        documents.append(SourceDocument(kind="inquiry", title=row["subject"],
            text=row["body"] + "\n\n" + row["resolution"], inquiry_id=row["id"]))
    chunks = [chunk for doc in documents for chunk in chunk_document(doc)]
    vectors = np.array(embedder.encode([c.source.title + "\n" + c.text for c in chunks]))
    results = []
    for query, kind, expected in (
        ("青空物流センターで仕分け設備が止まった原因は何か", "document", "document:seed/docs/incident-demo-001.md"),
        ("配送再開の時刻がまだ決まっていない荷物の遅延報告", "document", "document:seed/docs/delay-demo-001.md"),
        ("配達完了後の受領確認について過去の問い合わせ対応を調べたい", "inquiry", "inquiry:501"),
        ("到着予定が分からないとき、どのように案内するか", "document", "document:seed/docs/faq.md"),
    ):
        case_started = time.monotonic()
        query_vector = np.array(embedder.encode([query], query=True)[0])
        scores = vectors @ query_vector
        candidates = [i for i, c in enumerate(chunks) if c.source.kind == kind]
        top = sorted(candidates, key=lambda i: -scores[i])[:3]
        top_sources = [chunks[i].source.key for i in top]
        results.append({"expected": expected, "passed": expected in top_sources,
            "top_sources": top_sources, "scores": [round(float(scores[i]), 4) for i in top],
            "seconds": round(time.monotonic() - case_started, 3)})
    output = {"embedding_id": EMBEDDING_ID, "device": "cpu", "threads": 4,
        "chunks": len(chunks), "load_including_download_seconds": round(loaded - started, 2),
        "results": results}
    path = Path("artifacts/embedding-verification.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
