from datetime import datetime

from pydantic import BaseModel


class InfraSummaryOut(BaseModel):
    configured: bool
    asgName: str = ""
    inServiceCount: int = 0
    targetGroupName: str = ""
    healthyTargetCount: int = 0
    totalTargetCount: int = 0
    albName: str = ""
    albRequestCountPerMin: int = 0
    albLatencyMs: float = 0


class TargetHealthItemOut(BaseModel):
    instanceId: str
    state: str
    port: int


class ScalingPolicyOut(BaseModel):
    configured: bool
    policyType: str | None = None
    metric: str | None = None
    targetValue: float | None = None
    minSize: int = 0
    desiredCapacity: int = 0
    maxSize: int = 0
    cooldownSec: int | None = None


class InfraStatusOut(BaseModel):
    summary: InfraSummaryOut
    targetHealth: list[TargetHealthItemOut]
    scalingPolicy: ScalingPolicyOut


class InstanceDetailOut(BaseModel):
    instanceId: str
    az: str
    instanceType: str
    launchedAt: str
    state: str
    cpuPercent: float
    colorIndex: int


class CpuSeriesPointOut(BaseModel):
    time: str
    cpuPercent: float


class InfraMetricsOut(BaseModel):
    instances: list[InstanceDetailOut]
    cpuSeries: list[dict]


class ActivityItemOut(BaseModel):
    id: str
    time: str
    status: str
    description: str
    cause: str = ""
