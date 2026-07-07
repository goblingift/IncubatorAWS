import boto3
from boto3.dynamodb.conditions import Key
from response_utils import response

TABLE_NAME = "incubator_measurement_clean"

dynamodb = boto3.resource("dynamodb")
table    = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    try:
        device_id = (event.get("pathParameters") or {}).get("device_id")

        if device_id:
            result = table.query(
                KeyConditionExpression=Key("device_id").eq(device_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = result.get("Items", [])
        else:
            result = table.scan()
            items = sorted(result.get("Items", []), key=lambda x: x.get("timestamp", ""), reverse=True)[:1]

        body = items[0] if items else {"message": "No measurements found"}

        return response(200, body)

    except Exception as e:
        return response(500, {"error": str(e)})