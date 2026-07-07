from repository import get_alerts
from response_utils import response

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    device_id = (event.get("pathParameters") or {}).get("device_id")
    if not device_id:
        return response(400, {"error": "Missing path parameter: device_id"})

    alerts = get_alerts(device_id)
    return response(200, alerts)
