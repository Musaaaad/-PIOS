from __future__ import annotations
import hashlib, json
from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.entities import (
    Organization, Site, MeasurableElement, Finding, ReadinessSnapshot, ReadinessSnapshotItem,
    AssuranceProgram, AssuranceControl, DataQualityRun, DataQualityIssue,
    RiskAssessmentRun, RiskAssessmentItem, AiGovernancePolicy, AiRecommendation,
    PortfolioSnapshot, PortfolioSiteMetric,
)

OPEN_FINDING_STATUSES = ["Open","Acknowledged","CAPAOpen","VerificationPending","Reopened"]
PROHIBITED_ACTIONS = ["ApproveCompliance","ApproveNotApplicable","SignEvidence","CloseCriticalCAPA","ChangeKPI","PublishEvidenceReady"]
ALLOWED_USE_CASES = ["RiskSummarization","EvidenceGapSuggestion","CAPAPlanningSupport","ExecutiveNarrative","TrendExplanation"]

def utcnow(): return datetime.now(timezone.utc)

def ensure_ai_policy(db: Session, organization_id, actor_id=None):
    row = db.scalar(select(AiGovernancePolicy).where(AiGovernancePolicy.organization_id==organization_id, AiGovernancePolicy.code=="PIOS-AI-GOV-001"))
    if row: return row, False
    row = AiGovernancePolicy(organization_id=organization_id, code="PIOS-AI-GOV-001", name="PIOS Human-Governed AI Policy", status="Effective", allowed_use_cases=ALLOWED_USE_CASES, prohibited_actions=PROHIBITED_ACTIONS, human_review_required=True, model_registry={"rules-engine-v1":{"type":"deterministic","external_data":False,"auto_execute":False}}, approved_by=actor_id, approved_at=utcnow())
    db.add(row); db.flush(); return row, True

def _band(score):
    return "Critical" if score>=75 else "High" if score>=50 else "Moderate" if score>=25 else "Low"

