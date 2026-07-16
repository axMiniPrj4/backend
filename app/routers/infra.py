"""인프라 검증 대시보드 (모니터링 전용, SYSTEM_ADMIN). ASG/ALB/CloudWatch를 boto3로 조회."""
from fastapi import APIRouter, Depends

from app.core.deps import require_admin
from app.models.user import User
from app.schemas.infra import (
    ActivityItemOut,
    InfraMetricsOut,
    InfraStatusOut,
    InfraSummaryOut,
    InstanceDetailOut,
    ScalingPolicyOut,
    TargetHealthItemOut,
)
from app.services import infra_aws

router = APIRouter(prefix="/api/internal/infra", tags=["Infra"])


@router.get("/status", response_model=InfraStatusOut)
def get_status(_: User = Depends(require_admin)):
    if not infra_aws.is_configured():
        return InfraStatusOut(
            summary=InfraSummaryOut(configured=False),
            targetHealth=[],
            scalingPolicy=ScalingPolicyOut(configured=False),
        )

    asg = infra_aws.safe_call(infra_aws.get_asg, None)
    target_health = infra_aws.safe_call(infra_aws.get_target_health, [])
    policies = infra_aws.safe_call(infra_aws.get_scaling_policies, [])
    req_per_min, latency_ms = infra_aws.safe_call(infra_aws.get_alb_metrics_per_min, (0, 0.0))

    in_service_count = sum(1 for i in (asg or {}).get("Instances", []) if i.get("LifecycleState") == "InService")
    healthy_count = sum(1 for t in target_health if t.get("TargetHealth", {}).get("State") == "healthy")

    target_group_name = infra_aws.settings.infra_target_group_arn.split("/")[-2] if infra_aws.settings.infra_target_group_arn else ""

    summary = InfraSummaryOut(
        configured=True,
        asgName=infra_aws.settings.infra_asg_name,
        inServiceCount=in_service_count,
        targetGroupName=target_group_name,
        healthyTargetCount=healthy_count,
        totalTargetCount=len(target_health),
        albName=infra_aws.settings.infra_alb_name,
        albRequestCountPerMin=req_per_min,
        albLatencyMs=latency_ms,
    )

    health_items = [
        TargetHealthItemOut(
            instanceId=t["Target"]["Id"],
            state=t.get("TargetHealth", {}).get("State", "unknown"),
            port=t["Target"].get("Port", 0),
        )
        for t in target_health
    ]

    if policies:
        p = policies[0]
        ttc = p.get("TargetTrackingConfiguration", {})
        metric_spec = ttc.get("PredefinedMetricSpecification", {})
        scaling_policy = ScalingPolicyOut(
            configured=True,
            policyType=p.get("PolicyType"),
            metric=metric_spec.get("PredefinedMetricType"),
            targetValue=ttc.get("TargetValue"),
            minSize=(asg or {}).get("MinSize", 0),
            desiredCapacity=(asg or {}).get("DesiredCapacity", 0),
            maxSize=(asg or {}).get("MaxSize", 0),
            cooldownSec=p.get("Cooldown"),
        )
    else:
        scaling_policy = ScalingPolicyOut(
            configured=False,
            minSize=(asg or {}).get("MinSize", 0),
            desiredCapacity=(asg or {}).get("DesiredCapacity", 0),
            maxSize=(asg or {}).get("MaxSize", 0),
        )

    return InfraStatusOut(summary=summary, targetHealth=health_items, scalingPolicy=scaling_policy)


@router.get("/metrics", response_model=InfraMetricsOut)
def get_metrics(_: User = Depends(require_admin)):
    if not infra_aws.is_configured():
        return InfraMetricsOut(instances=[], cpuSeries=[])

    asg = infra_aws.safe_call(infra_aws.get_asg, None)
    asg_instances = (asg or {}).get("Instances", [])
    instance_ids = [i["InstanceId"] for i in asg_instances]
    launch_times = infra_aws.safe_call(lambda: infra_aws.get_instance_launch_times(instance_ids), {})

    instances = []
    cpu_series_by_instance = {}
    for inst in asg_instances:
        instance_id = inst["InstanceId"]
        cpu_percent = infra_aws.safe_call(lambda iid=instance_id: infra_aws.get_instance_cpu_latest(iid), 0.0)
        launch_time = launch_times.get(instance_id)
        instances.append(
            InstanceDetailOut(
                instanceId=instance_id,
                az=inst.get("AvailabilityZone", ""),
                instanceType=inst.get("InstanceType", ""),
                launchedAt=launch_time.strftime("%Y-%m-%d %H:%M") if launch_time else "",
                state=inst.get("LifecycleState", "unknown"),
                cpuPercent=cpu_percent,
                colorIndex=infra_aws.instance_color_index(instance_id),
            )
        )
        cpu_series_by_instance[instance_id] = infra_aws.safe_call(
            lambda iid=instance_id: infra_aws.get_instance_cpu_series(iid), []
        )

    merged_by_time: dict[str, dict] = {}
    for instance_id, series in cpu_series_by_instance.items():
        for point in series:
            row = merged_by_time.setdefault(point["time"], {"time": point["time"]})
            row[instance_id] = point["cpuPercent"]
    cpu_series = [merged_by_time[t] for t in sorted(merged_by_time.keys())]

    return InfraMetricsOut(instances=instances, cpuSeries=cpu_series)


@router.get("/activities", response_model=list[ActivityItemOut])
def get_activities(_: User = Depends(require_admin)):
    if not infra_aws.is_configured():
        return []

    activities = infra_aws.safe_call(infra_aws.get_activities, [])
    return [
        ActivityItemOut(
            id=a["ActivityId"],
            time=a["StartTime"].strftime("%Y-%m-%d %H:%M"),
            status=a.get("StatusCode", "Unknown"),
            description=a.get("Description", ""),
            cause=a.get("Cause", ""),
        )
        for a in activities
    ]
