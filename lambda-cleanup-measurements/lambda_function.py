from processor import MeasurementProcessor
from repositories import DynamoRepository

processor = MeasurementProcessor()

def lambda_handler(event, context):
    batch_item_failures = []

    for record in event.get("Records", []):
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber")
        try:
            if record.get("eventName") != "INSERT":
                continue
            raw = DynamoRepository.ddb_to_python(record["dynamodb"]["NewImage"])
            result = processor.process(raw)
            if result.is_valid:
                DynamoRepository.save_clean(result.clean_item)
            else:
                DynamoRepository.save_rejected(result.clean_item)
        except Exception:
            if sequence_number:
                batch_item_failures.append({"itemIdentifier": sequence_number})

    return {"batchItemFailures": batch_item_failures}
