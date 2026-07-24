HOURLY_TABLE_NAME = "incubator_light_hourly"
SETTINGS_TABLE_NAME = "incubator_settings"

HOUR_SECONDS = 3600
LOOKBACK_HOURS = 24

# Used only when a device has no incubator_settings row yet, or an existing
# row predates this feature. Duplicated from incubator-settings-get/config.py
# - if those defaults change, update both files together.
DEFAULT_LIGHT_SLEEP_MAX = 20
DEFAULT_LIGHT_SLEEP_MIN_HOURS = 8
