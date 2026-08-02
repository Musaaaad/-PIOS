"""Run after PostgreSQL migration/seed and MinIO are reachable."""
from __future__ import annotations
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

ready = client.get('/ready')
ready.raise_for_status()
assert ready.json()['database'] == 'reachable'

campaign = client.post('/api/v1/evidence-campaigns', json={
    'name': 'Sprint 2 Runtime Smoke',
    'period_start': '2026-07-01',
    'period_end': '2026-09-30',
}).json()
client.post(f"/api/v1/evidence-campaigns/{campaign['id']}/lifecycle", json={'to_status': 'Open'}).raise_for_status()
request = client.post(f"/api/v1/evidence-campaigns/{campaign['id']}/requests", json={'requests': [{
    'me_id': 'MM.31.1', 'tool_code': 'ECF-D', 'eoc': ['D'],
}]}).json()[0]
client.post(f"/api/v1/evidence-requests/{request['id']}/start").raise_for_status()
item = client.post(f"/api/v1/evidence-requests/{request['id']}/items", json={
    'source_type': 'Document', 'title': 'Runtime smoke evidence',
    'period_start': '2026-07-01', 'period_end': '2026-07-31',
    'scope_sites': ['TGH'], 'scope_shifts': ['All'],
}).json()
pdf = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
upload = client.post(f"/api/v1/evidence-items/{item['id']}/files", files={
    'file': ('runtime-smoke.pdf', pdf, 'application/pdf')
})
upload.raise_for_status()
client.post(f"/api/v1/evidence-items/{item['id']}/submit").raise_for_status()
client.post(f"/api/v1/evidence-items/{item['id']}/review/start").raise_for_status()
codes = ['AUTHENTICITY','CURRENCY','SCOPE','REPRESENTATIVENESS','TRACEABILITY','CONSISTENCY','EOC_MATCH']
review = client.post(f"/api/v1/evidence-items/{item['id']}/reviews", json={
    'verdict': 'Accepted', 'reason_code': 'RUNTIME_SMOKE',
    'tests': [{'test_code': code, 'result': 'Pass'} for code in codes],
})
review.raise_for_status()
result = {
    'ready': ready.json(), 'campaign_id': campaign['id'], 'request_id': request['id'],
    'item_id': item['id'], 'file_id': upload.json()['id'], 'sha256': upload.json()['sha256'],
    'storage_uri': upload.json()['storage_uri'], 'review': review.json(),
}
out = ROOT / 'reports/sprint2_runtime_smoke.json'
out.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(out)
