from app.schemas.plan import PlanContext, RefinedPlan
from app.schemas.pool import PoolResponse

POOL_REGISTRY: dict[str, PoolResponse] = {}
PLAN_REGISTRY: dict[str, RefinedPlan] = {}
PLAN_CONTEXT_REGISTRY: dict[str, PlanContext] = {}
