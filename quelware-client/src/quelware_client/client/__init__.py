from ._grpc import create_quelware_client
from ._standalone_grpc import create_standalone_client

__all__ = ["create_quelware_client", "create_standalone_client"]
