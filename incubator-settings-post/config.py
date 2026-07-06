import os

TABLE_NAME = os.environ.get("TABLE_NAME", "incubator_settings")

NUMERIC_FIELDS = [
    "temperature_min",
    "temperature_max",
    "humidity_min",
    "humidity_max",
    "co2_max",
    "light_max",
    "pitch_deg_max",
    "roll_deg_max",
    "sound_max",
    "weight_min",
    "weight_max",
    "voltage_min",
    "voltage_max",
    "current_min",
    "current_max",
    "water_level_min",
    "water_level_max"
]
