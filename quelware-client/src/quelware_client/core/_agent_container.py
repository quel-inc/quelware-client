import logging

from quelware_core.entities.unit import UnitLabel

from quelware_client.core.interfaces.diagnostics_agent import DiagnosticsAgent
from quelware_client.core.interfaces.health_agent import HealthAgent
from quelware_client.core.interfaces.instrument_agent import InstrumentAgent
from quelware_client.core.interfaces.resource_agent import ResourceAgent
from quelware_client.core.interfaces.session_agent import SessionAgent
from quelware_client.core.interfaces.system_configuration_agent import (
    SystemConfigurationAgent,
)
from quelware_client.core.interfaces.trigger_agent import TriggerAgent
from quelware_client.core.interfaces.worker_agent import WorkerAgent

logger = logging.getLogger(__name__)


class AgentContainer:
    def __init__(self):
        self._session: SessionAgent | None = None
        self._conf: SystemConfigurationAgent | None = None
        self._trigger: TriggerAgent | None = None
        self._health: dict[UnitLabel, HealthAgent] = {}
        self._rsrc: dict[UnitLabel, ResourceAgent] = {}
        self._inst: dict[UnitLabel, InstrumentAgent] = {}
        self._diag: dict[UnitLabel, DiagnosticsAgent] = {}
        self._worker: dict[UnitLabel, WorkerAgent] = {}

    def update_health_agent(self, unit_label: UnitLabel, agent: HealthAgent | None):
        if agent is None:
            if unit_label in self._health:
                self._health[unit_label]
            else:
                logger.warning(f"ResourceAgent for '{unit_label}' not found. Continue.")
        else:
            self._health[unit_label] = agent

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

    def update_diagnostics_agent(
        self, unit_label: UnitLabel, agent: DiagnosticsAgent | None
    ):
        if agent is None:
            if unit_label in self._diag:
                self._diag[unit_label]
            else:
                logger.warning(
                    f"DiagnosticsAgent for '{unit_label}' not found. Continue."
                )
        else:
            self._diag[unit_label] = agent

    def update_worker_agent(self, unit_label: UnitLabel, agent: WorkerAgent | None):
        if agent is None:
            if unit_label in self._worker:
                self._worker[unit_label]
            else:
                logger.warning(f"WorkerAgent for '{unit_label}' not found. Continue.")
        else:
            self._worker[unit_label] = agent

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

    @property
    def trigger(self) -> TriggerAgent:
        if self._trigger is None:
            raise ValueError("TriggerAgent not set.")
        return self._trigger

    @trigger.setter
    def trigger(self, val: TriggerAgent):
        self._trigger = val

    def health(self, unit_label: UnitLabel) -> HealthAgent:
        if unit_label not in self._health:
            raise ValueError(f"HealthAgent for '{unit_label}' not set.")
        return self._health[unit_label]

    def resource(self, unit_label: UnitLabel) -> ResourceAgent:
        if unit_label not in self._rsrc:
            raise ValueError(f"ResouceAgent for '{unit_label}' not set.")
        return self._rsrc[unit_label]

    def instrument(self, unit_label: UnitLabel) -> InstrumentAgent:
        if unit_label not in self._inst:
            raise ValueError(f"InstrumentAgent for '{unit_label}' not set.")
        return self._inst[unit_label]

    def diagnostics(self, unit_label: UnitLabel) -> DiagnosticsAgent:
        if unit_label not in self._diag:
            raise ValueError(f"DiagnosticsAgent for '{unit_label}' not set.")
        return self._diag[unit_label]

    def worker(self, unit_label: UnitLabel) -> WorkerAgent:
        if unit_label not in self._worker:
            raise ValueError(f"WorkerAgent for '{unit_label}' not set.")
        return self._worker[unit_label]
