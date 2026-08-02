import base64, json, time
import jwt, pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from app.core.config import Settings
from app.core.security import decode_oidc_token, Principal
from app.core.site_access import require_site_access
from fastapi import HTTPException

def b64u(v):
    raw=v.to_bytes((v.bit_length()+7)//8,"big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

def fixture():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048); pub=key.public_key().public_numbers(); kid="v17"
    jwks={"keys":[{"kty":"RSA","kid":kid,"use":"sig","alg":"RS256","n":b64u(pub.n),"e":b64u(pub.e)}]}
    settings=Settings(env="test",auth_mode="oidc",oidc_issuer="https://id.test/pios",oidc_audience="pios-api",oidc_jwks_json=json.dumps(jwks),oidc_algorithms="RS256")
    return key,kid,settings

def token(key,kid,settings,**overrides):
    now=int(time.time()); claims={"sub":"user-1","iss":settings.oidc_issuer,"aud":settings.oidc_audience,"iat":now,"exp":now+300,"roles":["EvidenceOwner"],"sites":["TGH"]}; claims.update(overrides)
    return jwt.encode(claims,key,algorithm="RS256",headers={"kid":kid})

def test_oidc_positive():
    key,kid,s=fixture(); c=decode_oidc_token(token(key,kid,s),s); assert c["sub"]=="user-1" and c["sites"]==["TGH"]

@pytest.mark.parametrize("override",[{"aud":"wrong"},{"iss":"https://wrong"},{"exp":1}])
def test_oidc_negative_claims(override):
    key,kid,s=fixture()
    with pytest.raises(Exception): decode_oidc_token(token(key,kid,s,**override),s)

def test_oidc_wrong_key_rejected():
    key,kid,s=fixture(); other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    bad=jwt.encode({"sub":"u","iss":s.oidc_issuer,"aud":s.oidc_audience,"exp":int(time.time())+60,"roles":["EvidenceOwner"]},other,algorithm="RS256",headers={"kid":kid})
    with pytest.raises(Exception): decode_oidc_token(bad,s)

def test_site_isolation_after_claim_mapping():
    p=Principal("user-1",frozenset({"EvidenceOwner"}),site_codes=frozenset({"TGH"}),auth_source="oidc")
    require_site_access(p,"TGH")
    with pytest.raises(HTTPException): require_site_access(p,"OTHER")
