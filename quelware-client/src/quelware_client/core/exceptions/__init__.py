from abc import ABC
from collections.abc import Mapping

from quelware_core.entities.resource import ResourceId
from quelware_core.entities.result import ResultContainer
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


class InvalidUnitStatusError(_ErrorWithUnitLabelsMixin, QuelwareClientError): ...


class ServiceUnavailableError(QuelwareClientError):
    DEFAULT_MESSAGE = "The requested service is not available on the server."


class RunFailedError(QuelwareClientError):
    """Some instruments of a run failed.

    ``failures`` holds the error each of them raised, and ``results`` the
    results of the others.
    """

    def __init__(
        self,
        failures: Mapping[ResourceId, BaseException],
        results: Mapping[ResourceId, ResultContainer],
    ):
        self.failures = dict(failures)
        self.results = dict(results)
        detail = "; ".join(
            f"{rid}: {err}" for rid, err in sorted(self.failures.items())
        )
        super().__init__(
            f"{len(self.failures)} of {len(self.failures) + len(self.results)} "
            f"instruments failed: {detail}"
        )
