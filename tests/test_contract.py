import json
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.llm import ModelError, interpret
from app.schemas import Scenario, Directive, Interpretation
from app.optimizer import optimize
from app.validator import validate_plan, ReplayError
from pydantic import ValidationError
import pytest

CASES = json.loads((Path(__file__).resolve().parents[1]/'samples/public_cases.json').read_text())['cases']

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'unit-test-placeholder')
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

def test_health(client):
    assert client.get('/health').json() == {'status': 'ok'}

def test_missing_key(client, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY')
    assert client.get('/health').status_code == 503

@pytest.mark.parametrize('case', CASES, ids=lambda c:c['id'])
def test_api_ground_truth(client, case):
    async def fake_interpret(scenario, transport):
        return [Directive.model_validate(d) for d in case['expected_output']['directive_interpretation']]
    with patch('app.main.interpret', fake_interpret):
        r = client.post('/optimize-energy', json=case['input'])
    assert r.status_code == 200
    assert abs(r.json()['total_cost_bdt']-case['expected_output']['total_cost_bdt']) <= .01
    assert len(r.json()['hourly_plan']) == 24

@pytest.mark.parametrize('body', ['{bad', '{}', '{"scenario_id":null}'])
def test_bad_json(client, body):
    assert client.post('/optimize-energy', content=body, headers={'Content-Type':'application/json'}).status_code == 400

def test_duplicate_hour(client):
    data = json.loads(json.dumps(CASES[0]['input']))
    data['hours'][1]['hour'] = 0
    assert client.post('/optimize-energy', json=data).status_code == 400

def test_provider_safe_failure(client):
    async def failed(*args):
        raise ModelError('MODEL_QUOTA_EXCEEDED')
    with patch('app.main.interpret', failed):
        r = client.post('/optimize-energy', json=CASES[0]['input'])
    assert r.status_code == 500
    assert r.json() == {'error':'MODEL_QUOTA_EXCEEDED'}

def test_guardrail_shape():
    with pytest.raises(ValidationError):
        Directive.model_validate({'note_index':0, 'applies':False, 'directive_type':'no_charge_window',
            'structured_adjustment':{'hours':[2]}, 'explanation':'x'})
    with pytest.raises(ValidationError):
        Directive.model_validate({'note_index':0, 'applies':True, 'directive_type':'solar_reduction',
            'structured_adjustment':{'hours':[2,2], 'factor':1.5}, 'explanation':'x'})

def test_replay_catches_tamper():
    c = CASES[0]
    s = Scenario.model_validate(c['input'])
    ds = [Directive.model_validate(d) for d in c['expected_output']['directive_interpretation']]
    r = optimize(s, ds)
    r.hourly_plan[0].grid_kwh += 10
    with pytest.raises(ReplayError):
        validate_plan(s, r)

def test_llm_transport_and_parsing(monkeypatch):
    import asyncio
    monkeypatch.setenv('GEMINI_API_KEY', 'unit-test-placeholder')
    expected = CASES[0]['expected_output']['directive_interpretation']
    def handler(request):
        body = json.loads(request.content)
        assert 'operator_notes' in body['contents'][0]['parts'][0]['text']
        assert request.headers['x-goog-api-key'] == 'unit-test-placeholder'
        return httpx.Response(200, json={'candidates':[{'content':{'parts':[{'text':json.dumps({'directive_interpretation':expected})}]}}]})
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            ds = await interpret(Scenario.model_validate(CASES[0]['input']), c)
            assert ds[0].structured_adjustment.factor == .25
    asyncio.run(check())
