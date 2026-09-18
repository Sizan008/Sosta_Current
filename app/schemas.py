from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

Number = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
HourNumber = Annotated[StrictInt, Field(ge=0, le=23)]
Text = Annotated[str, Field(min_length=1, strict=True)]

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Hour(Model):
    hour: HourNumber
    demand_kwh: Number
    solar_kwh: Number
    tariff_bdt_per_kwh: Number

class Battery(Model):
    capacity_kwh: Number
    initial_energy_kwh: Number
    minimum_energy_kwh: Number
    max_charge_kwh_per_hour: Number
    max_discharge_kwh_per_hour: Number

    @model_validator(mode='after')
    def bounds(self):
        if not self.minimum_energy_kwh <= self.initial_energy_kwh <= self.capacity_kwh:
            raise ValueError('Battery must satisfy minimum <= initial <= capacity')
        return self

class Scenario(Model):
    scenario_id: Text
    operator_notes: Annotated[list[Text], Field(min_length=1, max_length=3)]
    hours: Annotated[list[Hour], Field(min_length=24, max_length=24)]
    battery: Battery

    @model_validator(mode='after')
    def unique_hours(self):
        if sorted(h.hour for h in self.hours) != list(range(24)):
            raise ValueError('hours must contain exactly the integers 0 through 23')
        return self

class Window(Model):
    hours: Annotated[list[HourNumber], Field(min_length=1, max_length=24)]

    @model_validator(mode='after')
    def ordered(self):
        if self.hours != sorted(set(self.hours)):
            raise ValueError('Directive hours must be unique and sorted')
        return self

class Solar(Window):
    factor: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]

class Reserve(Window):
    minimum_energy_kwh: Number

class GridCap(Window):
    max_grid_kwh: Number

class Directive(Model):
    note_index: Annotated[StrictInt, Field(ge=0)]
    applies: StrictBool
    directive_type: Literal['solar_reduction', 'minimum_battery_reserve', 'no_charge_window', 'no_discharge_window', 'max_grid_window', 'no_op']
    structured_adjustment: Solar | Reserve | GridCap | Window | None
    explanation: Text

    @model_validator(mode='after')
    def shape(self):
        expected = {'solar_reduction': Solar, 'minimum_battery_reserve': Reserve,
                    'max_grid_window': GridCap, 'no_charge_window': Window,
                    'no_discharge_window': Window}
        if self.directive_type == 'no_op':
            if self.applies or self.structured_adjustment is not None:
                raise ValueError('no_op requires false and null')
        elif not self.applies or type(self.structured_adjustment) is not expected[self.directive_type]:
            raise ValueError('Directive adjustment does not match type')
        return self

class Interpretation(Model):
    directive_interpretation: list[Directive]

class PlanHour(Model):
    hour: HourNumber
    grid_kwh: Number
    solar_used_kwh: Number
    battery_action: Literal['charge', 'discharge', 'idle']
    battery_kwh: Number
    battery_energy_after_kwh: Number

class Result(Model):
    scenario_id: Text
    directive_interpretation: list[Directive]
    hourly_plan: Annotated[list[PlanHour], Field(min_length=24, max_length=24)]
    total_grid_kwh: Number
    total_cost_bdt: Number
    peak_grid_kwh: Number
    plan_summary: Text
