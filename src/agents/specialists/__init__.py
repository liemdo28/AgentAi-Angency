"""src.agents.specialists package — all 11 department specialist agents."""
from src.agents.specialists.base import BaseSpecialist
from src.agents.specialists.strategy import StrategySpecialist
from src.agents.specialists.creative import CreativeSpecialist
from src.agents.specialists.media import MediaSpecialist
from src.agents.specialists.data import DataSpecialist
from src.agents.specialists.account import AccountSpecialist
from src.agents.specialists.tech import TechSpecialist
from src.agents.specialists.sales import SalesSpecialist
from src.agents.specialists.ops import OperationsSpecialist
from src.agents.specialists.finance import FinanceSpecialist
from src.agents.specialists.crm import CRMAutomationSpecialist
from src.agents.specialists.production import ProductionSpecialist

__all__ = [
    "BaseSpecialist",
    "StrategySpecialist",
    "CreativeSpecialist",
    "MediaSpecialist",
    "DataSpecialist",
    "AccountSpecialist",
    "TechSpecialist",
    "SalesSpecialist",
    "OperationsSpecialist",
    "FinanceSpecialist",
    "CRMAutomationSpecialist",
    "ProductionSpecialist",
]

# Map department key → specialist class
DEPARTMENT_SPECIALIST_MAP: dict[str, type[BaseSpecialist]] = {
    "strategy": StrategySpecialist,
    "creative": CreativeSpecialist,
    "media": MediaSpecialist,
    "data": DataSpecialist,
    "account": AccountSpecialist,
    "tech": TechSpecialist,
    "sales": SalesSpecialist,
    "operations": OperationsSpecialist,
    "finance": FinanceSpecialist,
    "crm_automation": CRMAutomationSpecialist,
    "production": ProductionSpecialist,
}


def run_specialist(state: dict) -> dict:
    """
    Dispatcher — picks the correct specialist based on state['to_department']
    and runs it. Returns updates to merge into state.
    """
    from src.agents.state import AgenticState

    to_dept = state.get("to_department", "")
    specialist_cls = DEPARTMENT_SPECIALIST_MAP.get(to_dept)

    if specialist_cls is None:
        return {
            **state,
            "errors": [
                *state.get("errors", []),
                f"No specialist found for department: {to_dept}",
            ],
        }

    specialist = specialist_cls()
    return specialist.generate(state)
