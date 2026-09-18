"""Run from repo root: python -m tests.check_model. Never prints credentials."""
import asyncio
import json
from pathlib import Path
import httpx
from dotenv import load_dotenv
from app.schemas import Scenario
from app.llm import interpret, ModelError

async def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / '.env')
    scenario = Scenario.model_validate(json.loads((root/'samples/public_cases.json').read_text())['cases'][0]['input'])
    async with httpx.AsyncClient(timeout=23) as client:
        try:
            result = await interpret(scenario, client)
            print('MODEL OK')
            for d in result:
                print(d.model_dump_json())
        except ModelError as exc:
            print('MODEL CHECK FAILED:', exc.code)
            print('Check key, model name, project permissions, quota and network. No secret values are printed.')
            raise SystemExit(1)

if __name__ == '__main__':
    asyncio.run(main())
