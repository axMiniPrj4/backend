"""인프라 검증 대시보드용 AWS 조회 (읽기 전용, boto3는 EC2 IAM Role 자격증명 사용)."""
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

_INSTANCE_COLORS = 6


def is_configured() -> bool:
    return bool(settings.aws_region and settings.infra_asg_name and settings.infra_alb_name and settings.infra_target_group_arn)


def _session():
    return boto3.session.Session(region_name=settings.aws_region)


def _asg_client():
    return _session().client("autoscaling")


def _elbv2_client():
    return _session().client("elbv2")


def _ec2_client():
    return _session().client("ec2")


def _cloudwatch_client():
    return _session().client("cloudwatch")


def get_asg():
    resp = _asg_client().describe_auto_scaling_groups(AutoScalingGroupNames=[settings.infra_asg_name])
    groups = resp.get("AutoScalingGroups", [])
    return groups[0] if groups else None


def get_scaling_policies():
    resp = _asg_client().describe_policies(AutoScalingGroupName=settings.infra_asg_name)
    return resp.get("ScalingPolicies", [])


def get_target_health():
    resp = _elbv2_client().describe_target_health(TargetGroupArn=settings.infra_target_group_arn)
    return resp.get("TargetHealthDescriptions", [])


def get_load_balancer():
    resp = _elbv2_client().describe_load_balancers(Names=[settings.infra_alb_name])
    lbs = resp.get("LoadBalancers", [])
    return lbs[0] if lbs else None


def get_activities(max_items: int = 20):
    resp = _asg_client().describe_scaling_activities(AutoScalingGroupName=settings.infra_asg_name, MaxRecords=max_items)
    return resp.get("Activities", [])


def get_instance_launch_times(instance_ids: list[str]) -> dict[str, datetime]:
    if not instance_ids:
        return {}
    resp = _ec2_client().describe_instances(InstanceIds=instance_ids)
    out = {}
    for reservation in resp.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            out[inst["InstanceId"]] = inst.get("LaunchTime")
    return out


def _metric_avg(client, namespace, metric_name, dimensions, start, end, period=60):
    resp = client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=start,
        EndTime=end,
        Period=period,
        Statistics=["Average"],
    )
    points = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
    return points


def get_instance_cpu_latest(instance_id: str) -> float:
    cw = _cloudwatch_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=5)
    points = _metric_avg(cw, "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": instance_id}], start, end)
    if not points:
        return 0.0
    return round(points[-1]["Average"], 1)


def get_instance_cpu_series(instance_id: str, minutes: int = 15) -> list[dict]:
    cw = _cloudwatch_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    points = _metric_avg(cw, "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": instance_id}], start, end, period=60)
    return [{"time": p["Timestamp"].strftime("%H:%M"), "cpuPercent": round(p["Average"], 1)} for p in points]


def get_alb_metrics_per_min() -> tuple[int, float]:
    cw = _cloudwatch_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=5)
    lb = get_load_balancer()
    if not lb:
        return 0, 0.0
    lb_arn = lb["LoadBalancerArn"]
    lb_suffix = "/".join(lb_arn.split(":")[-1].split("/")[1:])
    dims = [{"Name": "LoadBalancer", "Value": lb_suffix}]
    req_points = _metric_avg(cw, "AWS/ApplicationELB", "RequestCount", dims, start, end, period=60)
    latency_points = _metric_avg(cw, "AWS/ApplicationELB", "TargetResponseTime", dims, start, end, period=60)
    req_per_min = round(req_points[-1]["Average"]) if req_points else 0
    latency_ms = round(latency_points[-1]["Average"] * 1000) if latency_points else 0
    return req_per_min, latency_ms


def instance_color_index(instance_id: str) -> int:
    return abs(hash(instance_id)) % _INSTANCE_COLORS


def safe_call(fn, default):
    try:
        return fn()
    except (BotoCoreError, ClientError):
        return default