def calculate_risk(db: Session, site_id, code: str, period_label: str, actor_id=None):
    existing = db.scalar(select(RiskAssessmentRun).where(RiskAssessmentRun.site_id==site_id, RiskAssessmentRun.code==code))
    if existing: return existing
    mes = list(db.scalars(select(MeasurableElement).where(MeasurableElement.active.is_(True)).order_by(MeasurableElement.me_id)).all())
    latest_readiness = db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id==site_id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
    readiness = {}
    if latest_readiness:
        readiness = {x.measurable_element_id:x for x in db.scalars(select(ReadinessSnapshotItem).where(ReadinessSnapshotItem.snapshot_id==latest_readiness.id)).all()}
    findings = defaultdict(list)
    for f in db.scalars(select(Finding).where(Finding.site_id==site_id, Finding.status.in_(OPEN_FINDING_STATUSES))).all(): findings[f.measurable_element_id].append(f)
    program_ids = list(db.scalars(select(AssuranceProgram.id).where(AssuranceProgram.site_id==site_id)).all())
    overdue_me = set()
    if program_ids:
        now=utcnow()
        overdue_me=set(db.scalars(select(AssuranceControl.measurable_element_id).where(AssuranceControl.program_id.in_(program_ids), AssuranceControl.active.is_(True), AssuranceControl.next_due_at.is_not(None), AssuranceControl.next_due_at<now)).all())
    latest_dq = db.scalar(select(DataQualityRun).where(DataQualityRun.site_id==site_id).order_by(DataQualityRun.created_at.desc()).limit(1))
    dq_me=set()
    if latest_dq:
        for issue in db.scalars(select(DataQualityIssue).where(DataQualityIssue.run_id==latest_dq.id, DataQualityIssue.status.not_in(["Closed","Resolved"]))).all():
            if issue.entity_type=="MeasurableElement":
                me=db.scalar(select(MeasurableElement).where(MeasurableElement.me_id==issue.entity_id));
                if me: dq_me.add(me.id)
    previous = db.scalar(select(RiskAssessmentRun).where(RiskAssessmentRun.site_id==site_id).order_by(RiskAssessmentRun.generated_at.desc()).limit(1))
    previous_scores={}
    if previous:
        previous_scores={x.measurable_element_id:x.risk_score for x in db.scalars(select(RiskAssessmentItem).where(RiskAssessmentItem.run_id==previous.id)).all()}
    run=RiskAssessmentRun(site_id=site_id,code=code,period_label=period_label,status="Completed",methodology_version="1.0",created_by=actor_id,summary_json={})
    db.add(run); db.flush()
    bands=defaultdict(int); scores=[]
    for me in mes:
        score=0; signals=[]
        if me.esr: score+=20; signals.append({"code":"ESR","weight":20})
        open_fs=findings.get(me.id,[])
        sev={f.severity for f in open_fs}
        if "P0" in sev: score+=45; signals.append({"code":"OPEN_P0","weight":45})
        elif "P1" in sev: score+=30; signals.append({"code":"OPEN_P1","weight":30})
        elif "P2" in sev: score+=15; signals.append({"code":"OPEN_P2","weight":15})
        if len(open_fs)>1: extra=min(10,(len(open_fs)-1)*3); score+=extra; signals.append({"code":"MULTIPLE_FINDINGS","weight":extra})
        ri=readiness.get(me.id)
        state=ri.readiness_state if ri else "Missing"
        state_weight={"CriticalBlocked":30,"Blocked":20,"Missing":20,"Partial":10,"EvidenceSufficient":0,"NotApplicable":0}.get(state,10)
        if state_weight: score+=state_weight; signals.append({"code":f"READINESS_{state.upper()}","weight":state_weight})
        if me.id in overdue_me: score+=20; signals.append({"code":"OVERDUE_CONTROL","weight":20})
        if me.id in dq_me: score+=10; signals.append({"code":"DATA_QUALITY_ISSUE","weight":10})
        score=min(100,score); band=_band(score); bands[band]+=1; scores.append(score)
        prior=previous_scores.get(me.id); trend="Unknown" if prior is None else "Rising" if score>prior+5 else "Falling" if score<prior-5 else "Stable"
        rationale=", ".join(x["code"] for x in signals) if signals else "No active risk signal detected by the deterministic rules engine."
        db.add(RiskAssessmentItem(run_id=run.id, measurable_element_id=me.id, risk_score=score, risk_band=band, trend=trend, signals=signals, rationale=rationale, owner_role_code=me.owner_role_code, human_status="Unreviewed"))
    run.summary_json={"total_me":len(mes),"average_risk":round(sum(scores)/len(scores),1) if scores else 0,"max_risk":max(scores) if scores else 0,"bands":dict(bands),"methodology":"Deterministic signals; not a compliance score or clinical prediction"}
    db.flush(); return run

def generate_recommendations(db: Session, run: RiskAssessmentRun, site_id, limit: int, actor_id=None):
    items=list(db.scalars(select(RiskAssessmentItem).where(RiskAssessmentItem.run_id==run.id).order_by(RiskAssessmentItem.risk_score.desc()).limit(limit)).all())
    created=[]
    for item in items:
        existing=db.scalar(select(AiRecommendation).where(AiRecommendation.risk_run_id==run.id, AiRecommendation.measurable_element_id==item.measurable_element_id))
        if existing: continue
        me=db.get(MeasurableElement,item.measurable_element_id)
        context={"me_id":me.me_id,"risk_score":item.risk_score,"risk_band":item.risk_band,"signals":item.signals,"eoc":me.eoc}
        prompt_hash=hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()
        action="Prioritize human review, verify the indicated signals, collect evidence matching EOC, and open a governed Finding/CAPA only after reviewer confirmation."
        row=AiRecommendation(site_id=site_id,risk_run_id=run.id,measurable_element_id=me.id,recommendation_type="RiskReduction",title=f"Human review recommended for {me.me_id}",recommendation_text=action,rationale=item.rationale,confidence=round(min(.95,.55+item.risk_score/250),2),status="NeedsHumanReview",source_context=context,prompt_hash=prompt_hash,model_id="rules-engine-v1",guardrail_result={"passed":True,"human_review_required":True,"auto_execute":False,"prohibited_actions":PROHIBITED_ACTIONS},created_by=actor_id)
        db.add(row); created.append(row)
    db.flush(); return created

