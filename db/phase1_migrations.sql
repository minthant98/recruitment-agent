-- ================================================================
-- Recruitment SaaS — Phase 1 Migration
-- Run AFTER your existing migrations.sql is already applied.
-- Supabase Dashboard → SQL Editor → paste → Run
-- ================================================================


-- ── STEP 1: New tables ───────────────────────────────────────────

-- Organizations — one row per SME client
CREATE TABLE organizations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    recruitment_email   TEXT,           -- inbox the Gmail poller watches
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Users — recruiter accounts scoped to an org
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'recruiter',  -- recruiter | admin
    invited_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Invite tokens — for the "invite a colleague" flow
CREATE TABLE invite_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    invited_by  UUID NOT NULL REFERENCES users(id),
    used        BOOLEAN DEFAULT FALSE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ── STEP 2: Add org_id to all existing tables ────────────────────
-- These are nullable first so existing rows don't break.
-- After backfilling (if you have data), you can add NOT NULL.

ALTER TABLE departments
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE job_descriptions
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE screening_results
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE judge_verdicts
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE hitl_reviews
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;

ALTER TABLE screening_criteria
    ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id) ON DELETE CASCADE;


-- ── STEP 3: Rename job_descriptions → jobs ───────────────────────
-- Supabase does not support direct table rename via ALTER in the UI.
-- We create a jobs view alias instead — cleaner and non-destructive.
-- Your existing code keeps working via job_descriptions.
-- New code uses jobs.

CREATE VIEW jobs AS SELECT * FROM job_descriptions;

-- Add extra fields to job_descriptions for SaaS use
ALTER TABLE job_descriptions
    ADD COLUMN IF NOT EXISTS employment_type  TEXT,           -- Full-time | Part-time | Contract
    ADD COLUMN IF NOT EXISTS status           TEXT DEFAULT 'OPEN',  -- OPEN | CLOSED | DRAFT
    ADD COLUMN IF NOT EXISTS created_by       UUID REFERENCES users(id);


-- ── STEP 4: New fields on pipeline_runs ─────────────────────────

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS confidence_score FLOAT;

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS match_status TEXT DEFAULT 'AUTO_ASSIGNED';

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'EMAIL';

-- ── STEP 5: Indexes for performance ─────────────────────────────

CREATE INDEX IF NOT EXISTS idx_users_org_id
    ON users(org_id);

CREATE INDEX IF NOT EXISTS idx_departments_org_id
    ON departments(org_id);

CREATE INDEX IF NOT EXISTS idx_job_descriptions_org_id
    ON job_descriptions(org_id);

CREATE INDEX IF NOT EXISTS idx_candidates_org_id
    ON candidates(org_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_org_id
    ON pipeline_runs(org_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_match_status
    ON pipeline_runs(match_status);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_source
    ON pipeline_runs(source);

CREATE INDEX IF NOT EXISTS idx_audit_log_org_id
    ON audit_log(org_id);

CREATE INDEX IF NOT EXISTS idx_invite_tokens_token
    ON invite_tokens(token);


-- ── STEP 6: Seed your existing org (CB Bank) ────────────────────
-- This backfills org_id for all your existing rows so they
-- are owned by a real org instead of NULL.
-- Run this AFTER the migration above.

-- 1. Create CB Bank as the first org
INSERT INTO organizations (id, name, recruitment_email)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Pansy Work',
    'pansypyae1219@gmail.com'   -- replace with your actual recruitment inbox
);

-- 2. Backfill org_id on all existing tables
UPDATE departments      SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE job_descriptions SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE candidates       SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE pipeline_runs    SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE screening_results SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE judge_verdicts   SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE hitl_reviews     SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE audit_log        SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;
UPDATE screening_criteria SET org_id = '00000000-0000-0000-0000-000000000001' WHERE org_id IS NULL;


-- ── DONE ─────────────────────────────────────────────────────────
-- New tables:     organizations, users, invite_tokens
-- Modified:       all 9 existing tables now have org_id
-- New fields:     pipeline_runs.confidence_score, match_status, source
--                 job_descriptions.employment_type, status, created_by
-- View alias:     jobs → job_descriptions
-- Seeded:         CB Bank org + backfilled all existing rows