import json

from google.rpc.error_details_pb2 import ErrorInfo


def build_details(obj):
    obj_json = json.dumps(obj)
    return [ErrorInfo(metadata={"json": obj_json})]


def extract_obj(details):
    if details:
        for detail in details:
            if isinstance(detail, ErrorInfo):
                obj_json = detail.metadata["json"]
                obj = json.loads(obj_json)
                return obj


__all__ = ["build_details", "extract_obj"]
