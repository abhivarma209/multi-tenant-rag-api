from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Tenant

async def get_current_tenant(
    x_api_key: str = Header(...),   # FastAPI extracts X-API-Key header
    db: Session = Depends(get_db)
) -> Tenant:
    # TODO: query db for tenant with this api_key
    # TODO: raise 401 if not found
    # TODO: return tenant
    tenant = db.query(Tenant).filter(Tenant.api_key == x_api_key).first()
    if not tenant:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return tenant