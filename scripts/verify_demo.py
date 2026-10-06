"""Real HTTP/LLM/DB/RAG checks; semantic acceptance also needs human review."""

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx

CASES = {
    "A": "SHP-DEMO-002の配送状態は？",
    "B": "デモ青空商店の荷物が遅延している原因は？",
    "C": "配達完了後の受領確認について、過去の問い合わせでの対応を調べて",
    "D": "SHP-NOT-FOUNDの配送状態は？",
    "E": "デモ双葉商会の荷物を調べて",
}


# Deliberately narrow regressions for known false positives, not semantic validation.
CAUSE_CONTRADICTION = re.compile(
    r"(?:センサー(?:の)?故障|安全停止)[^。！？\n、,]{0,20}"
    r"(?:ではありません|ではない|でない|していません|していない|確認できません|確認できない)"
    r"|(?:原因|理由)[^。！？\n、,]{0,15}(?:不明|特定できません|確認できません)"
)
DELIVERY_CONTRADICTION = re.compile(
    r"(?:11[:：]15|11時15分)(?:の配達(?:完了)?(?:時刻|記録))?(?:は|が|という時刻は)?"
    r"(?:ではありません|ではない|でない|確認できません|確認できない|記録がありません|記録はありません)"
    r"|配達(?:完了)?(?:時刻|記録)[^。！？\n、,]{0,15}"
    r"(?:不明|確認できません|確認できない|記録がありません|記録はありません)"
)
MANUAL_REVIEW = {
    "A": "正本と配送状態・時刻が一致し、矛盾する説明がないこと。",
    "B": "対象荷物の遅延原因がセンサー故障による安全停止と一致し、復旧・到着予定を捏造していないこと。",
    "C": "問い合わせ501の配達完了時刻11:15（日本時間）と確認方法を正しく反映し、受領確認の実施を断定していないこと。",
    "D": "該当荷物が確認できないと説明し、存在しない事実を補っていないこと。",
    "E": "両顧客候補を示し、追加情報なしに一方を選んでいないこと。",
}


def assess(case, data):
    answer = data.get("answer", "")
    sources = {s["id"]: s for s in data.get("sources", [])}
    steps = data.get("steps", [])
    codes = {p["code"] for p in data.get("unresolved", [])}
    success = [s for s in steps if s["ok"]]
    failures = []
    def check(condition, reason):
        if not condition:
            failures.append(reason)
    check(set(data) == {"answer", "sources", "steps", "unresolved"}, "応答契約")
    check(bool(success), "検索操作の履歴")
    if case == "A":
        check("shipment:SHP-DEMO-002" in sources, "荷物の根拠")
        check(any(word in answer for word in ("配達完了", "配送完了", "配達済み", "配送済み")), "配達完了の回答")
        check(not codes, "未解決事項が空")
        if "02:15" in answer or "2時15分" in answer:
            check("UTC" in answer or "協定世界時" in answer, "UTC時刻のタイムゾーン表記")
    elif case == "B":
        check(len(success) >= 3, "複数段階の操作")
        check(any(s["tool"] == "search_shipments" and s["args"].get("customer_id") == 101 for s in success), "顧客IDの引き継ぎ")
        check(any(s["tool"] == "get_shipment_details" and s["args"].get("shipment_id") == "SHP-DEMO-001" for s in success), "荷物IDと配送イベント")
        check(any(s["tool"] == "search_knowledge" and (s["args"].get("reference_id") in {"INC-DEMO-001", "SHP-DEMO-001"} or "INC-DEMO-001" in s["args"].get("query", "")) for s in success), "業務IDを使った文書検索")
        check("shipment:SHP-DEMO-001" in sources, "業務データの根拠")
        check(any(s.get("path") == "seed/docs/incident-demo-001.md" for s in sources.values()), "原因を記載した障害報告の根拠")
        check("センサー" in answer and ("故障" in answer or "安全停止" in answer), "正本に合う遅延原因")
        check(not CAUSE_CONTRADICTION.search(answer), "正本の遅延原因を否定・不明としない")
        check(not any(p in answer for p in ("明日到着します", "復旧しました")), "未確定事項を断定しない")
    elif case == "C":
        names = [s["tool"] for s in success]
        check("search_knowledge" in names and "get_inquiry" in names and names.index("search_knowledge") < names.index("get_inquiry"), "検索から正本取得への依存")
        check(any(s["tool"] == "get_inquiry" and s["args"].get("inquiry_id") == 501 for s in success), "問い合わせ501の正本取得")
        check("inquiry:501" in sources and any(s.get("origin_id") == "inquiry:501" for s in sources.values()), "チャンクと正本の根拠")
        check("11:15" in answer or "11時15分" in answer, "正本の配達時刻を回答へ反映")
        check(not DELIVERY_CONTRADICTION.search(answer), "正本の配達記録・時刻を否定しない")
        # Known unsupported claims for inquiry 501, not a general fact-checker.
        check(not re.search(
            r"受領(?:確認)?(?:は|が|を)[^。！？\n]{0,30}"
            r"(?:行われています|行われました|完了しています|完了しました|実施されています|実施されました|実施しました)",
            answer) and "受領済みです" not in answer,
            "確認方法の案内から受領確認の実施を断定しない")
    elif case == "D":
        check(any(s["tool"] in {"search_shipments", "get_shipment_details"} and s["args"].get("shipment_id") == "SHP-NOT-FOUND" for s in success), "不存在IDの検索")
        check("not_found" in codes, "不存在の未解決コード")
        check("確認でき" in answer or "見つか" in answer or "存在しない" in answer, "確認不能の回答")
        check(not any(s.get("record_id") == "SHP-NOT-FOUND" for s in sources.values()), "架空の荷物根拠を作らない")
    elif case == "E":
        check({"customer:201", "customer:202"}.issubset(sources), "両候補の根拠")
        check("ambiguous_target" in codes, "曖昧性の未解決コード")
        check("複数" in answer, "複数候補の提示")
        check(not any(s["tool"] == "search_shipments" for s in success), "候補を勝手に選ばない")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "logiscope-qwen30-probe"))
    parser.add_argument("--repeat", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--output", default="artifacts/demo-verification.json")
    args = parser.parse_args()
    results = []
    with httpx.Client(timeout=960, trust_env=False) as http:
        for repetition in range(args.repeat):
            for case, question in CASES.items():
                started = time.monotonic()
                row = {"case": case, "question": question, "repetition": repetition + 1,
                       "manual_review_required": True, "manual_review_check": MANUAL_REVIEW[case]}
                try:
                    response = http.post(args.base_url.rstrip("/") + "/agent", json={"question": question})
                    row["http_status"] = response.status_code
                    if response.status_code == 200:
                        data = response.json()
                        row.update(response=data, failures=assess(case, data))
                    else:
                        row["failures"] = ["HTTPエラー"]
                    row["passed"] = not row["failures"]
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
                    row.update(passed=False, error_type=type(error).__name__)
                row["seconds"] = round(time.monotonic() - started, 2)
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": args.model, "results": results}, ensure_ascii=False, indent=2) + "\n")
    print(f"Automated checks passed {sum(r['passed'] for r in results)} of {len(results)} cases; semantic acceptance requires human review.")
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
