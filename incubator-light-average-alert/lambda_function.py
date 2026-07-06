import logging
import time
import uuid
from decimal import Decimal

from config import HOUR_SECONDS, LOOKBACK_HOURS
from repository import LightAverageRepository

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    now = int(time.time())
    current_hour_bucket = now // HOUR_SECONDS * HOUR_SECONDS
    start_bucket = current_hour_bucket - (LOOKBACK_HOURS - 1) * HOUR_SECONDS

    for device in LightAverageRepository.get_devices_with_light_avg_max():
        device_id = device.get("device_id")
        light_avg_max = device.get("light_avg_max")
        if not device_id or light_avg_max is None:
            continue

        try:
            buckets = LightAverageRepository.get_hourly_buckets(device_id, start_bucket, current_hour_bucket)

            total_sum = sum((b.get("light_sum", 0) for b in buckets), Decimal(0))
            total_count = sum(b.get("reading_count", 0) for b in buckets)

            if total_count == 0:
                continue  # no data in window (e.g. device offline) - no false alert

            average = total_sum / total_count

            if average > light_avg_max:
                LightAverageRepository.save_alert({
                    "device_id": device_id,
                    "alert_id": str(uuid.uuid4()),
                    "timestamp": current_hour_bucket,
                    "checked_at": now,
                    "field": "light_intensity_avg_24h",
                    "value": average,
                    "bound": "max",
                    "threshold": light_avg_max,
                })
                LightAverageRepository.publish_alert(
                    subject=f"Incubator alert: {device_id} light_intensity_avg_24h out of range",
                    message=(
                        f"Device {device_id} reported a 24h average light intensity of {average}, "
                        f"which is above the configured max threshold of {light_avg_max}."
                    ),
                )
        except Exception:
            logger.exception("Failed to evaluate light average for device %s", device_id)

    return {"statusCode": 200}
