import boto3
from config import TABLE_NAME

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

def get_settings(device_id):
    result = table.get_item(Key={"device_id": device_id})
    return result.get("Item")
