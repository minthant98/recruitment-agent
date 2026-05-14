-- ================================================================
-- Recruitment Agent — Supabase Migrations
-- Run this in: Supabase Dashboard → SQL Editor → Run
-- ================================================================


-- ── 1. departments ───────────────────────────────────────────────
CREATE TABLE departments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    head_name   TEXT NOT NULL,
    head_email  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ── 2. job_descriptions ──────────────────────────────────────────
CREATE TABLE job_descriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dept_id         UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    role_title      TEXT NOT NULL,
    seniority_level TEXT,
    required_years  FLOAT,
    raw_text        TEXT,
    source_file     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ── 3. screening_criteria ────────────────────────────────────────
CREATE TABLE screening_criteria (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jd_id           UUID NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    criterion_name  TEXT NOT NULL,
    weight          FLOAT NOT NULL,
    description     TEXT
);


-- ── 4. candidates ────────────────────────────────────────────────
CREATE TABLE candidates (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                        TEXT NOT NULL,
    email                       TEXT,
    total_experience_years      FLOAT,
    relevant_experience_years   FLOAT,
    previous_roles              JSONB,
    industry_exposure           JSONB,
    education                   TEXT,
    raw_cv_text                 TEXT,
    structured_cv               JSONB,
    source_email_id             TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);


-- ── 5. pipeline_runs ─────────────────────────────────────────────
CREATE TABLE pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    jd_id           UUID NOT NULL REFERENCES job_descriptions(id) ON DELETE CASCADE,
    current_node    TEXT NOT NULL DEFAULT 'classifier',
    status          TEXT NOT NULL DEFAULT 'in_progress',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at on every pipeline_runs change
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pipeline_runs_updated_at
    BEFORE UPDATE ON pipeline_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── 6. screening_results ─────────────────────────────────────────
CREATE TABLE screening_results (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    required_skills_score   FLOAT,
    experience_score        FLOAT,
    preferred_skills_score  FLOAT,
    education_domain_score  FLOAT,
    composite_score         FLOAT,
    experience_match_rating TEXT,
    skills_analysis         JSONB,
    experience_analysis     JSONB,
    strengths               JSONB,
    weaknesses              JSONB,
    recommendation          TEXT,
    decision_justification  TEXT,
    full_screener_output    JSONB,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);


-- ── 7. judge_verdicts ────────────────────────────────────────────
CREATE TABLE judge_verdicts (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                   UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    criterion_verdicts       JSONB,
    overall_agrees           BOOLEAN,
    suggested_recommendation TEXT,
    conflict_flag            BOOLEAN NOT NULL DEFAULT FALSE,
    conflict_reason          TEXT,
    confidence               FLOAT,
    created_at               TIMESTAMPTZ DEFAULT NOW()
);


-- ── 8. hitl_reviews ──────────────────────────────────────────────
CREATE TABLE hitl_reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    reviewed_by     TEXT NOT NULL,
    final_decision  TEXT NOT NULL,
    override_reason TEXT,
    was_overridden  BOOLEAN DEFAULT FALSE,
    reviewed_at     TIMESTAMPTZ DEFAULT NOW()
);


-- ── 9. audit_log ─────────────────────────────────────────────────
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    node_name   TEXT NOT NULL,
    action      TEXT NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ================================================================
-- Indexes for common query patterns
-- ================================================================

CREATE INDEX idx_pipeline_runs_candidate ON pipeline_runs(candidate_id);
CREATE INDEX idx_pipeline_runs_jd        ON pipeline_runs(jd_id);
CREATE INDEX idx_pipeline_runs_status    ON pipeline_runs(status);
CREATE INDEX idx_screening_results_run   ON screening_results(run_id);
CREATE INDEX idx_judge_verdicts_run      ON judge_verdicts(run_id);
CREATE INDEX idx_judge_verdicts_conflict ON judge_verdicts(conflict_flag);
CREATE INDEX idx_audit_log_run           ON audit_log(run_id, created_at);

