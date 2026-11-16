"""Names a server lists in ``VersionInfo.features``, one per newer form it accepts."""

from collections.abc import Iterable
from typing import Literal, get_args

Feature = Literal[
    # waveforms as Waveform.dense, a DenseIqArray
    "dense_waveform",
]

KNOWN: frozenset[Feature] = frozenset(get_args(Feature))


def known(names: Iterable[str]) -> frozenset[Feature]:
    """The names this package knows, of those a server listed."""
    listed = set(names)
    return frozenset(name for name in KNOWN if name in listed)
