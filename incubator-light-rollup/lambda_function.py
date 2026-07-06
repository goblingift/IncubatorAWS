import logging

from config import HOUR_SECONDS
from repository import LightRollupRepository

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    batch_item_failures = []

    for record in event.get("Records", []):
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber")
        try:
            # INSERT only: this lambda accumulates a running sum/count per hour
            # bucket. A MODIFY on an already-counted reading would double-count
            # it, and the stream is NEW_IMAGE-only so there's no OldImage to
            # subtract first.
            if record.get("eventName") != "INSERT":
                continue

            measurement = LightRollupRepository.ddb_to_python(record["dynamodb"]["NewImage"])

            if measurement.get("cleaning_status") != "clean":
                continue

            device_id = measurement.get("device_id")
            timestamp = measurement.get("timestamp")
            if not device_id or timestamp is None:
                continue

            # Presence/None check, not truthiness: 0 lux is a legitimate
            # reading (e.g. incubator kept dark) and must still be counted,
            # otherwise the average would be biased toward only lit readings.
            if "light_intensity" not in measurement or measurement["light_intensity"] is None:
                continue

            hour_bucket = int(timestamp // HOUR_SECONDS * HOUR_SECONDS)
            LightRollupRepository.add_reading(device_id, hour_bucket, measurement["light_intensity"])
        except Exception:
            logger.exception("Failed to process record %s", sequence_number)
            if sequence_number:
                batch_item_failures.append({"itemIdentifier": sequence_number})

    return {"batchItemFailures": batch_item_failures}
