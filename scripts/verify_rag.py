"""Real E5 + read-only PostgreSQL retrieval smoke checks, no LLM."""

import asyncio
import json
from pathlib import Path
import time

from logi_scope.config import Settings
from logi_scope.db.session import create_reader_engine
from logi_scope.rag.embeddings import EMBEDDING_ID, E5Embedder
from logi_scope.tools import BusinessTools


async def main():
    embedder = E5Embedder()
    engine = create_reader_engine(Settings())
    results = []
    try:
        tools = BusinessTools(engine, timeout=60, embedder=embedder)
        for arguments, expected in (
            ({"query": "仕分け設備が止まった原因は何か", "kind": "document", "reference_id": "INC-DEMO-001"}, "document:seed/docs/incident-demo-001.md"),
            ({"query": "配送再開時刻が未確定の荷物の遅延報告", "kind": "document"}, "document:seed/docs/delay-demo-001.md"),
            ({"query": "配達完了後の受領確認について過去の問い合わせ対応を調べたい", "kind": "inquiry"}, "inquiry:501"),
            ({"query": "到着予定が分からないとき、どのように案内するか", "kind": "document"}, "document:seed/docs/faq.md"),
        ):
            started = time.monotonic()
            result = await tools.execute("search_knowledge", arguments)
            top = [r["source_key"] for r in result.records[:3]]
            original_ok = True
            if expected.startswith("inquiry:"):
                matching = next((r for r in result.records[:3] if r["source_key"] == expected), None)
                if matching:
                    original = await tools.execute("get_inquiry", {"inquiry_id": matching["inquiry_id"]})
                    original_ok = bool(original.records) and original.sources[0].id == expected
                else:
                    original_ok = False
            results.append({"expected": expected, "passed": expected in top and original_ok,
                "top_sources": top, "original_retrieved": original_ok if expected.startswith("inquiry:") else None,
                "seconds": round(time.monotonic() - started, 3)})
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
    output = {"embedding_id": EMBEDDING_ID, "results": results}
    path = Path("artifacts/rag-verification.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
