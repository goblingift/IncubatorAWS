import time

from config import RANGE_SECONDS, DEFAULT_RANGE
from repository import get_measurements
from downsampler import downsample
from response_utils import response

def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return response(200, {"message": "ok"})

    try:
        device_id = (event.get("pathParameters") or {}).get("device_id")
        if not device_id:
            return response(400, {"error": "Missing path parameter: device_id"})

        range_param = (event.get("queryStringParameters") or {}).get("range", DEFAULT_RANGE)
        if range_param not in RANGE_SECONDS:
            return response(400, {
                "error": f"Invalid range '{range_param}'. Must be one of: {', '.join(RANGE_SECONDS)}"
            })

        end = int(time.time())
        start = end - RANGE_SECONDS[range_param]

        items = get_measurements(device_id, start, end)
        return response(200, downsample(items, start, end))
    except Exception as e:
        return response(500, {"error": str(e)})
