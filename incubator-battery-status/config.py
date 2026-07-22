import os

TABLE_NAME = os.environ.get("TABLE_NAME", "incubator_measurement_clean")

WINDOW_SECONDS = 3600  # fixed 60-minute lookback, not query-configurable

# --- Battery discharge curves --------------------------------------------
# voltage -> state-of-charge percent, measured by discharging the incubator's
# battery under idle and heater-loaded conditions (5% increments). Each list
# is sorted descending by voltage/percent (100% down to 0%), matching
# curve.interpolate_percent's expected shape.
CURVE_CALIBRATED = True

IDLE_CURVE = [
    (12.39, 100),
    (12.19, 95),
    (12.10, 90),
    (11.93, 85),
    (11.74, 80),
    (11.59, 75),
    (11.47, 70),
    (11.33, 65),
    (11.18, 60),
    (11.03, 55),
    (10.90, 50),
    (10.78, 45),
    (10.69, 40),
    (10.60, 35),
    (10.51, 30),
    (10.40, 25),
    (10.27, 20),
    (10.12, 15),
    (9.96, 10),
    (9.70, 5),
    (8.68, 0),
]

HEATER_CURVE = [
    (11.88, 100),
    (11.50, 95),
    (11.42, 90),
    (11.27, 85),
    (11.10, 80),
    (10.97, 75),
    (10.86, 70),
    (10.75, 65),
    (10.62, 60),
    (10.49, 55),
    (10.36, 50),
    (10.26, 45),
    (10.18, 40),
    (10.10, 35),
    (10.01, 30),
    (9.91, 25),
    (9.79, 20),
    (9.65, 15),
    (9.49, 10),
    (9.23, 5),
    (8.26, 0),
]

# Below this, a positive slope is treated as noise, not real drain. Set to 0
# to always project a runtime whenever the slope is even slightly negative.
MIN_DRAIN_RATE_PERCENT_PER_HOUR = 0.1
