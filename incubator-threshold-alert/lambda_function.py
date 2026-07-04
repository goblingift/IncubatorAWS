import logging
import time
import uuid

from checker import ThresholdChecker
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
