"""Pack a complex array into bytes of a given dtype, and unpack it."""

from collections.abc import Sequence

import numpy as np

import quelware_core.pb.quelware.models.v1 as pb_models

_COMPLEX128_LE = np.dtype("<c16")


def pack(
    values: np.ndarray | Sequence[complex],
) -> tuple[pb_models.DenseIqArrayDtype, int, bytes]:
    """Return the dtype, count and bytes of ``values`` as float64 (i, q) pairs."""
    arr = np.ascontiguousarray(values, dtype=_COMPLEX128_LE)
    return (
        pb_models.DenseIqArrayDtype.COMPLEX128_LE_INTERLEAVED,
        arr.size,
        arr.tobytes(),
    )


def unpack(dtype: pb_models.DenseIqArrayDtype, count: int, data: bytes) -> np.ndarray:
    """Return the ``count`` values in ``data``; ValueError if they do not fit."""
    match dtype:
        case pb_models.DenseIqArrayDtype.COMPLEX128_LE_INTERLEAVED:
            element = _COMPLEX128_LE
        case _:
            raise ValueError(f"unsupported dense dtype: {dtype!r}")
    expected_len = count * element.itemsize
    if len(data) != expected_len:
        raise ValueError(
            f"dense data length {len(data)} does not match count {count} "
            f"(expected {expected_len} bytes)"
        )
    # copy: frombuffer alone would return a read-only view of the pb bytes
    return np.frombuffer(data, dtype=element).copy()
