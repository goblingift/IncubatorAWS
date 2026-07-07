import boto3
from boto3.dynamodb.conditions import Key
from config import TABLE_NAME

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

def get_alerts(device_id):
    items = []
    kwargs = {"KeyConditionExpression": Key("device_id").eq(device_id)}

    while True:
        result = table.query(**kwargs)
        items.extend(result.get("Items", []))
        if "LastEvaluatedKey" not in result:
            break
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]

    items.sort(key=lambda item: item.get("checked_at", 0), reverse=True)
    return items
