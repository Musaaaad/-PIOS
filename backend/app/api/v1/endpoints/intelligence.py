from __future__ import annotations
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.audit import add_audit_event
from app.core.config import get_settings
from app.core.security import Principal, get_principal, require_roles
from app.db.session import get_db
from app.models.entities import Organization, Site, RiskAssessmentRun, RiskAssessmentItem, AiGovernancePolicy, AiRecommendation, PortfolioSnapshot, PortfolioSiteMetric, MeasurableElement
from app.schemas.intelligence import RiskRunCreate,RiskRunRead,RiskItemRead,AiPolicyRead,RecommendationGenerate,RecommendationRead,RecommendationReview,PortfolioCreate,PortfolioRead
from app.services.intelligence import ensure_ai_policy,calculate_risk,generate_recommendations,review_recommendation,create_portfolio_snapshot
router=APIRouter()
def _actor(p):
    try:return UUID(p.user_id)
    except:return None
def _ctx(db):
    s=get_settings(); org=db.scalar(select(Organization).where(Organization.code==s.organization_code));
    if not org: raise HTTPException(409,"Baseline organization is not seeded")
    site=db.scalar(select(Site).where(Site.organization_id==org.id,Site.code==s.default_site_code));
    if not site: raise HTTPException(404,"Site not found")
    return org,site
@router.post('/intelligence/risk-runs',response_model=RiskRunRead,status_code=201)
def create_risk_run(payload:RiskRunCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('AccreditationLead','MedicationSafety','PharmacyDirector','SystemAdmin'))]):
    org,site=_ctx(db); row=calculate_risk(db,site.id,payload.code,payload.period_label,_actor(principal)); add_audit_event(db,request,principal,org.id,'intelligence.risk.calculate','RiskAssessmentRun',str(row.id),after=row.summary_json); db.commit();db.refresh(row);return row
@router.get('/intelligence/risk-runs/{run_id}')
def get_risk_run(run_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    row=db.get(RiskAssessmentRun,run_id)
    if not row: raise HTTPException(404,'Risk run not found')
    return RiskRunRead.model_validate(row)
@router.get('/intelligence/risk-runs/{run_id}/items')
def list_risk_items(run_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)],band:str|None=Query(None)):
    q=select(RiskAssessmentItem,MeasurableElement.me_id).join(MeasurableElement,MeasurableElement.id==RiskAssessmentItem.measurable_element_id).where(RiskAssessmentItem.run_id==run_id)
    if band:q=q.where(RiskAssessmentItem.risk_band==band)
    rows=db.execute(q.order_by(RiskAssessmentItem.risk_score.desc(),MeasurableElement.me_id)).all()
    return [{**RiskItemRead.model_validate(x).model_dump(mode='json'),'me_id':me_id} for x,me_id in rows]
@router.post('/intelligence/ai-policy/bootstrap')
def bootstrap_policy(request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('SystemAdmin','PharmacyDirector','AccreditationLead'))]):
    org,_=_ctx(db); row,created=ensure_ai_policy(db,org.id,_actor(principal)); add_audit_event(db,request,principal,org.id,'intelligence.ai_policy.bootstrap','AiGovernancePolicy',str(row.id),after={'created':created});db.commit();db.refresh(row);return {'policy':AiPolicyRead.model_validate(row),'created':created}
@router.get('/intelligence/ai-policy',response_model=AiPolicyRead)
def get_policy(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    org,_=_ctx(db); row,_=ensure_ai_policy(db,org.id);db.commit();db.refresh(row);return row
@router.post('/intelligence/risk-runs/{run_id}/recommendations/generate')
def generate(run_id:UUID,payload:RecommendationGenerate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('AccreditationLead','MedicationSafety','PharmacyDirector'))]):
    org,site=_ctx(db); run=db.get(RiskAssessmentRun,run_id)
    if not run:raise HTTPException(404,'Risk run not found')
    ensure_ai_policy(db,org.id,_actor(principal)); rows=generate_recommendations(db,run,site.id,payload.limit,_actor(principal)); add_audit_event(db,request,principal,org.id,'intelligence.recommendations.generate','RiskAssessmentRun',str(run.id),after={'created':len(rows)});db.commit();return {'created':len(rows),'recommendations':[RecommendationRead.model_validate(x) for x in rows]}
