# how long a call waits for its reply, so that a unit that is gone fails it
# instead of holding it until a proxy gives up
CALL_TIMEOUT_SEC = 30.0
HEALTH_CHECK_TIMEOUT_SEC = 10.0
# a fetch waits on the unit until the run ends; one past this is made again
FETCH_TIMEOUT_SEC = 60.0
CONFIGURE_UNIT_TIMEOUT_SEC = 120.0

__all__ = [
    "CALL_TIMEOUT_SEC",
    "CONFIGURE_UNIT_TIMEOUT_SEC",
    "FETCH_TIMEOUT_SEC",
    "HEALTH_CHECK_TIMEOUT_SEC",
]
