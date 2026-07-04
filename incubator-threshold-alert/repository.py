import boto3
from boto3.dynamodb.types import TypeDeserializer
from config import SETTINGS_TABLE_NAME, ALERTS_TABLE_NAME, ALERTS_TOPIC_ARN

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
deserializer = TypeDeserializer()
settings_table = dynamodb.Table(SETTINGS_TABLE_NAME)
alerts_table = dynamodb.Table(ALERTS_TABLE_NAME)

class ThresholdRepository:
    @staticmethod
    def ddb_to_python(ddb_item):
        return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}

    @staticmethod
    def get_settings(device_id):
        result = settings_table.get_item(Key={"device_id": device_id})
        return result.get("Item")

    @staticmethod
    def save_alert(alert):
        alerts_table.put_item(Item=alert)

    @staticmethod
    def publish_alert(subject, message):
        sns.publish(TopicArn=ALERTS_TOPIC_ARN, Subject=subject, Message=message)