@router.get('/intelligence/recommendations',response_model=list[RecommendationRead])
def list_recommendations(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)],status:str|None=Query(None)):
    _,site=_ctx(db);q=select(AiRecommendation).where(AiRecommendation.site_id==site.id)
    if status:q=q.where(AiRecommendation.status==status)
    return list(db.scalars(q.order_by(AiRecommendation.created_at.desc())).all())
@router.post('/intelligence/recommendations/{recommendation_id}/review',response_model=RecommendationRead)
def review(recommendation_id:UUID,payload:RecommendationReview,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('AccreditationLead','MedicationSafety','PharmacyDirector'))]):
    org,_=_ctx(db);row=db.get(AiRecommendation,recommendation_id)
    if not row:raise HTTPException(404,'Recommendation not found')
    review_recommendation(row,payload.decision,payload.comment,_actor(principal));add_audit_event(db,request,principal,org.id,'intelligence.recommendation.review','AiRecommendation',str(row.id),after=payload.model_dump());db.commit();db.refresh(row);return row
@router.post('/intelligence/portfolio-snapshots',response_model=PortfolioRead,status_code=201)
def create_portfolio(payload:PortfolioCreate,request:Request,db:Annotated[Session,Depends(get_db)],principal:Annotated[Principal,Depends(require_roles('PharmacyDirector','AccreditationLead','SystemAdmin'))]):
    org,_=_ctx(db);row=create_portfolio_snapshot(db,org.id,payload.code,payload.period_label,_actor(principal));add_audit_event(db,request,principal,org.id,'intelligence.portfolio.create','PortfolioSnapshot',str(row.id),after=row.summary_json);db.commit();db.refresh(row);return row
@router.get('/intelligence/portfolio-snapshots/{snapshot_id}')
def get_portfolio(snapshot_id:UUID,db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    row=db.get(PortfolioSnapshot,snapshot_id)
    if not row:raise HTTPException(404,'Portfolio snapshot not found')
    metrics=list(db.scalars(select(PortfolioSiteMetric).where(PortfolioSiteMetric.snapshot_id==snapshot_id).order_by(PortfolioSiteMetric.status,PortfolioSiteMetric.risk_score.desc())).all())
    return {'snapshot':PortfolioRead.model_validate(row).model_dump(mode='json'),'sites':[{'site_id':str(x.site_id),'readiness_score':x.readiness_score,'risk_score':x.risk_score,'open_p0':x.open_p0,'open_p1':x.open_p1,'esr_red':x.esr_red,'data_quality_issues':x.data_quality_issues,'overdue_controls':x.overdue_controls,'status':x.status,'details':x.details} for x in metrics]}
@router.get('/intelligence/executive-dashboard')
def executive_dashboard(db:Annotated[Session,Depends(get_db)],_:Annotated[Principal,Depends(get_principal)]):
    org,site=_ctx(db);risk=db.scalar(select(RiskAssessmentRun).where(RiskAssessmentRun.site_id==site.id).order_by(RiskAssessmentRun.generated_at.desc()).limit(1));policy,_=ensure_ai_policy(db,org.id); pending=db.scalars(select(AiRecommendation).where(AiRecommendation.site_id==site.id,AiRecommendation.status=='NeedsHumanReview')).all();db.commit()
    return {'site_code':site.code,'latest_risk':RiskRunRead.model_validate(risk).model_dump(mode='json') if risk else None,'pending_human_review':len(list(pending)),'ai_policy':{'code':policy.code,'human_review_required':policy.human_review_required,'prohibited_actions':policy.prohibited_actions},'safety_note':'Risk is a decision-support signal, not a compliance score or clinical prediction.'}
