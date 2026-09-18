import numpy as np
from scipy.optimize import linprog
from .guardrails import effective_limits
from .schemas import Result, PlanHour

class OptimizationError(Exception):
    pass

def optimize(scenario, directives):
    hours, solar, reserve, charge, discharge, caps = effective_limits(scenario, directives)
    b = scenario.battery
    # 96 variables: grid[24], solar_used[24], signed_charge[24], energy_after[24].
    # A signed battery flow prevents simultaneous charging and discharging.
    c = np.zeros(96)
    c[:24] = [h.tariff_bdt_per_kwh for h in hours]
    bounds = ([(0, caps[h]) for h in range(24)] + [(0, solar[h]) for h in range(24)]
              + [(-discharge[h], charge[h]) for h in range(24)]
              + [(reserve[h], b.capacity_kwh) for h in range(24)])
    eq = np.zeros((49, 96))
    rhs = np.zeros(49)
    for h in range(24):
        eq[h, h] = 1
        eq[h, 24+h] = 1
        eq[h, 48+h] = -1
        rhs[h] = hours[h].demand_kwh
        eq[24+h, 72+h] = 1
        eq[24+h, 48+h] = -1
        if h:
            eq[24+h, 72+h-1] = -1
        else:
            rhs[24+h] = b.initial_energy_kwh
    eq[48, 95] = 1
    rhs[48] = b.initial_energy_kwh
    res = linprog(c, A_eq=eq, b_eq=rhs, bounds=bounds, method='highs',
                  options={'time_limit': 3.0})
    if not res.success:
        raise OptimizationError('No optimal feasible schedule found')
    plan = []
    for h in range(24):
        flow = float(res.x[48+h])
        # Preserve meaningful small flows; clip only solver dust at 1e-9.
        if abs(flow) < 1e-9:
            flow = 0.0
        plan.append(PlanHour(hour=h, grid_kwh=max(0.0, float(res.x[h])),
            solar_used_kwh=max(0.0, float(res.x[24+h])),
            battery_action='charge' if flow > 0 else 'discharge' if flow < 0 else 'idle',
            battery_kwh=abs(flow), battery_energy_after_kwh=max(0.0, float(res.x[72+h]))))
    return Result(scenario_id=scenario.scenario_id, directive_interpretation=directives,
        hourly_plan=plan, total_grid_kwh=sum(p.grid_kwh for p in plan),
        total_cost_bdt=sum(p.grid_kwh * hours[p.hour].tariff_bdt_per_kwh for p in plan),
        peak_grid_kwh=max(p.grid_kwh for p in plan),
        plan_summary='Applies the operator directives, minimizes grid electricity cost using linear programming, and restores the initial battery energy at the end of the day.')
