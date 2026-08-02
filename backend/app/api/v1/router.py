from fastapi import APIRouter
from app.api.v1.endpoints import (
    standards, documents, imports, audit, evidence, corrective_actions, readiness,
    dashboard, notifications, exports, pilot, deployment, operations, assurance, intelligence, governance, action_planning, committee_governance, institutional_pilot,
)

router = APIRouter()
router.include_router(standards.router, tags=["Standards Registry"])
router.include_router(documents.router, tags=["Master Document Register"])
router.include_router(imports.router, tags=["Import Center"])
router.include_router(evidence.router, tags=["Evidence Workflow"])
router.include_router(corrective_actions.router, tags=["Findings and CAPA"])
router.include_router(readiness.router, tags=["Readiness"])
router.include_router(dashboard.router, tags=["Dashboard and Worklists"])
router.include_router(notifications.router, tags=["Notifications"])
router.include_router(exports.router, tags=["Export Center"])
router.include_router(pilot.router, tags=["Pilot Control and UAT"])
router.include_router(deployment.router, tags=["Deployment Acceptance"])
router.include_router(operations.router, tags=["Production Operations and Cutover"])
router.include_router(assurance.router, tags=["Continuous Assurance and Cluster Rollout"])
router.include_router(intelligence.router, tags=["Risk Intelligence and Governed AI"])
router.include_router(governance.router, tags=["Production Governance and Evidence Integrity"])
router.include_router(action_planning.router, tags=["Intelligence to Action and Human Decision Governance"])
router.include_router(committee_governance.router, tags=["Institutional Committee Governance and Decision Analytics"])
router.include_router(institutional_pilot.router, tags=["Institutional Pilot Execution and Outcomes"])
router.include_router(audit.router, tags=["Audit"])
