# Exceptions

The errors `quelware-client` raises. Each of them derives from
`QuelwareClientError`.

An error that a unit reports while it runs an instrument comes as it is: as a
`grpclib.GRPCError` from `wait_for_result()`, and in `RunFailedError.failures`
from `wait_for_results()`. See [Triggering](../../concepts/triggering.md).

## Errors of a run

::: quelware_client.core.exceptions.RunFailedError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.NotTriggeredError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.UnitBusyError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.InitializeFailedError
    options:
      heading_level: 3

## Other errors

::: quelware_client.core.exceptions.QuelwareClientError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.ServiceUnavailableError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.ResourceNotFoundError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.LockConflictError
    options:
      heading_level: 3

::: quelware_client.core.exceptions.InvalidUnitStatusError
    options:
      heading_level: 3
