import logging
import time
import uuid
from decimal import Decimal

from checker import ThresholdChecker
from config import IDLE_CURVE, HEATER_CURVE
from curve import percent_for_reading
from repository import ThresholdRepository

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    batch_item_failures = []

    for record in event.get("Records", []):
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber")
        try:
            if record.get("eventName") not in ("INSERT", "MODIFY"):
                continue

            measurement = ThresholdRepository.ddb_to_python(record["dynamodb"]["NewImage"])

            if measurement.get("cleaning_status") != "clean":
                continue

            device_id = measurement.get("device_id")
            if not device_id:
                continue

            # Synthetic field, not written by lambda-cleanup-measurements:
            # derived from voltage (+ relay_state_3 for heater-load curve
            # selection) via the same discharge-curve interpolation as
            # incubator-battery-status, so ThresholdChecker can compare it
            # against battery_percent_min like any other measurement field.
            # Must be Decimal, not the native float curve.py returns -
            # DynamoDB's put_item rejects native floats.
            if measurement.get("voltage") is not None:
                measurement["battery_percent"] = Decimal(
                    str(round(percent_for_reading(measurement, IDLE_CURVE, HEATER_CURVE), 2))
                )

            settings = ThresholdRepository.get_settings(device_id)
            if not settings:
                continue

            violations = ThresholdChecker.check(measurement, settings)

            for violation in violations:
                ThresholdRepository.save_alert({
                    "device_id": device_id,
                    "alert_id": str(uuid.uuid4()),
                    "timestamp": measurement.get("timestamp"),
                    "checked_at": int(time.time()),
                    "field": violation["field"],
                    "value": violation["value"],
                    "bound": violation["bound"],
                    "threshold": violation["threshold"],
                })
                ThresholdRepository.publish_alert(
                    subject=f"Incubator alert: {device_id} {violation['field']} out of range",
                    message=(
                        f"Device {device_id} reported {violation['field']} = {violation['value']}, "
                        f"which is {'below' if violation['bound'] == 'min' else 'above'} the "
                        f"configured {violation['bound']} threshold of {violation['threshold']}."
                    ),
                )
        except Exception:
            logger.exception("Failed to process record %s", sequence_number)
            if sequence_number:
                batch_item_failures.append({"itemIdentifier": sequence_number})

    return {"batchItemFailures": batch_item_failures}
