"""Explicit scenario accounting. Missing components never become free compute."""
from __future__ import annotations
import math

def _num(v,name,positive=False):
    if type(v) not in (int,float) or not math.isfinite(v) or (v<=0 if positive else v<0): raise ValueError('invalid '+name)
    return float(v)

def estimate_cost(summary,scenario,energy=None):
    if not isinstance(summary,dict) or not isinstance(scenario,dict): raise ValueError('objects required')
    duration=_num(summary.get('duration_s'),'duration_s',True);accepted=summary.get('accepted_tasks')
    if type(accepted) is not int or accepted<0: raise ValueError('invalid accepted_tasks')
    numeric=['capex_usd','residual_usd','life_hours','utilization','financing_usd_per_hour','hosting_usd_per_hour','operations_usd_per_hour','maintenance_usd_per_hour','network_usd_per_hour','electricity_usd_per_kwh','pue','intervention_seconds','intervention_usd_per_hour','average_it_power_w']
    for key in numeric:
        if scenario.get(key) is not None: _num(scenario[key],key,key in ('life_hours','utilization','pue'))
    if scenario.get('utilization') is not None and scenario['utilization']>1: raise ValueError('utilization must be <=1')
    if scenario.get('pue') is not None and scenario['pue']<1: raise ValueError('PUE must be >=1')
    if scenario.get('capex_usd') is not None and scenario.get('residual_usd') is not None and scenario['residual_usd']>scenario['capex_usd']: raise ValueError('residual exceeds capex')
    hours=duration/3600;components={};limits=[]
    amort_keys=['capex_usd','residual_usd','life_hours','utilization']
    components['amortization_usd']=((scenario['capex_usd']-scenario['residual_usd'])/(scenario['life_hours']*scenario['utilization'])*hours) if all(scenario.get(k) is not None for k in amort_keys) else None
    for name in ('financing','hosting','operations','maintenance','network'):
        rate=scenario.get(name+'_usd_per_hour');components[name+'_usd']=rate*hours if rate is not None else None
    seconds=scenario.get('intervention_seconds');rate=scenario.get('intervention_usd_per_hour')
    components['intervention_usd']=seconds*rate/3600 if seconds is not None and rate is not None else None
    price=scenario.get('electricity_usd_per_kwh');pue=scenario.get('pue');board_subtotal=None;electricity=None;basis='unknown'
    if energy is not None and not isinstance(energy,dict): raise ValueError('energy must be object')
    if energy and energy.get('joules') is not None:
        j=_num(energy['joules'],'joules');scope=energy.get('scope')
        if price is not None:
            if scope=='facility': electricity=j/3600000*price;basis='facility energy observation times scenario tariff'
            elif scope=='it_equipment' and pue is not None: electricity=j/3600000*pue*price;basis='IT energy observation times scenario PUE and tariff'
            else: board_subtotal=j/3600000*price;limits.append('Partial device energy has no complete IT/facility boundary; PUE is not applied to board power.')
    if electricity is None and scenario.get('average_it_power_w') is not None and price is not None and pue is not None:
        electricity=scenario['average_it_power_w']*duration/3600000*pue*price;basis='Explicit modeled whole-IT power, PUE and tariff; not measured facility consumption'
    components['electricity_usd']=electricity
    unknown=[k for k,v in components.items() if v is None];subtotal=sum(v for v in components.values() if v is not None);total=subtotal if not unknown else None
    return {'schema':'ocl.cost/1','mode':'scenario','scenario':dict(scenario),'duration_s':duration,'accepted_tasks':accepted,'components':components,'known_subtotal_usd':subtotal,'subtotal_usd':subtotal,'unknown_components':unknown,'complete':not unknown,'total_usd':total,'modeled_cost_per_accepted_usd':total/accepted if total is not None and accepted else None,'measured_scope_energy_cost_usd':board_subtotal,'electricity_basis':basis,'limitations':limits+['Scenario values are assumptions, not observed expenditures.','Costs include all elapsed time and failed attempts; no per-task timing subtraction.']}
