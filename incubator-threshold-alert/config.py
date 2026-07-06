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
}
