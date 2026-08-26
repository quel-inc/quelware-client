import betterproto2

import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.result import ResultContainer
from quelware_core.pb_converter.directive import (
    iq_waveform_from_dense_pb,
    iq_waveform_from_pb,
    iq_waveform_to_dense_pb,
)


def _complex_to_pb_point(val: complex) -> pb_models.IqPoint:
    return pb_models.IqPoint(i=val.real, q=val.imag)


def _pb_point_to_complex(pb: pb_models.IqPoint) -> complex:
    return complex(pb.i, pb.q)


def result_container_to_pb(entity: ResultContainer) -> pb_models.ResultContainer:
    pb = pb_models.ResultContainer()

    for name, waves in entity.iq_waveform_result.items():
        pb.iq_result[name] = pb_models.IqResult(
            dense_waveforms=pb_models.DenseWaveformList(
                waveforms=[iq_waveform_to_dense_pb(w) for w in waves]
            )
        )

    for name, points in entity.iq_point_result.items():
        pb.iq_result[name] = pb_models.IqResult(
            iq_points=pb_models.IqPointList(
                iq_points=[_complex_to_pb_point(p) for p in points]
            )
        )

    for name, int_data in entity.integer_result.items():
        pb.integer_result[name] = pb_models.IntegerResult(integers=int_data)

    return pb


def result_container_from_pb(pb: pb_models.ResultContainer) -> ResultContainer:
    entity = ResultContainer()

    for name, iq_res_pb in pb.iq_result.items():
        _, val = betterproto2.which_one_of(iq_res_pb, "result")
        match val:
            case pb_models.DenseWaveformList():
                entity.iq_waveform_result[name] = [
                    iq_waveform_from_dense_pb(wf) for wf in val.waveforms
                ]
            case pb_models.WaveformList():
                entity.iq_waveform_result[name] = [
                    iq_waveform_from_pb(pb_models.Waveform(sampled=wf))
                    for wf in val.waveforms
                ]
            case pb_models.IqPointList():
                entity.iq_point_result[name] = [
                    _pb_point_to_complex(pt) for pt in val.iq_points
                ]

    for name, int_res_pb in pb.integer_result.items():
        entity.integer_result[name] = list(int_res_pb.integers)

    return entity
