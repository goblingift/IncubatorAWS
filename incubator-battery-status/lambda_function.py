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

def _relay_state(item):
    return int(item.get("relay_state_3") or 0)

def _trailing_same_state_segment(readings):
    """Walk backward from the most recent reading and keep only the
    contiguous run sharing its relay_state_3. A heater on/off transition
    within the window switches which discharge curve applies, and the two
    curves aren't perfectly reconciled against each other - regressing
    across that switch reads the resulting voltage/percent jump as a
    drain-rate trend that isn't really there (e.g. the heater turning off
    looks like charging). Restricting to the same-state tail avoids it, at
    the cost of a shorter series (or none at all) right after a transition."""
    if not readings:
        return []
    current_state = _relay_state(readings[-1])
    segment = []
    for item in reversed(readings):
        if _relay_state(item) != current_state:
            break
        segment.append(item)
    segment.reverse()
    return segment

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

        latest_item = readings[-1]
        current_percent = percent_for_reading(latest_item, IDLE_CURVE, HEATER_CURVE)

        base = {
            "device_id": device_id,
            "timestamp": int(latest_item["timestamp"]),
            "battery_voltage": float(latest_item["voltage"]),
            "battery_percent": round(current_percent, 2),
            "heater_active": _relay_state(latest_item) == 1,
            "curve_calibrated": CURVE_CALIBRATED,
        }

        # Regress only over the trailing same-heater-state segment, not the
        # whole window - see _trailing_same_state_segment for why.
        segment = _trailing_same_state_segment(readings)
        percent_series = [
            (int(item["timestamp"]), percent_for_reading(item, IDLE_CURVE, HEATER_CURVE))
            for item in segment
        ]
        base["sample_count"] = len(percent_series)

        try:
            slope_per_second, _ = linear_regression(percent_series)
        except ValueError:
            return response(200, {
                **base,
                "status": "insufficient_data",
                "message": "Need >=2 readings at different timestamps with an unchanged "
                           "heater state to estimate a drain rate (heater state may have "
                           "just changed)",
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
