from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
html=(root/'index.html').read_text(); js=(root/'app.js').read_text(); css=(root/'styles.css').read_text()
assert 'dir="rtl"' in html and 'id="main"' in html and 'aria-label' in html
for route in ['dashboard','worklist','readiness','evidence','findings','documents','exports','pilot','deployment','operations','assurance','intelligence','actions','committee','institutional-pilot','governance','security']:
    assert route in js
for endpoint in ['/dashboard/overview','/worklists/my','/notifications','/exports','/identity/me']:
    assert endpoint in js
assert '@media' in css and 'html[dir="ltr"]' in css
assert 'بيانات عرض تجريبية غير معتمدة' in (root/'demo-data.js').read_text()
print('STATIC_CHECK_PASS')
