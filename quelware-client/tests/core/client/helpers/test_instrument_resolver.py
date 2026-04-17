import pytest
from quelware_core.entities.instrument import (
    FixedTimelineConfig,
    FixedTimelineProfile,
    InstrumentDefinition,
    InstrumentInfo,
    InstrumentMode,
    InstrumentRole,
)
from quelware_core.entities.resource import ResourceId

from quelware_client.client.helpers.instrument_resolver import InstrumentResolver

_DUMMY_PROFILE = FixedTimelineProfile(frequency_range_min=0.0, frequency_range_max=1.0)
_DUMMY_CONFIG = FixedTimelineConfig(
    sampling_period_fs=1, bitdepth=16, timeline_step_samples=1, samples_per_tick=1
)


def _make_inst_info(inst_id: str, alias: str) -> InstrumentInfo:
    return InstrumentInfo(
        id=ResourceId(inst_id),
        port_id=ResourceId("dummy:port"),
        definition=InstrumentDefinition(
            alias=alias,
            mode=InstrumentMode.FIXED_TIMELINE,
            role=InstrumentRole.TRANSCEIVER,
            profile=_DUMMY_PROFILE,
        ),
        config=_DUMMY_CONFIG,
    )


class TestInstrumentResolver:
    def _build_resolver(self, inst_infos: list[InstrumentInfo]) -> InstrumentResolver:
        resolver = InstrumentResolver()
        new_id_to_inst_info = {}
        new_short: dict[str, dict[str, ResourceId]] = {}
        for inst_info in inst_infos:
            full_alias = inst_info.definition.alias
            new_id_to_inst_info[inst_info.id] = inst_info
            unit, _, short = full_alias.partition(":")
            if short:
                new_short.setdefault(short, {})[unit] = inst_info.id
            else:
                new_short.setdefault(full_alias, {})[""] = inst_info.id
        resolver._id_to_inst_info = new_id_to_inst_info
        resolver._short_alias_to_ids = new_short
        return resolver

    def test_find_by_short_alias_unique(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
            ]
        )
        info = resolver.find_inst_info_by_alias("readout")
        assert info.id == ResourceId("unit-a:inst1")

    def test_find_by_short_alias_with_unit(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
                _make_inst_info("unit-b:inst2", "unit-b:readout"),
            ]
        )
        info = resolver.find_inst_info_by_alias("readout", unit="unit-b")
        assert info.id == ResourceId("unit-b:inst2")

    def test_find_by_short_alias_ambiguous_raises(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
                _make_inst_info("unit-b:inst2", "unit-b:readout"),
            ]
        )
        with pytest.raises(ValueError, match="Multiple instruments"):
            resolver.find_inst_info_by_alias("readout")

    def test_find_not_found_raises(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
            ]
        )
        with pytest.raises(ValueError, match="not found"):
            resolver.find_inst_info_by_alias("nonexistent")

    def test_find_by_unit_not_found_raises(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
            ]
        )
        with pytest.raises(ValueError, match="not found in unit"):
            resolver.find_inst_info_by_alias("readout", unit="unit-c")

    def test_find_by_id(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
            ]
        )
        info = resolver.find_inst_info_by_id(ResourceId("unit-a:inst1"))
        assert info.definition.alias == "unit-a:readout"

    def test_resolve_multiple(self):
        resolver = self._build_resolver(
            [
                _make_inst_info("unit-a:inst1", "unit-a:readout"),
                _make_inst_info("unit-a:inst2", "unit-a:control"),
            ]
        )
        ids = resolver.resolve(["readout", "control"], unit="unit-a")
        assert ids == [ResourceId("unit-a:inst1"), ResourceId("unit-a:inst2")]
