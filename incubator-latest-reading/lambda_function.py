import boto3
import json
from boto3.dynamodb.conditions import Key

TABLE_NAME = "incubator_measurement_clean"

dynamodb = boto3.resource("dynamodb")
table    = dynamodb.Table(TABLE_NAME)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}

def lambda_handler(event, context):
    try:
        device_id = (event.get("pathParameters") or {}).get("device_id")

        if device_id:
            response = table.query(
                KeyConditionExpression=Key("device_id").eq(device_id),
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get("Items", [])
        else:
            response = table.scan()
            items = sorted(response.get("Items", []), key=lambda x: x.get("timestamp", ""), reverse=True)[:1]

        body = items[0] if items else {"message": "No measurements found"}

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(body, default=str),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }