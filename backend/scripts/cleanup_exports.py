from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import ExportJob

removed=0
with SessionLocal() as db:
    rows=db.scalars(select(ExportJob).where(ExportJob.expires_at.is_not(None),ExportJob.expires_at<datetime.now(timezone.utc),ExportJob.status=='Completed')).all()
    for row in rows:
        if row.storage_uri:
            p=Path(row.storage_uri)
            if p.exists(): p.unlink(missing_ok=True)
            try: p.parent.rmdir()
            except OSError: pass
        row.status='Expired'; removed+=1
    db.commit()
print({'expired_exports':removed})
