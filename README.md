# GridWise: LLM-assisted campus energy scheduling

FastAPI service for BUP CSE Fest preliminary. The language model converts operator
notes into supported directives; strict Pydantic models and guardrails validate
those directives; SciPy HiGHS minimizes grid cost; an independent replay validates
energy balance, source limits, battery transitions, directives and totals.

## Local quickstart (Python 3.12)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env locally; insert your Gemini API key. Never commit this file.
python -m tests.check_model
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Configuration:
- GEMINI_API_KEY: required, Google AI Studio API key. Set in .env locally or the hosting environment.
- GEMINI_MODEL: defaults to gemini-2.5-flash; use an available generateContent model.
- PORT: Docker/Render port, defaults to 8000 in Docker.

The model directly generates directive_interpretation consumed by the optimizer.
There is no phrase-matching interpreter or hidden no-LLM production fallback.
One batched model call interprets all notes, with one bounded retry. Invalid
model output never silently becomes no_op. Total model deadline is 20 seconds;
solver time limit is 3 seconds. Health checks test local configuration, not live
provider quota. Run check_model to verify live provider access separately.

## API and tests

```bash
curl http://localhost:8000/health
python -m tests.run_samples
python -m tests.run_samples --url http://localhost:8000
python -c 'import json; print(json.dumps(json.load(open("samples/public_cases.json"))["cases"][0]["input"]))' > /tmp/gridwise-request.json
curl -X POST http://localhost:8000/optimize-energy -H 'Content-Type: application/json' --data-binary @/tmp/gridwise-request.json
```

Offline samples use reference directives and verify 10 optimal costs and replay
validity; they do NOT test the LLM. Live samples verify the actual LLM/API,
compare structured interpretation to public ground truth, replay using that
truth and compare optimal costs. SAMPLE-01 reference cost is 38365 BDT.
The complete sample request/response examples are in samples/public_cases.json.
For additional contract/error tests: `pip install pytest` then `python -m pytest -q`.

Endpoints: GET /health and POST /optimize-energy. Swagger: /docs.
Malformed/structurally invalid input: 400. Infeasible optimization: 422.
Provider/model errors: controlled 500 with a safe code. Examples:
MODEL_AUTH_FAILED/MODEL_ACCESS_DENIED (key/project permissions),
MODEL_NOT_FOUND (model identifier), MODEL_QUOTA_EXCEEDED (quota),
MODEL_NETWORK_ERROR, MODEL_TIMEOUT, MODEL_OUTPUT_INVALID.
Health returns 503 when no key is configured. No secret values or raw provider
responses are returned or logged by application code.

## Mathematics

For each hour, use grid g>=0, solar s>=0, signed battery flow q and battery state E.
Positive q charges, negative q discharges; a single signed flow avoids simultaneous
actions. Minimize sum(g[h]*tariff[h]) subject to:
- g+s-q=demand
- E[h]=E[h-1]+q[h], initial predecessor = initial_energy_kwh
- -max_discharge <= q <= max_charge (window directives tighten these bounds)
- 0 <= s <= adjusted solar, 0 <= g <= applicable grid cap
- active reserve <= E <= capacity
- E[23] = initial_energy_kwh
The model assumes the specification's lossless battery. Excess solar may be
curtailed; grid export is not allowed. The optimizer receives validated numeric
constraints only. Response totals are computed from returned plan values.

## Render deployment

Create a Render Web Service from the GitHub repo. Choose Python runtime.
Root directory: blank if app/ and requirements.txt are at repo root.
Build: `pip install -r requirements.txt`
Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
Health path: `/health`
Environment: GEMINI_API_KEY (secret), GEMINI_MODEL=gemini-2.5-flash.
Use Python 3.12 (the repo includes .python-version).
Test the public /health and run samples with --url against the public base URL.
Render free-service cold starts can exceed the judge timeout; keep the submitted
service available throughout evaluation and choose hosting capacity accordingly.

## Docker fallback

Build and publish from the project root:
```bash
docker build -t sizan008/gridwise-api:v1 .
docker run --rm --env-file .env -p 8001:8000 sizan008/gridwise-api:v1
# In another terminal:
curl http://localhost:8001/health
python -m tests.run_samples --url http://localhost:8001
# After tests pass:
docker push sizan008/gridwise-api:v1
```
Organizer fallback (credentials provisioned separately, never in the public README):
```bash
docker pull sizan008/gridwise-api:v1
docker run --rm --env-file .env -p 8000:8000 sizan008/gridwise-api:v1
```
Image name above is the intended submission reference; it is available only
AFTER the team builds and pushes successfully. This source bundle is not an
already-published image. Docker copies only source/samples/tests, never .env.
The service binds 0.0.0.0 and runs as a non-root user.

## Limitations and interpretation conventions

No hosted API/provider performance claim is made before live tests pass.
Model semantics can still be wrong despite schema validation; hidden paraphrases
must be tested. No persistent database, model training or external real-world
campus data is required. Each request is independent.
Overlapping solar reductions are not specified in the brief: this implementation
multiplies factors. Overlapping reserves use the maximum; grid caps the minimum.
Overnight windows are interpreted as wrapping through midnight, then sorted.
Organizer clarification should override these two unspecified conventions.
Model unavailability returns a controlled failure, not fabricated interpretations.
Core tested package versions are pinned in requirements.txt. Uvicorn retains a
compatible range; freeze the final deployed environment for full transitive reproducibility.

## Submission checklist

- Submit the public API base URL and keep it reachable.
- Repo created after question reveal; private during event, public after deadline.
- Submit a tested pullable Docker image tag/digest and these run commands.
- Document model/provider, configuration names and dependencies.
- Submit an accessible <=3 minute architecture/run-test video (tie-break).
- Verify no .env, keys, local credentials or .venv are committed.

## Credits

Google Gemini API: language interpretation. FastAPI/Starlette/Uvicorn: HTTP API.
Pydantic: structured validation. SciPy/HiGHS and NumPy: optimization.
HTTPX: provider transport. python-dotenv: local configuration.
Public synthetic samples: BUP challenge organizers.
Implementation assistance: ChatGPT/Codex. Team members must review and understand
all core logic and follow the event's attribution and participation rules.



## Verification of this source bundle

13/13 offline public samples matched reference optimal costs and passed replay.
20 local contract/validation tests passed, using mocked model responses where
appropriate. A live provider check did not succeed: generation returned model
not-found/access-denied responses although model listing succeeded. Actual Gemini
access, semantic accuracy, latency, Docker build/run and Render deployment must
still be verified in the team environment. To inspect available IDs, run
`python -m tests.list_models`, then set GEMINI_MODEL in .env and rerun
`python -m tests.check_model`. Model listing alone does not prove generation access.
