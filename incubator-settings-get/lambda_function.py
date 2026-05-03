import json
import os
from decimal import Decimal
from datetime import datetime, timezone

import boto3

TABLE_NAME = os.environ.get("TABLE_NAME", "incubator_settings")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,GET",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    device_id = (event.get("pathParameters") or {}).get("device_id")
    if not device_id:
        return response(400, {"error": "Missing path parameter: device_id"})

    result = table.get_item(Key={"device_id": device_id})
    item = result.get("Item")

    if not item:
        item = {
            "device_id": device_id,
            "target_temperature": 37,
            "target_humidity": 50,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    return response(200, item)