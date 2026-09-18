"""Print provider model IDs without printing API keys."""
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
key = os.getenv('GEMINI_API_KEY', '').strip()
if not key:
    raise SystemExit('GEMINI_API_KEY is missing')
try:
    r = httpx.get('https://generativelanguage.googleapis.com/v1beta/models',
        headers={'x-goog-api-key':key}, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f'Model listing failed: HTTP {r.status_code}')
    for model in r.json().get('models', []):
        if 'generateContent' in model.get('supportedGenerationMethods', []):
            print(model['name'].removeprefix('models/'))
except httpx.HTTPError:
    raise SystemExit('Model listing network error')
