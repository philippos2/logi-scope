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


@pytest.mark.parametrize("conclusion,passed", [
    ("配達完了時刻を確認する方法が案内されています。", True),
    ("受領確認が実際に行われたかは確認できません。", True),
    ("受領確認が行われていないとは断定できません。", True),
    ("その時刻をもって受領確認が行われています。", False),
    ("受領確認を実施しました。", False),
    ("受領確認が完了しました。", False),
    ("受領済みです。", False),
])
def test_original_inquiry_does_not_prove_receipt_confirmation(conclusion, passed):
    data = {
        "answer": "配達完了時刻は11時15分（日本時間）です。" + conclusion,
        "sources": [{"id": "inquiry:501"}, {"id": "chunk:example", "origin_id": "inquiry:501"}],
        "steps": [
            {"tool": "search_knowledge", "args": {}, "ok": True},
            {"tool": "get_inquiry", "args": {"inquiry_id": 501}, "ok": True},
        ],
        "unresolved": [],
    }
    assert (not assess("C", data)) is passed


@pytest.mark.parametrize("answer,passed", [
    ("原因はセンサー故障による安全停止です。", True),
    ("センサー故障による安全停止です。復旧予定は確認できません。", True),
    ("原因はセンサー故障ではありません。", False),
    ("センサー故障による安全停止ではないため、原因は不明です。", False),
    ("センサー故障による安全停止は確認できません。", False),
])
def test_delay_cause_rejects_contradictory_answer_with_valid_evidence(answer, passed):
    data = {
        "answer": answer,
        "sources": [{"id": "shipment:SHP-DEMO-001"},
                    {"id": "chunk:incident", "path": "seed/docs/incident-demo-001.md"}],
        "steps": [
            {"tool": "search_shipments", "args": {"customer_id": 101}, "ok": True},
            {"tool": "get_shipment_details", "args": {"shipment_id": "SHP-DEMO-001"}, "ok": True},
            {"tool": "search_knowledge", "args": {"reference_id": "INC-DEMO-001"}, "ok": True},
        ],
        "unresolved": [],
    }
    assert (not assess("B", data)) is passed


@pytest.mark.parametrize("answer,passed", [
    ("配達完了時刻は11:15（日本時間）です。受領確認の実施は確認できません。", True),
    ("11:15に配達完了していますが、受領確認の実施は確認できません。", True),
    ("11:15の配達記録は確認できません。", False),
    ("配達完了時刻は11時15分ではありません。", False),
    ("11:15という検索結果がありますが、配達時刻は不明です。", False),
])
def test_original_inquiry_rejects_denied_delivery_record(answer, passed):
    data = {
        "answer": answer,
        "sources": [{"id": "inquiry:501"}, {"id": "chunk:example", "origin_id": "inquiry:501"}],
        "steps": [
            {"tool": "search_knowledge", "args": {}, "ok": True},
            {"tool": "get_inquiry", "args": {"inquiry_id": 501}, "ok": True},
        ],
        "unresolved": [],
    }
    assert (not assess("C", data)) is passed
