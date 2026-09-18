import os
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .schemas import Scenario, Result
from .llm import interpret, ModelError
from .optimizer import optimize, OptimizationError
from .validator import validate_plan

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=httpx.Timeout(23.0, connect=5.0),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=10)) as client:
        app.state.client = client
        yield

app = FastAPI(title='GridWise Energy Optimizer', version='1.0.0', lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Do not echo user input, raw exceptions, prompts, or secret values.
    return JSONResponse(status_code=400, content={'error': 'INVALID_REQUEST',
        'details': [{'field': '.'.join(map(str, e['loc'])), 'type': e['type']} for e in exc.errors()]})

@app.exception_handler(Exception)
async def internal_error(request, exc):
    return JSONResponse(status_code=500, content={'error': 'INTERNAL_ERROR'})

@app.get('/health')
def health():
    # Local readiness; does not consume model quota for every health probe.
    if not os.getenv('GEMINI_API_KEY', '').strip():
        return JSONResponse(status_code=503, content={'status': 'not_ready'})
    return {'status': 'ok'}

@app.post('/optimize-energy', response_model=Result)
async def optimize_energy(scenario: Scenario, request: Request):
    try:
        directives = await interpret(scenario, request.app.state.client)
        result = await run_in_threadpool(optimize, scenario, directives)
        return validate_plan(scenario, result)
    except ModelError as exc:
        return JSONResponse(status_code=500, content={'error': exc.code})
    except OptimizationError:
        return JSONResponse(status_code=422, content={'error': 'NO_FEASIBLE_OPTIMAL_PLAN'})
    except Exception:
        # Catch within the route to prevent ASGI exception traceback logging.
        return JSONResponse(status_code=500, content={'error': 'PLAN_VALIDATION_FAILED'})
