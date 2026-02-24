from abc import ABC

from quelware_core.entities.resource import ResourceId
from quelware_core.entities.unit import UnitLabel
from typing_extensions import Self


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

    def with_resource_ids(self, rids: list[ResourceId]) -> Self:
        self.rids = rids
        return self

    def __str__(self):
        base_msg = super().__str__()
        if hasattr(self, "rids") and self.rids:
            return f"{base_msg} (ids: {self.rids})"
        return base_msg


class LockConflictError(_ErrorWithResourceIdsMixin, QuelwareClientError): ...


class LockNotFoundError(QuelwareClientError): ...


class InvalidTokenError(QuelwareClientError): ...


class ResourceNotFoundError(_ErrorWithResourceIdsMixin, QuelwareClientError):
    DEFAULT_MESSAGE = "Resource not found."


class ResourceRoleNotMatchedError(_ErrorWithResourceIdsMixin, QuelwareClientError):
    DEFAULT_MESSAGE = "Resource role not matched."


class ResourceCategoryNotMatchedError(_ErrorWithResourceIdsMixin, QuelwareClientError):
    DEFAULT_MESSAGE = "Resource role not matched."


class DuplicateIdError(QuelwareClientError): ...


class _ErrorWithUnitLabelsMixin(ABC):
    unit_labels: list[UnitLabel]

    def with_unit_labels(self, unit_labels: list[UnitLabel]) -> Self:
        self.unit_labels = unit_labels
        return self

    def __str__(self):
        base_msg = super().__str__()
        if hasattr(self, "unit_labels") and self.unit_labels:
            return f"{base_msg} (unit_labels: {self.unit_labels})"
        return base_msg


class UnitNotFoundError(_ErrorWithUnitLabelsMixin, QuelwareClientError): ...
