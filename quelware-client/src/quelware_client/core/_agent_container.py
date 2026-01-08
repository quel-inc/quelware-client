import logging

from quelware_core.entities.unit import UnitLabel

from quelware_client.core.interfaces.instrument_agent import InstrumentAgent
from quelware_client.core.interfaces.resource_agent import ResourceAgent
from quelware_client.core.interfaces.session_agent import SessionAgent
from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)

logger = logging.getLogger(__name__)


class AgentContainer:
    def __init__(self):
        self._session: SessionAgent | None = None
        self._conf: SystemConfigurationAgent | None = None
        self._rsrc: dict[UnitLabel, ResourceAgent] = {}
        self._inst: dict[UnitLabel, InstrumentAgent] = {}

    def update_resource_agent(self, unit_label: UnitLabel, agent: ResourceAgent | None):
        if agent is None:
            if unit_label in self._rsrc:
                self._rsrc[unit_label]
            else:
                logger.warning(f"ResourceAgent for '{unit_label}' not found. Continue.")
        else:
            self._rsrc[unit_label] = agent

    def update_instrument_agent(
        self, unit_label: UnitLabel, agent: InstrumentAgent | None
    ):
        if agent is None:
            if unit_label in self._rsrc:
                self._inst[unit_label]
            else:
                logger.warning(
                    f"InstrumentAgent for '{unit_label}' not found. Continue."
                )
        else:
            self._inst[unit_label] = agent

    @property
    def session(self) -> SessionAgent:
        if self._session is None:
            raise ValueError("SessionAgent not set.")
        return self._session

    @session.setter
    def session(self, val: SessionAgent):
        self._session = val

    @property
    def system_configuration(self) -> SystemConfigurationAgent:
        if self._conf is None:
            raise ValueError("ConfigurationAgent not set.")
        return self._conf

    @system_configuration.setter
    def system_configuration(self, val: SystemConfigurationAgent):
        self._conf = val

    def resource(self, unit_label: UnitLabel) -> ResourceAgent:
        if unit_label not in self._rsrc:
            raise ValueError(f"ResouceAgent for '{unit_label}' not set.")
        return self._rsrc[unit_label]

    def instrument(self, unit_label: UnitLabel) -> InstrumentAgent:
        if unit_label not in self._inst:
            raise ValueError(f"InstrumentAgent for '{unit_label}' not set.")
        return self._inst[unit_label]
