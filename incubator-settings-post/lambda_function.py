import json
from decimal import Decimal
from datetime import datetime, timezone

from config import NUMERIC_FIELDS
from repository import save_settings
from response_utils import response

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    try:
        body = json.loads(event.get("body") or "{}")

        item = {
            "device_id": str(body["device_id"]).strip(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        for field in NUMERIC_FIELDS:
            item[field] = Decimal(str(body[field]))

        save_settings(item)
        return response(200, item)

    except json.JSONDecodeError:
        return response(400, {"message": "Invalid JSON body"})
    except KeyError as exc:
        return response(400, {"message": f"Missing required field: {str(exc)}"})
    except Exception as exc:
        return response(500, {"message": str(exc)})
