import os

TABLE_NAME = os.environ.get("TABLE_NAME", "incubator_measurement_clean")

RANGE_SECONDS = {
    "1h": 3600,
    "2h": 7200,
    "24h": 86400,
    "7d": 604800,
}

DEFAULT_RANGE = "24h"

MAX_POINTS = 750
