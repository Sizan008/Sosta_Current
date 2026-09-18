from .schemas import Scenario, Directive

def validate_directives(scenario: Scenario, directives: list[Directive]):
    if [d.note_index for d in directives] != list(range(len(scenario.operator_notes))):
        raise ValueError('One ordered interpretation is required for each note')
    for d in directives:
        if d.directive_type == 'minimum_battery_reserve':
            if d.structured_adjustment.minimum_energy_kwh > scenario.battery.capacity_kwh:
                raise ValueError('Reserve exceeds battery capacity')
    return directives

def effective_limits(scenario, directives):
    hours = sorted(scenario.hours, key=lambda h: h.hour)
    b = scenario.battery
    solar = [h.solar_kwh for h in hours]
    reserve = [b.minimum_energy_kwh] * 24
    charge = [b.max_charge_kwh_per_hour] * 24
    discharge = [b.max_discharge_kwh_per_hour] * 24
    grid = [None] * 24
    for d in directives:
        if d.directive_type == 'no_op':
            continue
        a = d.structured_adjustment
        for h in a.hours:
            if d.directive_type == 'solar_reduction':
                # Overlap is unspecified by the brief; use multiplicative reductions.
                solar[h] *= a.factor
            elif d.directive_type == 'minimum_battery_reserve':
                reserve[h] = max(reserve[h], a.minimum_energy_kwh)
            elif d.directive_type == 'no_charge_window':
                charge[h] = 0.0
            elif d.directive_type == 'no_discharge_window':
                discharge[h] = 0.0
            elif d.directive_type == 'max_grid_window':
                grid[h] = a.max_grid_kwh if grid[h] is None else min(grid[h], a.max_grid_kwh)
    return hours, solar, reserve, charge, discharge, grid
