import time

from config import HOUR_SECONDS, LOOKBACK_HOURS, DEFAULT_LIGHT_SLEEP_MAX, DEFAULT_LIGHT_SLEEP_MIN_HOURS
from repository import LightSleepStatusRepository
from response_utils import response

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    try:
        device_id = (event.get("pathParameters") or {}).get("device_id")
        if not device_id:
            return response(400, {"error": "Missing path parameter: device_id"})

        now = int(time.time())
        current_hour_bucket = now // HOUR_SECONDS * HOUR_SECONDS
        start_bucket = current_hour_bucket - (LOOKBACK_HOURS - 1) * HOUR_SECONDS

        settings = LightSleepStatusRepository.get_settings(device_id) or {}
        light_sleep_max = settings.get("light_sleep_max", DEFAULT_LIGHT_SLEEP_MAX)
        light_sleep_min_hours = settings.get("light_sleep_min_hours", DEFAULT_LIGHT_SLEEP_MIN_HOURS)

        buckets = LightSleepStatusRepository.get_hourly_buckets(device_id, start_bucket, current_hour_bucket)

        total_count = sum(b.get("reading_count", 0) for b in buckets)
        if total_count == 0:
            return response(200, {
                "device_id": device_id,
                "status": "no_data",
                "message": f"No light readings in the last {LOOKBACK_HOURS} hours",
                "sleep_friendly_hours": None,
                "light_sleep_min_hours": light_sleep_min_hours,
                "light_sleep_max": light_sleep_max,
                "passing": None,
                "sample_count": 0,
                "bucket_count": len(buckets),
            })

        sleep_friendly_hours = sum(
            1 for b in buckets
            if b.get("reading_count", 0) > 0
            and (b.get("light_sum", 0) / b.get("reading_count", 1)) <= light_sleep_max
        )

        return response(200, {
            "device_id": device_id,
            "status": "ok",
            "sleep_friendly_hours": sleep_friendly_hours,
            "light_sleep_min_hours": light_sleep_min_hours,
            "light_sleep_max": light_sleep_max,
            "passing": sleep_friendly_hours >= light_sleep_min_hours,
            "sample_count": total_count,
            "bucket_count": len(buckets),
        })

    except Exception as e:
        return response(500, {"error": str(e)})
