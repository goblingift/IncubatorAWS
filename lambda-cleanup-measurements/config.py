CLEAN_TABLE_NAME = "incubator_measurement_clean"
REJECTED_TABLE_NAME = "incubator_measurement_rejected"

FIELD_SCHEMA = {
    "device_id": {"type": "string", "required": True, "strip": True, "max_length": 128},
    "timestamp": {"type": "epoch_int", "required": True, "min": 0},
    "co2_ppm": {"type": "decimal", "required": False, "min": 0, "max": 40000},
    "current": {"type": "decimal", "required": False, "min": 0, "max": 100},
    "humidity_rh": {"type": "decimal", "required": False, "min": 0, "max": 100},
    "light_intensity": {"type": "decimal", "required": False, "min": 0},
    "pitch_deg": {"type": "decimal", "required": False, "min": -180, "max": 180},
    "relay_state": {"type": "bool_int", "required": False},
    "roll_deg": {"type": "decimal", "required": False, "min": -180, "max": 180},
    "sound_intensity": {"type": "decimal", "required": False, "min": 0},
    "temperature_celsius": {"type": "decimal", "required": False, "min": -20, "max": 80},
    "voltage": {"type": "decimal", "required": False, "min": 0, "max": 60},
    "water_level": {"type": "decimal", "required": False, "min": 0},
    "weight_gram": {"type": "decimal", "required": False, "min": 0, "max": 20000},
}

OPTIONAL_PASSTHROUGH_FIELDS = set()
