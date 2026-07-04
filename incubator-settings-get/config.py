import os

TABLE_NAME = os.environ.get("TABLE_NAME", "incubator_settings")

DEFAULT_SETTINGS = {
    "temperature_target": 37.5,
    "temperature_min": 36,
    "temperature_max": 39,
    "humidity_target": 55,
    "humidity_min": 45,
    "humidity_max": 70,
    "co2_max": 7100,
    "light_max": 7,
    "pitch_deg_max": 15,
    "roll_deg_max": 15,
    "sound_max": 80,
    "weight_min": 0,
    "weight_max": 5000,
    "voltage_min": 11,
    "voltage_max": 13,
    "current_min": 0,
    "current_max": 2,
    "water_level_min": 10,
    "water_level_max": 100
}
