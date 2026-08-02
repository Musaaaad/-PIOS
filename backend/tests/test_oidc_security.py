import base64
import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from app.core.config import Settings
from app.core.security import decode_oidc_token


def b64u_int(value: int) -> str:
    raw = value.to_bytes((value.bit_length()+7)//8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_offline_oidc_jwks_verification():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers(); kid = "test-key"
    jwks = {"keys":[{"kty":"RSA","kid":kid,"use":"sig","alg":"RS256","n":b64u_int(pub.n),"e":b64u_int(pub.e)}]}
    settings = Settings(
        env="test", auth_mode="oidc", oidc_issuer="https://id.example.test/realms/pios",
        oidc_audience="pios-api", oidc_jwks_json=json.dumps(jwks), oidc_algorithms="RS256",
    )
    now = int(time.time())
    token = jwt.encode({"sub":"user-1","iss":settings.oidc_issuer,"aud":settings.oidc_audience,"iat":now,"exp":now+300,"roles":["AccreditationLead"],"sites":["TGH"]}, key, algorithm="RS256", headers={"kid":kid})
    claims = decode_oidc_token(token, settings)
    assert claims["sub"] == "user-1" and claims["roles"] == ["AccreditationLead"]
