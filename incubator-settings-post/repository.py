import boto3
from config import TABLE_NAME

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

def save_settings(item):
    table.put_item(Item=item)
