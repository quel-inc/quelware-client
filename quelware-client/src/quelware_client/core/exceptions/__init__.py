from abc import ABC
from typing import Self

from quelware_core.entities.resource import ResourceId


class QuelwareClientError(Exception):
    DEFAULT_MESSAGE: str = ""

    def __init__(self, message: str | None = None):
        if message is None:
            self.message = self.DEFAULT_MESSAGE
        else:
            self.message = message
        super().__init__(self.message)


class _ErrorWithResourceIdsMixin(ABC):
    rids: list[ResourceId]

    def with_resource_ids(self, iids: list[ResourceId]) -> Self:
        self.rids = iids
        return self

    def __str__(self):
        return f"{super().__str__()} (ids: {self.rids})"


class LockConflictError(QuelwareClientError, _ErrorWithResourceIdsMixin): ...


class LockNotFoundError(QuelwareClientError): ...


class InvalidTokenError(QuelwareClientError): ...


class ResourceNotFoundError(QuelwareClientError, _ErrorWithResourceIdsMixin):
    DEFAULT_MESSAGE = "Resource not found."


class ResourceRoleNotMatchedError(QuelwareClientError, _ErrorWithResourceIdsMixin):
    DEFAULT_MESSAGE = "Resource role not matched."


class ResourceTypeNotMatchedError(QuelwareClientError, _ErrorWithResourceIdsMixin):
    DEFAULT_MESSAGE = "Resource role not matched."


class DuplicateIdError(QuelwareClientError): ...


class UnitNotFoundError(QuelwareClientError): ...
