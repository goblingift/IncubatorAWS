import boto3
from decimal import Decimal
from boto3.dynamodb.types import TypeDeserializer
from config import CLEAN_TABLE_NAME, REJECTED_TABLE_NAME

dynamodb = boto3.resource("dynamodb")
deserializer = TypeDeserializer()
clean_table = dynamodb.Table(CLEAN_TABLE_NAME)
rejected_table = dynamodb.Table(REJECTED_TABLE_NAME)

class DynamoRepository:
    @staticmethod
    def ddb_to_python(ddb_item):
        return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}

    @staticmethod
    def to_dynamo_compatible(value):
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, dict):
            return {k: DynamoRepository.to_dynamo_compatible(v) for k, v in value.items()}
        if isinstance(value, list):
            return [DynamoRepository.to_dynamo_compatible(v) for v in value]
        return value

    @staticmethod
    def save_clean(item):
        clean_table.put_item(Item=DynamoRepository.to_dynamo_compatible(item))

    @staticmethod
    def save_rejected(item):
        rejected_table.put_item(Item=DynamoRepository.to_dynamo_compatible(item))
