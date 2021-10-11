import json
import boto3
import uuid
import os
from botocore.vendored import requests
from botocore.client import Config

dynamodb_client = boto3.client("dynamodb")
table_name = os.environ["table_name"]

def rekognition_on_s3_upload(event, context):
    bucket_name = os.environ["s3_bucket"]
    rekognition_client = boto3.client("rekognition")

    for record in event["Records"]:
        key = record["s3"]["object"]["key"]
        rkg_res = rekognition_client.detect_labels(Image={"S3Object":{"Bucket": bucket_name, "Name": key}}, MaxLabels=3)
        try:
            dynamodb_client.update_item(
                TableName = table_name,
                Key = { "id": { "S": key }},
                UpdateExpression = "set labels=:labels",
                ExpressionAttributeValues={
                    ":labels": { "S" : json.dumps(rkg_res) }
                }
            )
        except:
            print(f"Error updating blob (id: {key})")


def post_blob(event, context):
    callback_url = ""
    try:
        callback_url = event["queryStringParameters"]["callback_url"]
    except:
        callback_url = ""
    bucket_name = os.environ["s3_bucket"]

    blob_id = str(uuid.uuid4())

    s3_client = boto3.client("s3", 
        aws_access_key_id = os.environ["aws_access_key_id"],
        aws_secret_access_key = os.environ["aws_secret_access_key"],
        config=Config(signature_version="s3v4"))

    s3_params = {
        "Bucket": bucket_name,
        "Key": blob_id
    }

    response = {}

    try:
        s3_res = s3_client.generate_presigned_url("put_object", Params=s3_params, ExpiresIn=3600)

        body = {
                "id": { "S": blob_id },
                "presigned_url": { "S": str(s3_res) },
            }

        if callback_url != "":
            body["callback_url"] = { "S": callback_url }
        
        dynamodb_client.put_item(
            TableName = table_name,
            Item = body
        )

        response = {
            "statusCode": 200,
            "body": json.dumps(body)
        }
    except:
        response = {
            "statusCode": 500,
            "body": "Presigned URL generation failed."
        }

    return response

def get_blob(event, context):
    id = event["pathParameters"]["blob_id"]
    response = {}
    try:
        resp = dynamodb_client.get_item(
            TableName=table_name,
            Key = { "id": 
                { 
                    "S": str(id)
                } 
            }
        )

        item = resp.get("Item")

        response = {
            "statusCode": 200,
            "body": json.dumps(item)
        }
    except:
        response = {
            "statusCode": 500,
            "body": f"Failed to retrieve blob (id: {id})."
        }
    return response

def make_callback(event, context):
    for record in event["Records"]:
        if("UPDATE" == record["eventName"]):
            body = record["dynamodb"]["NewImage"]
            if "callback_url" in body:
                try:
                    requests.post(body["callback_url"], data=body)
                except:
                    print(f"Request to callback URL {body['callback_url']} failed")

