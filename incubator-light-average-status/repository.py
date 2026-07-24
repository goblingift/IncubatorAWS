import boto3
from boto3.dynamodb.conditions import Key
from config import HOURLY_TABLE_NAME, SETTINGS_TABLE_NAME

dynamodb = boto3.resource("dynamodb")
hourly_table = dynamodb.Table(HOURLY_TABLE_NAME)
settings_table = dynamodb.Table(SETTINGS_TABLE_NAME)

class LightSleepStatusRepository:
    @staticmethod
    def get_hourly_buckets(device_id, start_bucket, end_bucket):
        result = hourly_table.query(
            KeyConditionExpression=Key("device_id").eq(device_id) & Key("hour_bucket").between(start_bucket, end_bucket),
        )
        return result.get("Items", [])

    @staticmethod
    def get_settings(device_id):
        result = settings_table.get_item(Key={"device_id": device_id})
        return result.get("Item")
