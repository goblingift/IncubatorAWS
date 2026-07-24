import logging
import time
import uuid

from config import HOUR_SECONDS, LOOKBACK_HOURS
from repository import LightSleepRepository

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    now = int(time.time())
    current_hour_bucket = now // HOUR_SECONDS * HOUR_SECONDS
    start_bucket = current_hour_bucket - (LOOKBACK_HOURS - 1) * HOUR_SECONDS

    for device in LightSleepRepository.get_devices_with_light_sleep_settings():
        device_id = device.get("device_id")
        light_sleep_max = device.get("light_sleep_max")
        light_sleep_min_hours = device.get("light_sleep_min_hours")
        if not device_id or light_sleep_max is None or light_sleep_min_hours is None:
            continue

        try:
            buckets = LightSleepRepository.get_hourly_buckets(device_id, start_bucket, current_hour_bucket)

            total_count = sum(b.get("reading_count", 0) for b in buckets)
            if total_count == 0:
                continue  # no data at all in the window (e.g. device offline) - no false alert

            # A missing hour_bucket row (no readings that hour) is silently
            # excluded from this count: incubator-light-rollup only ever
            # creates a row via ADD light_sum, reading_count together, so
            # there's no such thing as a row with reading_count 0. A
            # reporting gap therefore can't masquerade as evidence of
            # darkness.
            sleep_friendly_hours = sum(
                1 for b in buckets
                if b.get("reading_count", 0) > 0
                and (b.get("light_sum", 0) / b.get("reading_count", 1)) <= light_sleep_max
            )

            if sleep_friendly_hours < light_sleep_min_hours:
                LightSleepRepository.save_alert({
                    "device_id": device_id,
                    "alert_id": str(uuid.uuid4()),
                    "timestamp": current_hour_bucket,
                    "checked_at": now,
                    "field": "light_sleep_hours_24h",
                    "value": sleep_friendly_hours,
                    "bound": "min",
                    "threshold": light_sleep_min_hours,
                })
                LightSleepRepository.publish_alert(
                    subject=f"Incubator alert: {device_id} light_sleep_hours_24h out of range",
                    message=(
                        f"Device {device_id} had only {sleep_friendly_hours} sleep-friendly hour(s) "
                        f"(hourly avg. light intensity <= {light_sleep_max} lux) out of the last "
                        f"{LOOKBACK_HOURS}h, below the configured minimum of {light_sleep_min_hours}."
                    ),
                )
        except Exception:
            logger.exception("Failed to evaluate light sleep hours for device %s", device_id)

    return {"statusCode": 200}