def review_recommendation(row: AiRecommendation, decision: str, comment: str, actor_id=None):
    if row.status not in {"NeedsHumanReview","NeedsRevision"}: raise HTTPException(409,"Recommendation is not reviewable")
    row.decision=decision; row.decision_comment=comment; row.reviewed_by=actor_id; row.reviewed_at=utcnow()
    row.status={"ApprovedForPlanning":"HumanApprovedForPlanning","Rejected":"Rejected","NeedsRevision":"NeedsRevision"}[decision]
    return row

def create_portfolio_snapshot(db: Session, organization_id, code: str, period_label: str, actor_id=None):
    existing=db.scalar(select(PortfolioSnapshot).where(PortfolioSnapshot.organization_id==organization_id, PortfolioSnapshot.code==code))
    if existing: return existing
    snap=PortfolioSnapshot(organization_id=organization_id,code=code,period_label=period_label,methodology_version="1.0",summary_json={},created_by=actor_id)
    db.add(snap); db.flush(); metrics=[]
    sites=list(db.scalars(select(Site).where(Site.organization_id==organization_id,Site.active.is_(True)).order_by(Site.code)).all())
    for site in sites:
        rdy=db.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.site_id==site.id).order_by(ReadinessSnapshot.captured_at.desc()).limit(1))
        risk=db.scalar(select(RiskAssessmentRun).where(RiskAssessmentRun.site_id==site.id).order_by(RiskAssessmentRun.generated_at.desc()).limit(1))
        dq=db.scalar(select(DataQualityRun).where(DataQualityRun.site_id==site.id).order_by(DataQualityRun.created_at.desc()).limit(1))
        program_ids=list(db.scalars(select(AssuranceProgram.id).where(AssuranceProgram.site_id==site.id)).all())
        overdue=0
        if program_ids: overdue=db.scalar(select(func.count(AssuranceControl.id)).where(AssuranceControl.program_id.in_(program_ids), AssuranceControl.active.is_(True), AssuranceControl.next_due_at.is_not(None), AssuranceControl.next_due_at<utcnow())) or 0
        avg_risk=round(risk.summary_json.get("average_risk",0)) if risk else None
        esr_red=sum(1 for x in (rdy.esr_status.values() if rdy else []) if x.get("status")=="Red")
        status="Critical" if (rdy and rdy.open_p0>0) or esr_red else "Attention" if (rdy and (rdy.open_p1>0 or (rdy.readiness_score or 0)<85)) else "Stable"
        metric=PortfolioSiteMetric(snapshot_id=snap.id,site_id=site.id,readiness_score=rdy.readiness_score if rdy else None,risk_score=avg_risk,open_p0=rdy.open_p0 if rdy else 0,open_p1=rdy.open_p1 if rdy else 0,esr_red=esr_red,data_quality_issues=dq.summary_json.get("issue_total",0) if dq else 0,overdue_controls=overdue,status=status,details={"site_code":site.code,"readiness_snapshot_id":str(rdy.id) if rdy else None,"risk_run_id":str(risk.id) if risk else None})
        db.add(metric); metrics.append(metric)
    snap.summary_json={"site_total":len(metrics),"critical_sites":sum(x.status=="Critical" for x in metrics),"attention_sites":sum(x.status=="Attention" for x in metrics),"stable_sites":sum(x.status=="Stable" for x in metrics),"benchmark_rule":"Contextual comparison only; no punitive ranking or hidden case-mix adjustment"}
    db.flush(); return snap
