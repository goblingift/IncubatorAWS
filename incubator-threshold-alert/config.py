SETTINGS_TABLE_NAME = "incubator_settings"
ALERTS_TABLE_NAME = "incubator_alerts"
ALERTS_TOPIC_ARN = "arn:aws:sns:eu-north-1:683966915447:incubator-measurement-outside-allowed-range"

# Maps a measurement field to its threshold field(s) in incubator_settings.
# "abs": True means the measurement is compared by absolute value against
# a single max threshold (used for signed fields with a symmetric tolerance).
THRESHOLD_FIELDS = {
    "temperature_celsius": {"min": "temperature_min", "max": "temperature_max"},
    "humidity_rh": {"min": "humidity_min", "max": "humidity_max"},
    "co2_ppm": {"max": "co2_max"},
    "sound_intensity": {"max": "sound_max"},
    "weight_gram": {"min": "weight_min", "max": "weight_max"},
    "pitch_deg": {"max": "pitch_deg_max", "abs": True},
    "roll_deg": {"max": "roll_deg_max", "abs": True},
    "voltage": {"min": "voltage_min", "max": "voltage_max"},
    "current": {"min": "current_min", "max": "current_max"},
    "water_level": {"min": "water_level_min", "max": "water_level_max"},
    "battery_percent": {"min": "battery_percent_min"},
}

# --- Battery discharge curves --------------------------------------------
# Duplicated verbatim from incubator-battery-status/config.py - no shared
# Lambda layer in this repo. incubator-battery-status is the source of
# truth: if the curves are ever re-measured, update both files together,
# nothing enforces them staying in sync automatically.
IDLE_CURVE = [
    (12.39, 100), (12.19, 95), (12.10, 90), (11.93, 85), (11.74, 80),
    (11.59, 75), (11.47, 70), (11.33, 65), (11.18, 60), (11.03, 55),
    (10.90, 50), (10.78, 45), (10.69, 40), (10.60, 35), (10.51, 30),
    (10.40, 25), (10.27, 20), (10.12, 15), (9.96, 10), (9.70, 5), (8.68, 0),
]

HEATER_CURVE = [
    (11.88, 100), (11.50, 95), (11.42, 90), (11.27, 85), (11.10, 80),
    (10.97, 75), (10.86, 70), (10.75, 65), (10.62, 60), (10.49, 55),
    (10.36, 50), (10.26, 45), (10.18, 40), (10.10, 35), (10.01, 30),
    (9.91, 25), (9.79, 20), (9.65, 15), (9.49, 10), (9.23, 5), (8.26, 0),
]
