import boto3
from boto3.dynamodb.conditions import Key, Attr
from config import SETTINGS_TABLE_NAME, HOURLY_TABLE_NAME, ALERTS_TABLE_NAME, ALERTS_TOPIC_ARN

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
settings_table = dynamodb.Table(SETTINGS_TABLE_NAME)
hourly_table = dynamodb.Table(HOURLY_TABLE_NAME)
alerts_table = dynamodb.Table(ALERTS_TABLE_NAME)

class LightAverageRepository:
    @staticmethod
    def get_devices_with_light_avg_max():
        items = []
        scan_kwargs = {
            "FilterExpression": Attr("light_avg_max").exists(),
            "ProjectionExpression": "device_id, light_avg_max",
        }
        while True:
            result = settings_table.scan(**scan_kwargs)
            items.extend(result.get("Items", []))
            last_key = result.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
        return items

    @staticmethod
    def get_hourly_buckets(device_id, start_bucket, end_bucket):
        result = hourly_table.query(
            KeyConditionExpression=Key("device_id").eq(device_id) & Key("hour_bucket").between(start_bucket, end_bucket),
        )
        return result.get("Items", [])

    @staticmethod
    def save_alert(alert):
        alerts_table.put_item(Item=alert)

    @staticmethod
    def publish_alert(subject, message):
        sns.publish(TopicArn=ALERTS_TOPIC_ARN, Subject=subject, Message=message)
