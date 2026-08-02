# PIOS Sprint 2 Runtime Acceptance Checklist

تنفذ هذه القائمة على بيئة تحتوي PostgreSQL 16+ وMinIO/S3. لا تستخدم بيانات مرضى حقيقية أثناء الاختبار الأولي.

## 1. المنصة والتخزين

- `docker compose up --build -d` يعمل دون أخطاء.
- PostgreSQL healthy وMinIO bucket باسم `pios-evidence` موجود وغير عام.
- `/ready` يعيد `database=reachable` و`object_storage_backend=s3`.
- `alembic current` يصل إلى `0002_sprint2_evidence`.

## 2. Baseline

- 41 معيارًا.
- 266 ME.
- 63 بندًا فرعيًا.
- 75 وثيقة لطريف.

## 3. Evidence Workflow

- إنشاء Campaign في Draft ثم فتحها.
- إنشاء Request مرتبط بـME وEOC.
- منع تكرار `campaign + ME + tool_code`.
- إنشاء Evidence Item وربطه تلقائيًا بـME.
- رفع ملف نظيف إلى MinIO وتسجيل SHA-256.
- رفض MIME غير مسموح، ملف فارغ، توقيع ملف غير مطابق، EICAR، والملف المكرر.
- منع Submit دون ملف نظيف أوstructured content.
- انتقال Submitted ثم UnderReview.
- إلزام اختبارات المراجعة السبعة.
- منع Accepted عند وجود Test غير Pass.
- إنشاء Finding تلقائي عند Partial/Rejected/Contradictory/Expired.
- جعل Finding لـESR من P0 افتراضيًا.
- ظهور Audit Events وTrace ID لكل التحولات.

## 4. الأمن والخصوصية

- Bucket خاص وغير متاح للعامة.
- مفاتيح S3 خارج المستودع وفي Secret Store.
- HTTPS/TLS أمام API وObject Storage.
- OIDC/JWT مؤسسي بدل Dev Tokens قبل الإنتاج.
- تشفير التخزين والنسخ الاحتياطية وسياسة retention.
- استبدال Basic Scan بخدمة ClamAV أوبوابة فحص مؤسسية.
