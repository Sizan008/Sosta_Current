import math
from .guardrails import validate_directives

class ReplayError(Exception):
    pass

def validate_plan(scenario, result):
    """Independent replay: deliberately does not reuse optimizer limit arrays."""
    def require(ok, message):
        if not ok:
            raise ReplayError(message)
    tol = 0.005
    validate_directives(scenario, result.directive_interpretation)
    require(result.scenario_id == scenario.scenario_id, 'Scenario mismatch')
    require([p.hour for p in result.hourly_plan] == list(range(24)), 'Invalid hours')
    source = {h.hour: h for h in scenario.hours}
    b = scenario.battery
    energy = b.initial_energy_kwh
    for p in result.hourly_plan:
        h = source[p.hour]
        solar = h.solar_kwh
        reserve = b.minimum_energy_kwh
        cap = math.inf
        no_charge = no_discharge = False
        for d in result.directive_interpretation:
            a = d.structured_adjustment
            if a is None or p.hour not in a.hours:
                continue
            if d.directive_type == 'solar_reduction': solar *= a.factor
            elif d.directive_type == 'minimum_battery_reserve': reserve = max(reserve, a.minimum_energy_kwh)
            elif d.directive_type == 'max_grid_window': cap = min(cap, a.max_grid_kwh)
            elif d.directive_type == 'no_charge_window': no_charge = True
            elif d.directive_type == 'no_discharge_window': no_discharge = True
        require(all(math.isfinite(v) and v >= 0 for v in
            [p.grid_kwh, p.solar_used_kwh, p.battery_kwh, p.battery_energy_after_kwh]), 'Invalid number')
        ch = p.battery_kwh if p.battery_action == 'charge' else 0
        dis = p.battery_kwh if p.battery_action == 'discharge' else 0
        require(p.battery_action != 'idle' or p.battery_kwh == 0, 'Idle mismatch')
        require(ch <= b.max_charge_kwh_per_hour + tol and dis <= b.max_discharge_kwh_per_hour + tol, 'Rate exceeded')
        require(not no_charge or ch <= tol, 'Charging prohibited')
        require(not no_discharge or dis <= tol, 'Discharging prohibited')
        energy += ch - dis
        require(abs(energy - p.battery_energy_after_kwh) <= tol, 'State transition')
        require(reserve - tol <= energy <= b.capacity_kwh + tol, 'Battery bounds')
        require(p.solar_used_kwh <= solar + tol and p.grid_kwh <= cap + tol, 'Source bounds')
        require(abs(p.grid_kwh + p.solar_used_kwh + dis - h.demand_kwh - ch) <= tol, 'Energy balance')
    require(abs(energy - b.initial_energy_kwh) <= tol, 'Final energy')
    require(abs(result.total_grid_kwh - sum(p.grid_kwh for p in result.hourly_plan)) <= tol, 'Grid total')
    require(abs(result.total_cost_bdt - sum(p.grid_kwh * source[p.hour].tariff_bdt_per_kwh for p in result.hourly_plan)) <= tol, 'Cost total')
    require(abs(result.peak_grid_kwh - max(p.grid_kwh for p in result.hourly_plan)) <= tol, 'Peak total')
    return result
