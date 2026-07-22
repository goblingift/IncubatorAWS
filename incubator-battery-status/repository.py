import boto3
from boto3.dynamodb.conditions import Key
from config import TABLE_NAME

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

def get_recent_measurements(device_id, start, end):
    items = []
    kwargs = {
        "KeyConditionExpression": Key("device_id").eq(device_id) & Key("timestamp").between(start, end),
        "ProjectionExpression": "#ts, voltage, relay_state_3",
        "ExpressionAttributeNames": {"#ts": "timestamp"},
        "ScanIndexForward": True,
    }
    while True:
        result = table.query(**kwargs)
        items.extend(result.get("Items", []))
        if "LastEvaluatedKey" not in result:
            break
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    return items
