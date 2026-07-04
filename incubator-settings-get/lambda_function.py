from datetime import datetime, timezone

from config import DEFAULT_SETTINGS
from repository import get_settings
from response_utils import response

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    device_id = (event.get("pathParameters") or {}).get("device_id")
    if not device_id:
        return response(400, {"error": "Missing path parameter: device_id"})

    item = get_settings(device_id)

    if not item:
        item = {
            "device_id": device_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **DEFAULT_SETTINGS,
        }

    return response(200, item)
