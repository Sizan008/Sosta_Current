"""Offline solver/replay: python -m tests.run_samples
Live full pipeline: python -m tests.run_samples --url http://127.0.0.1:8000
"""
import argparse
import json
import time
from pathlib import Path
import httpx
from app.schemas import Scenario, Directive, Result
from app.optimizer import optimize
from app.validator import validate_plan

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url')
    args = parser.parse_args()
    cases = json.loads((Path(__file__).resolve().parents[1]/'samples/public_cases.json').read_text())['cases']
    failed = 0
    timings = []
    with httpx.Client(timeout=30) as client:
        for case in cases:
            start = time.perf_counter()
            try:
                scenario = Scenario.model_validate(case['input'])
                expected = [Directive.model_validate(d) for d in case['expected_output']['directive_interpretation']]
                if args.url:
                    response = client.post(args.url.rstrip('/')+'/optimize-energy', json=case['input'])
                    if response.status_code != 200:
                        raise ValueError(f'HTTP {response.status_code}: {response.text[:160]}')
                    result = Result.model_validate(response.json())
                else:
                    result = optimize(scenario, expected)
                validate_plan(scenario, result)
                actual_semantics = [d.model_dump(exclude={'explanation'}) for d in result.directive_interpretation]
                wanted_semantics = [d.model_dump(exclude={'explanation'}) for d in expected]
                if actual_semantics != wanted_semantics:
                    raise ValueError('Interpretation differs from ground truth')
                # Replay against organizer/public truth, not only model-reported directives.
                validate_plan(scenario, result.model_copy(update={'directive_interpretation': expected}))
                if abs(result.total_cost_bdt-case['expected_output']['total_cost_bdt']) > 0.01:
                    raise ValueError('Cost differs from public optimal reference')
                elapsed = time.perf_counter()-start
                timings.append(elapsed)
                print(case['id'], 'PASS', f'cost={result.total_cost_bdt:.2f}', f'{elapsed:.2f}s')
            except Exception as exc:
                failed += 1
                print(case['id'], 'FAIL', str(exc))
    print(f'{len(cases)-failed}/{len(cases)} passed. Mode:', 'LIVE LLM + API' if args.url else 'OFFLINE optimizer with reference directives (does not test LLM)')
    raise SystemExit(1 if failed else 0)

if __name__ == '__main__':
    main()
