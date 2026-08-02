import json
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import Organization, Site
from app.services.notifications import refresh_notifications

settings=get_settings()
with SessionLocal() as db:
    org=db.scalar(select(Organization).where(Organization.code==settings.organization_code))
    if not org: raise SystemExit('Baseline organization not seeded')
    site=db.scalar(select(Site).where(Site.organization_id==org.id,Site.code==settings.default_site_code))
    if not site: raise SystemExit('Default site not found')
    result=refresh_notifications(db,site); db.commit()
print(json.dumps({'site':site.code,**result},indent=2))
