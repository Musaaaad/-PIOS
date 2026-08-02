import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
text=(ROOT/'pyproject.toml').read_text(encoding='utf-8')
components=[]
for item in re.findall(r'^\s*"([A-Za-z0-9_.-]+)([^\"]*)"',text,re.M):
    name,spec=item;components.append({'type':'library','name':name,'version_constraint':spec.strip() or None})
import os
frontend=Path(os.getenv('PIOS_FRONTEND_ROOT', str(ROOT.parent/'frontend')))
for name in ['app.js','config.js','demo-data.js','styles.css','index.html']:
    p=frontend/name
    if p.exists():components.append({'type':'file','name':f'frontend/{name}','sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
sbom={'bomFormat':'CycloneDX','specVersion':'1.5','serialNumber':'urn:uuid:pios-v1.4','version':1,'metadata':{'component':{'type':'application','name':'PIOS','version':'1.4.0'}},'components':components,'notice':'Generated from declared dependencies and tracked frontend files; not a vulnerability scan.'}
out=ROOT/'reports/PIOS_SBOM_v1.4.json';out.write_text(json.dumps(sbom,indent=2,ensure_ascii=False),encoding='utf-8');print(out)
