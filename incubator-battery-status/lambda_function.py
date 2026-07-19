import time

from config import (
    WINDOW_SECONDS, IDLE_CURVE, HEATER_CURVE, CURVE_CALIBRATED,
    MIN_DRAIN_RATE_PERCENT_PER_HOUR,
)
from repository import get_recent_measurements
from curve import percent_for_reading
from regression import linear_regression
from response_utils import response

SECONDS_PER_HOUR = 3600

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    try:
        device_id = (event.get("pathParameters") or {}).get("device_id")
        if not device_id:
            return response(400, {"error": "Missing path parameter: device_id"})

        end = int(time.time())
        start = end - WINDOW_SECONDS
        items = get_recent_measurements(device_id, start, end)

        readings = [item for item in items if item.get("voltage") is not None]
        if not readings:
            return response(200, {
                "device_id": device_id,
                "status": "no_data",
                "message": f"No voltage readings in the last {WINDOW_SECONDS // 60} minutes",
                "curve_calibrated": CURVE_CALIBRATED,
            })

        percent_series = [
            (int(item["timestamp"]), percent_for_reading(item, IDLE_CURVE, HEATER_CURVE))
            for item in readings
        ]
        latest_item = readings[-1]
        current_percent = percent_for_reading(latest_item, IDLE_CURVE, HEATER_CURVE)

        base = {
            "device_id": device_id,
            "timestamp": int(latest_item["timestamp"]),
            "battery_voltage": float(latest_item["voltage"]),
            "battery_percent": round(current_percent, 2),
            "sample_count": len(percent_series),
            "curve_calibrated": CURVE_CALIBRATED,
        }

        try:
            slope_per_second, _ = linear_regression(percent_series)
        except ValueError:
            return response(200, {
                **base,
                "status": "insufficient_data",
                "message": f"Need >=2 readings at different timestamps in the last "
                           f"{WINDOW_SECONDS // 60} minutes to estimate a drain rate",
                "drain_rate_percent_per_hour": None,
                "remaining_hours": None,
                "predicted_shutdown_at": None,
            })

        drain_rate_per_hour = -slope_per_second * SECONDS_PER_HOUR

        if drain_rate_per_hour <= MIN_DRAIN_RATE_PERCENT_PER_HOUR:
            return response(200, {
                **base,
                "status": "stable_or_charging",
                "message": "Battery is stable or charging - no finite runtime to project",
                "drain_rate_percent_per_hour": round(drain_rate_per_hour, 2),
                "remaining_hours": None,
                "predicted_shutdown_at": None,
            })

        remaining_hours = current_percent / drain_rate_per_hour
        return response(200, {
            **base,
            "status": "draining",
            "drain_rate_percent_per_hour": round(drain_rate_per_hour, 2),
            "remaining_hours": round(remaining_hours, 2),
            "predicted_shutdown_at": end + int(remaining_hours * SECONDS_PER_HOUR),
        })

    except Exception as e:
        return response(500, {"error": str(e)})
