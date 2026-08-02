-- PIOS v1.7 post-import verification. Run after schema and seed are applied.
--
-- The indexes and constraints queries below count only application-defined
-- objects (matching the SQLAlchemy-metadata-level baseline in the comment
-- at the end of this file). Naively counting pg_indexes or
-- information_schema.table_constraints wholesale over-counts: pg_indexes
-- also includes the implicit indexes Postgres creates to back PRIMARY KEY
-- and UNIQUE constraints (92 + 77 = 169 extra on this schema), and
-- information_schema.table_constraints additionally synthesizes one virtual
-- CHECK-type row per NOT NULL column per the SQL standard (973 extra on
-- this schema) - neither is a real, independently named constraint in
-- pg_constraint. Verified directly against PostgreSQL 16 during Sprint 21
-- Runtime Validation: the naive queries returned 241 indexes and 1347
-- constraints against this exact schema, while the queries below returned
-- the documented baseline exactly.
SELECT count(*) AS tables FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';
SELECT count(*) AS columns FROM information_schema.columns WHERE table_schema='public';
SELECT count(*) AS indexes FROM pg_indexes i WHERE i.schemaname='public'
  AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conname = i.indexname AND c.connamespace = 'public'::regnamespace);
SELECT count(*) AS foreign_keys FROM pg_constraint WHERE connamespace='public'::regnamespace AND contype='f';
SELECT count(*) AS constraints FROM pg_constraint WHERE connamespace='public'::regnamespace;
-- Expected release baseline: 92 tables, 1305 columns, 72 indexes, 203 foreign keys, 374 constraints.
