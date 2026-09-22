"""Offline price/throughput arithmetic. No provisioning or benchmark execution."""
from __future__ import annotations
import math
from numbers import Real

def _number(value: Real, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f'{name} must be a finite number')
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        raise ValueError(f'{name} must be finite and ' + ('positive' if positive else 'nonnegative'))
    return result

def allocation_cost(rate_usd_per_gpu_hour: Real, billable_gpus: int,
                    extra_usd_per_hour: Real = 0) -> float:
    """Charge every allocated GPU, not just GPUs doing useful computation."""
    if isinstance(billable_gpus, bool) or not isinstance(billable_gpus, int) or billable_gpus < 1:
        raise ValueError('billable_gpus must be a positive integer')
    return (_number(rate_usd_per_gpu_hour, 'rate') * billable_gpus
            + _number(extra_usd_per_hour, 'extras'))

def required_throughput_ratio(hot_cost_per_hour: Real, other_cost_per_hour: Real) -> float:
    """Tie occurs at Q_hot / Q_other == C_hot / C_other; greater is cheaper."""
    return _number(hot_cost_per_hour, 'Hot Aisle cost') / _number(other_cost_per_hour, 'other cost', positive=True)

def cost_per_1000(hourly_cost: Real, accepted_units_per_billed_second: Real) -> float:
    """The rate denominator must include the billable window, including idle time."""
    return 1000 * _number(hourly_cost, 'hourly_cost') / (3600 * _number(accepted_units_per_billed_second, 'accepted rate', positive=True))

def relative_unit_cost_reduction(hot_unit_cost: Real, other_unit_cost: Real) -> float:
    """Negative means Hot Aisle is more expensive; no automatic winner filtering."""
    return 1 - _number(hot_unit_cost, 'Hot Aisle unit cost') / _number(other_unit_cost, 'other unit cost', positive=True)
