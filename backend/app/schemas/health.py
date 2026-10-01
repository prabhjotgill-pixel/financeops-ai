from typing import Literal

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: Literal["alive", "ready", "unavailable"]


class ServiceInfo(BaseModel):
    name: str
    environment: str
