-- PIOS v1.7 post-import verification. Run after schema and seed are applied.
SELECT count(*) AS tables FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';
SELECT count(*) AS columns FROM information_schema.columns WHERE table_schema='public';
SELECT count(*) AS indexes FROM pg_indexes WHERE schemaname='public';
SELECT count(*) AS foreign_keys FROM information_schema.table_constraints WHERE constraint_schema='public' AND constraint_type='FOREIGN KEY';
SELECT count(*) AS constraints FROM information_schema.table_constraints WHERE constraint_schema='public';
-- Expected release baseline: 92 tables, 1305 columns, 72 indexes, 203 foreign keys, 374 constraints.
