import logging
import time

from config import LOOKBACK_SECONDS
from repository import RejectedAlertRepository

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    cutoff = int(time.time()) - LOOKBACK_SECONDS

    rejections = RejectedAlertRepository.get_recent_rejections(cutoff)
    if not rejections:
        return {"statusCode": 200}

    lines = [
        f"- {item.get('device_id')} at {item.get('timestamp')}: {item.get('rejection_reason')}"
        for item in rejections
    ]
    message = (
        f"{len(rejections)} measurement(s) were rejected in the last 60 minutes:\n\n"
        + "\n".join(lines)
    )

    RejectedAlertRepository.publish_alert(
        subject=f"Incubator alert: {len(rejections)} rejected measurement(s) in the last 60 minutes",
        message=message,
    )

    return {"statusCode": 200}
