import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from grpclib.exceptions import StreamTerminatedError

logger = logging.getLogger(__name__)


_T = TypeVar("_T")


# Marker substrings in StreamTerminatedError messages that indicate the request
# was definitely not processed by the server, so retry is safe for any RPC.
_DEFINITELY_NOT_PROCESSED_MARKERS = ("REFUSED_STREAM",)

# Marker substrings that suggest the request was likely not processed, but may
# have been. Retry is safe only for idempotent RPCs.
_PROBABLY_NOT_PROCESSED_MARKERS = (
    "Connection lost",
    "Connection closed",
    "REFUSED_STREAM",
    "NO_ERROR",
)


def _is_retryable(exc: StreamTerminatedError, idempotent: bool) -> bool:
    msg = str(exc)
    markers = (
        _PROBABLY_NOT_PROCESSED_MARKERS
        if idempotent
        else _DEFINITELY_NOT_PROCESSED_MARKERS
    )
    return any(m in msg for m in markers)


async def call_with_retry(
    call: Callable[[], Awaitable[_T]],
    *,
    idempotent: bool = False,
    max_attempts: int = 5,
    retry_delay_sec: float = 0.1,
) -> _T:
    """Call an awaitable, retrying transient HTTP/2 stream errors.

    Retries `StreamTerminatedError` whose message indicates the server did not
    process the request. For non-idempotent RPCs (`idempotent=False`), only the
    strictly-safe cases (REFUSED_STREAM) are retried; for idempotent ones,
    connection-level resets are also retried. A short delay between attempts
    gives grpclib's Channel time to re-establish the underlying connection.
    """
    last_exc: StreamTerminatedError | None = None
    for attempt in range(max_attempts):
        try:
            return await call()
        except StreamTerminatedError as e:
            last_exc = e
            if attempt + 1 >= max_attempts or not _is_retryable(e, idempotent):
                raise
            logger.info(
                "retrying after stream termination: %s (attempt %d, idempotent=%s)",
                repr(e),
                attempt + 1,
                idempotent,
            )
            await asyncio.sleep(retry_delay_sec)
    assert last_exc is not None  # unreachable
    raise last_exc


__all__ = ["call_with_retry"]
