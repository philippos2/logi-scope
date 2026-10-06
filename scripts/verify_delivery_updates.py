"""Observe a local event update through the read-only agent; public JSON only."""

import json
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    question = {'question': 'SHP-UPDATE-001の配送状態は？'}
    rows = []
    with httpx.Client(timeout=960, trust_env=False) as http:
        for phase, labels in [('before', ('配送中', '輸送中')), ('after', ('配達完了', '配達済み'))]:
            if phase == 'after':
                payload = {'event_key': str(uuid4()), 'status': 'delivered', 'occurred_at': '2026-10-04T09:00:00+09:00'}
                created = http.post('http://updates:8001/shipments/SHP-UPDATE-001/events', json=payload)
                created.raise_for_status()
                replay = http.post('http://updates:8001/shipments/SHP-UPDATE-001/events', json=payload)
                replay.raise_for_status()
                assert created.status_code == 201 and replay.status_code == 200
                assert replay.json()['replayed'] and created.json()['event_id'] == replay.json()['event_id']
                rows.append({'phase': 'update_and_replay', 'passed': True, 'created': created.json(), 'replay': replay.json()})
            response = http.post('http://localhost:8000/agent', json=question)
            response.raise_for_status()
            data = response.json()
            passed = (any(label in data['answer'] for label in labels)
                and any(s['id'] == 'shipment:SHP-UPDATE-001' for s in data['sources'])
                and bool(data['steps']) and not data['unresolved'])
            rows.append({'phase': phase, 'passed': passed, 'response': data})
            print(f'{phase}: {"passed" if passed else "failed"}', flush=True)
    path = Path('artifacts/delivery-update-verification.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    print(f'Passed {sum(r["passed"] for r in rows)} of {len(rows)} cases.')
    raise SystemExit(0 if all(r['passed'] for r in rows) else 1)


if __name__ == '__main__':
    main()
