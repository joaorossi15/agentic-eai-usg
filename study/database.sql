CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS ai_interactions CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS participants CASCADE;

CREATE TABLE participants (
    participant_id UUID PRIMARY KEY,
    assignment_slot INTEGER NOT NULL UNIQUE
        CHECK (assignment_slot > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'not_started'
        CHECK (
            status IN (
                'not_started',
                'in_progress',
                'completed',
                'withdrawn'
            )
        ),
    background JSONB,
    post_study JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    participant_id UUID NOT NULL
        REFERENCES participants(participant_id)
        ON DELETE CASCADE,
    task_number INTEGER NOT NULL
        CHECK (task_number BETWEEN 1 AND 6),
    requirement_id VARCHAR(20) NOT NULL,
    principle VARCHAR(50) NOT NULL,
    condition VARCHAR(20) NOT NULL
        CHECK (condition IN ('manual', 'eai_usg')),
    status VARCHAR(20) NOT NULL DEFAULT 'not_started'
        CHECK (
            status IN (
                'not_started',
                'in_progress',
                'completed'
            )
        ),
    initial_eus JSONB,
    initial_analysis JSONB,
    initial_traceability JSONB,
    current_eus JSONB,
    final_eus JSONB,
    started_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    wall_clock_seconds DOUBLE PRECISION
        CHECK (
            wall_clock_seconds IS NULL
            OR wall_clock_seconds >= 0
        ),
    ai_wait_seconds DOUBLE PRECISION NOT NULL DEFAULT 0
        CHECK (ai_wait_seconds >= 0),
    inactive_seconds DOUBLE PRECISION NOT NULL DEFAULT 0
        CHECK (inactive_seconds >= 0),
    active_authoring_seconds DOUBLE PRECISION
        CHECK (
            active_authoring_seconds IS NULL
            OR active_authoring_seconds >= 0
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (participant_id, task_number)
);

CREATE TABLE ai_interactions (
    interaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL
        REFERENCES tasks(task_id)
        ON DELETE CASCADE,
    interaction_type VARCHAR(20) NOT NULL
        CHECK (
            interaction_type IN (
                'validation',
                'revision'
            )
        ),
    requested_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    latency_seconds DOUBLE PRECISION
        CHECK (
            latency_seconds IS NULL
            OR latency_seconds >= 0
        ),
    input_eus JSONB NOT NULL,
    validation_feedback JSONB,
    validation_output JSONB,
    revision_instruction TEXT,
    revision_output JSONB,
    revision_decision VARCHAR(20)
        CHECK (
            revision_decision IS NULL
            OR revision_decision IN (
                'accepted',
                'rejected'
            )
        ),
    api_response_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL
        REFERENCES tasks(task_id)
        ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_ai_interaction_type_per_task
ON ai_interactions(task_id, interaction_type);

CREATE INDEX idx_participants_assignment_slot
ON participants(assignment_slot);

CREATE INDEX idx_tasks_participant
ON tasks(participant_id);

CREATE INDEX idx_tasks_requirement
ON tasks(requirement_id);

CREATE INDEX idx_tasks_condition
ON tasks(condition);

CREATE INDEX idx_ai_interactions_task
ON ai_interactions(task_id);

CREATE INDEX idx_events_task
ON events(task_id);

CREATE INDEX idx_events_timestamp
ON events(event_timestamp);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
