import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.guardrails import UnsafeSQL, validate
from app.main import app

SCHEMA = json.loads(Path('schema.json').read_text())

@pytest.mark.parametrize('sql', [
    'DROP TABLE customers', 'SELECT 1; DELETE FROM orders',
    'SELECT missing FROM customers', 'SELECT * FROM secrets',
    'SELECT * FROM other.customers', "SELECT load_extension('x')",
    'SELECT * FROM customers LIMIT -1', 'SELECT * INTO backup FROM customers',
    'WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x',
    'WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT 1 FROM x) SELECT * FROM x',
])
def test_rejects(sql):
    with pytest.raises(UnsafeSQL):
        validate(sql, SCHEMA)

def test_cte_and_limit():
    sql = validate('WITH x AS (SELECT region FROM customers) SELECT region FROM x LIMIT 9999', SCHEMA)
    assert 'LIMIT 200' in sql

def test_api(tmp_path, monkeypatch):
    monkeypatch.setenv('API_KEY', 'test-key')
    monkeypatch.setenv('SQLITE_PATH', str(tmp_path / 'warehouse.db'))
    monkeypatch.setenv('LLM_PROVIDER', 'demo')
    monkeypatch.setenv('EMBEDDING_BACKEND', 'hash')
    monkeypatch.setenv('VECTOR_BACKEND', 'faiss')
    monkeypatch.setenv('WAREHOUSE', 'sqlite')
    with TestClient(app) as client:
        assert client.post('/query', json={'question':'total revenue'}).status_code == 401
        response = client.post('/query', headers={'X-API-Key':'test-key'}, json={'question':'total revenue','execute':True})
        assert response.status_code == 200, response.text
        assert response.json()['result']['rows'] == [[445.0]]
        preview = client.post('/query', headers={'X-API-Key':'test-key'}, json={'question':'revenue by region'})
        assert preview.json()['executed'] is False
