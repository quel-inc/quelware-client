from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

type IqArray = npt.NDArray[np.complex128]
type IqPoint = complex


@dataclass
class IqWaveform:
    sampling_period_fs: int
    iq_array: IqArray


def iq_array_to_in_phase_list(array: IqArray):
    return list(array.real)


def iq_array_to_quadrature_phase_list(array: IqArray):
    return list(array.imag)


def iq_array_from_lists(
    in_phase_list: Sequence[float], quadrature_phase_list: Sequence[float]
):
    return np.array(in_phase_list, dtype=np.complex128) + 1j * np.array(
        quadrature_phase_list, dtype=np.complex128
    )


__all__ = [
    "IqArray",
    "IqPoint",
    "IqWaveform",
    "iq_array_from_lists",
    "iq_array_to_in_phase_list",
    "iq_array_to_quadrature_phase_list",
]
