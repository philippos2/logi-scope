"""Equivalent delivered wording must not be mistaken for an agent failure."""

import runpy
from pathlib import Path

import pytest

assess = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/verify_demo.py"))["assess"]


@pytest.mark.parametrize("answer,passed", [
    ("配達完了です。", True),
    ("すでに配達済みです。", True),
    ("配送済みです。", True),
    ("配送中です。", False),
])
def test_single_lookup_accepts_equivalent_delivered_wording(answer, passed):
    data = {
        "answer": answer,
        "sources": [{"id": "shipment:SHP-DEMO-002"}],
        "steps": [{"tool": "search_shipments", "args": {"shipment_id": "SHP-DEMO-002"}, "ok": True}],
        "unresolved": [],
    }
    assert (not assess("A", data)) is passed
