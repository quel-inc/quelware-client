import quelware_core.pb.quelware.resource.v1 as pb_res
from quelware_core.entities.resource import ResourceId, ResourceInfo, ResourceType
from quelware_core.pb.quelware.resource.v1 import Resource

_RESOURCE_TYPE_TO_PB = {
    ResourceType.PORT: pb_res.ResourceType.PORT,
    ResourceType.INSTRUMENT: pb_res.ResourceType.INSTRUMENT,
}

_RESOURCE_TYPE_FROM_PB = {v: k for k, v in _RESOURCE_TYPE_TO_PB.items()}


def resource_info_to_pb(val: ResourceInfo) -> Resource:
    return Resource(id=val.id, type=_RESOURCE_TYPE_TO_PB[val.type])


def resource_info_from_pb(pb: Resource) -> ResourceInfo:
    return ResourceInfo(id=ResourceId(pb.id), type=_RESOURCE_TYPE_FROM_PB[pb.type])
