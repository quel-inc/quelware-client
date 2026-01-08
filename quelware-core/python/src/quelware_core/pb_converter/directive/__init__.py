from typing import assert_never

import betterproto2

import quelware_core.pb.quelware.models.v1 as pb_models
from quelware_core.entities.directives import (
    CaptureWindow,
    Directive,
    FixedTimelineDirective,
    SetFixedTimeline,
    SetFrequency,
    SetPhaseOffset,
    SetTimingOffset,
    WaveformEvent,
)
from quelware_core.entities.waveform.sampled import (
    IqWaveform,
    iq_array_from_lists,
    iq_array_to_in_phase_list,
    iq_array_to_quadrature_phase_list,
)


def _waveform_to_pb(entity: IqWaveform) -> pb_models.Waveform:
    return pb_models.Waveform(
        sampled=pb_models.SampledWaveform(
            i_samples=iq_array_to_in_phase_list(entity.iq_array),
            q_samples=iq_array_to_quadrature_phase_list(entity.iq_array),
            sampling_period_fs=entity.sampling_period_fs,
        )
    )


def _waveform_from_pb(pb: pb_models.Waveform) -> IqWaveform:
    _, val = betterproto2.which_one_of(pb, "waveform")
    match val:
        case pb_models.SampledWaveform():
            return IqWaveform(
                sampling_period_fs=val.sampling_period_fs,
                iq_array=iq_array_from_lists(val.i_samples, val.q_samples),
            )
        case _:
            raise ValueError(f"Unsupported waveform type: {type(val)}")


def _waveform_event_to_pb(entity: WaveformEvent) -> pb_models.SetFixedTimelineDirectiveWaveformEvent:
    return pb_models.SetFixedTimelineDirectiveWaveformEvent(
        waveform_index=entity.waveform_index,
        start_offset_samples=entity.start_offset_samples,
        gain=entity.gain,
        phase_offset_deg=entity.phase_offset_deg,
    )


def _waveform_event_from_pb(pb: pb_models.SetFixedTimelineDirectiveWaveformEvent) -> WaveformEvent:
    return WaveformEvent(
        waveform_index=pb.waveform_index,
        start_offset_samples=pb.start_offset_samples,
        gain=pb.gain,
        phase_offset_deg=pb.phase_offset_deg,
    )

def _capture_window_to_pb(entity: CaptureWindow) -> pb_models.SetFixedTimelineDirectiveCaptureWindow:
    return pb_models.SetFixedTimelineDirectiveCaptureWindow(
        name=entity.name,
        start_offset_samples=entity.start_offset_samples,
        duration_samples=entity.length_samples,
    )


def _capture_window_from_pb(pb: pb_models.SetFixedTimelineDirectiveCaptureWindow) -> CaptureWindow:
    return CaptureWindow(
        name=pb.name,
        start_offset_samples=pb.start_offset_samples,
        length_samples=pb.duration_samples
    )

def directive_to_pb(entity: Directive) -> pb_models.Directive:
    match entity:
        case SetFrequency():
            ft_cmd = pb_models.FixedTimelineDirective(
                set_frequency=pb_models.SetFrequencyDirective(frequency=entity.hz)
            )
        case SetPhaseOffset():
            ft_cmd = pb_models.FixedTimelineDirective(
                set_phase_offset=pb_models.SetPhaseOffsetDirective(
                    phase_offset_rad=entity.radian
                )
            )
        case SetTimingOffset():
            ft_cmd = pb_models.FixedTimelineDirective(
                set_timing_offset=pb_models.SetTimingOffsetDirective(
                    offset_samples=entity.offset_samples
                )
            )
        case SetFixedTimeline():
            library_pb = [_waveform_to_pb(w) for w in entity.waveform_library]
            events_pb = [_waveform_event_to_pb(e) for e in entity.events]
            capture_windows_pb = [_capture_window_to_pb(e) for e in entity.capture_windows]
            length_pb = entity.length
            ft_cmd = pb_models.FixedTimelineDirective(
                set_timeline=pb_models.SetFixedTimelineDirective(
                    waveform_library=library_pb,
                    events=events_pb,
                    length_samples=length_pb,
                    capture_windows=capture_windows_pb
                )
            )
        case _:
            assert_never(entity)

    return pb_models.Directive(fixed_timeline_sampled_waveform=ft_cmd)


def directive_from_pb(pb: pb_models.Directive) -> Directive:
    _, command = betterproto2.which_one_of(pb, "command")

    match command:
        case pb_models.FixedTimelineDirective():
            return _fixed_timeline_directive_from_pb(command)
        case _:
            raise ValueError(f"Unsupported directive command: {type(command)}")


def _fixed_timeline_directive_from_pb(
    pb: pb_models.FixedTimelineDirective,
) -> FixedTimelineDirective:
    _, command = betterproto2.which_one_of(pb, "command")

    match command:
        case pb_models.SetFrequencyDirective():
            return SetFrequency(hz=command.frequency)
        case pb_models.SetPhaseOffsetDirective():
            return SetPhaseOffset(radian=command.phase_offset_rad)
        case pb_models.SetTimingOffsetDirective():
            return SetTimingOffset(offset_samples=command.offset_samples)
        case pb_models.SetFixedTimelineDirective():
            library = [_waveform_from_pb(w) for w in command.waveform_library]
            events = [_waveform_event_from_pb(e) for e in command.events]
            capture_windows = [_capture_window_from_pb(e) for e in command.capture_windows]
            length = command.length_samples
            return SetFixedTimeline(
                waveform_library=library, events=events, length=length, capture_windows=capture_windows
            )
        case _:
            # This handles cases defined in proto (e.g. SetCaptureDuration)
            # but not yet implemented in the Python entities.
            raise ValueError(f"Unsupported fixed timeline directive: {type(command)}")
