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


class InitializeFailedError(QuelwareClientError):
    """Raised when the initialize of some units failed.

    ``failures`` holds the error of each unit that failed, by its label. The
    other units were initialized.
    """

    def __init__(self, failures: Mapping[UnitLabel, BaseException], units: int):
        self.failures = dict(failures)
        detail = "; ".join(f"{u}: {e}" for u, e in sorted(self.failures.items()))
        super().__init__(
            f"initialize failed on {len(self.failures)} of {units} units: {detail}"
        )


class NotTriggeredError(_ErrorWithResourceIdsMixin, QuelwareClientError):
    """Raised when waiting for an instrument that was not triggered.

    Within a session, each unit has at most one run. A new trigger on the unit
    replaces it, and initializing an instrument on the unit clears it. So only
    the instruments in the last trigger on each unit can be waited for.
    """

    DEFAULT_MESSAGE = "The instruments were not in the last trigger on their unit."


class UnitBusyError(_ErrorWithUnitLabelsMixin, QuelwareClientError):
    """Raised when a trigger or initialize of the same session is already
    running on the unit."""

    DEFAULT_MESSAGE = (
        "A trigger or initialize of this session is already running on the unit."
    )
