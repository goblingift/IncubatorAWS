import os

TABLE_NAME = os.environ.get("TABLE_NAME", "incubator_measurement_clean")

WINDOW_SECONDS = 3600  # fixed 60-minute lookback, not query-configurable

# --- Battery discharge curves --------------------------------------------
# voltage -> state-of-charge percent, PLACEHOLDER (straight line between
# incubator_settings' voltage_min/voltage_max defaults), NOT a real measured
# discharge curve. Replace IDLE_CURVE/HEATER_CURVE with literal
# (voltage, percent) lists once real data is delivered, and flip
# CURVE_CALIBRATED to True. No other file needs to change.
CURVE_CALIBRATED = False

def _placeholder_linear_curve(v_at_100, v_at_0):
    step = (v_at_100 - v_at_0) / 100
    return [(round(v_at_0 + step * pct, 3), pct) for pct in range(100, -1, -1)]

IDLE_CURVE = _placeholder_linear_curve(v_at_100=13.0, v_at_0=11.0)
HEATER_CURVE = _placeholder_linear_curve(v_at_100=12.6, v_at_0=10.6)  # sags under load

# Below this, a positive slope is treated as noise, not real drain. Set to 0
# to always project a runtime whenever the slope is even slightly negative.
MIN_DRAIN_RATE_PERCENT_PER_HOUR = 0.1
