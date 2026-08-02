from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

HEX=set('0123456789abcdef')
def _sha(v:str)->str:
    v=v.lower().strip()
    if len(v)!=64 or any(x not in HEX for x in v): raise ValueError('sha256 must be 64 lowercase hexadecimal characters')
    return v

class ReleaseCreate(BaseModel):
    code:str=Field(min_length=3,max_length=64)
    version:str=Field(min_length=1,max_length=32)
    release_sha:str
    _release_sha=field_validator('release_sha')(_sha)
class ArtifactCreate(BaseModel):
    name:str=Field(min_length=1,max_length=255)
    artifact_type:Literal['Backend','Frontend','OpenAPI','DatabaseSchema','Seed','SBOM','Manifest','TestReport','Other']
    uri:str=Field(min_length=3,max_length=2000)
    sha256:str
    size_bytes:int=Field(default=0,ge=0)
    media_type:str|None=None
    signed:bool=False
    signature_reference:str|None=None
    immutable:bool=True
    _sha256=field_validator('sha256')(_sha)
class ReleaseRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;organization_id:UUID;code:str;version:str;release_sha:str;status:str;artifact_count:int;evaluation_json:dict[str,Any];approved_at:datetime|None=None;published_at:datetime|None=None
class ArtifactRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;release_package_id:UUID;name:str;artifact_type:str;uri:str;sha256:str;size_bytes:int;media_type:str|None=None;signed:bool;signature_reference:str|None=None;immutable:bool
class SecurityControlUpdate(BaseModel):
    status:Literal['Pending','Pass','Fail','Waived']
    evidence_reference:str|None=Field(default=None,max_length=2000)
    details:dict[str,Any]=Field(default_factory=dict)
class SecurityControlRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;organization_id:UUID;code:str;title:str;category:str;severity:str;required:bool;status:str;evidence_reference:str|None=None;details:dict[str,Any];checked_at:datetime|None=None
class RetentionPolicyCreate(BaseModel):
    code:str=Field(min_length=3,max_length=64)
    entity_type:str=Field(min_length=2,max_length=128)
    retention_days:int=Field(ge=1,le=36500)
    legal_basis:str=Field(min_length=3,max_length=2000)
    purge_method:Literal['SoftDeleteThenPurge','ArchiveThenPurge','Anonymize','NeverPurge']='SoftDeleteThenPurge'
class RetentionPolicyRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;organization_id:UUID;code:str;entity_type:str;retention_days:int;legal_basis:str;purge_method:str;active:bool;approved_at:datetime|None=None
class LegalHoldCreate(BaseModel):
    code:str=Field(min_length=3,max_length=64)
    scope_type:Literal['Organization','Site','EntityType','Entity']
    scope_id:str|None=Field(default=None,max_length=128)
    reason:str=Field(min_length=3,max_length=2000)
class LegalHoldRelease(BaseModel):
    reason:str=Field(min_length=3,max_length=2000)
class LegalHoldRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;organization_id:UUID;code:str;scope_type:str;scope_id:str|None=None;reason:str;status:str;placed_at:datetime;released_at:datetime|None=None;release_reason:str|None=None
class AuditExportCreate(BaseModel):
    code:str=Field(min_length=3,max_length=64)
    period_start:datetime
    period_end:datetime
class AuditExportRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID;organization_id:UUID;code:str;period_start:datetime;period_end:datetime;status:str;event_count:int;root_hash:str;file_sha256:str;uri:str;manifest_json:dict[str,Any];verified_at:datetime|None=None
