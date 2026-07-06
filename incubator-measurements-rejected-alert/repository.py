import boto3
from boto3.dynamodb.conditions import Attr
from config import REJECTED_TABLE_NAME, ALERTS_TOPIC_ARN

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
rejected_table = dynamodb.Table(REJECTED_TABLE_NAME)

class RejectedAlertRepository:
    @staticmethod
    def get_recent_rejections(cutoff):
        items = []
        scan_kwargs = {"FilterExpression": Attr("processed_at").gte(cutoff)}
        while True:
            result = rejected_table.scan(**scan_kwargs)
            items.extend(result.get("Items", []))
            last_key = result.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key
        return items

    @staticmethod
    def publish_alert(subject, message):
        sns.publish(TopicArn=ALERTS_TOPIC_ARN, Subject=subject, Message=message)
