from collections import defaultdict
from collections.abc import Collection

from quelware_core.entities.resource import ResourceId, extract_unit_label
from quelware_core.entities.unit import UnitLabel


def create_unit_to_ids_map(
    instrument_ids: Collection[ResourceId],
) -> dict[UnitLabel, list[ResourceId]]:
    unit_to_ids_map = defaultdict(list)

    for rid in instrument_ids:
        label = extract_unit_label(rid)
        unit_to_ids_map[label].append(rid)

    return dict(unit_to_ids_map)
