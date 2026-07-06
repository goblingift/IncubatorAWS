import boto3
from boto3.dynamodb.types import TypeDeserializer
from config import HOURLY_TABLE_NAME, BUCKET_TTL_SECONDS

dynamodb = boto3.resource("dynamodb")
deserializer = TypeDeserializer()
hourly_table = dynamodb.Table(HOURLY_TABLE_NAME)

class LightRollupRepository:
    @staticmethod
    def ddb_to_python(ddb_item):
        return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}

    @staticmethod
    def add_reading(device_id, hour_bucket, light_intensity):
        hourly_table.update_item(
            Key={"device_id": device_id, "hour_bucket": hour_bucket},
            UpdateExpression="SET expires_at = :exp ADD light_sum :v, reading_count :one",
            ExpressionAttributeValues={
                ":exp": hour_bucket + BUCKET_TTL_SECONDS,
                ":v": light_intensity,
                ":one": 1,
            },
        )
