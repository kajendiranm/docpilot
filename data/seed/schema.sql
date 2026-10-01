-- Demo "team database" queried by the run_sql tool.
-- Re-running drops and recreates the tables, so seeding always starts clean.

DROP TABLE IF EXISTS deployments, incidents, services CASCADE;

CREATE TABLE services (
    id       SERIAL PRIMARY KEY,
    name     TEXT UNIQUE NOT NULL,
    team     TEXT NOT NULL,
    language TEXT NOT NULL,
    tier     TEXT NOT NULL CHECK (tier IN ('tier-1', 'tier-2', 'tier-3'))
);

CREATE TABLE incidents (
    id          SERIAL PRIMARY KEY,
    service_id  INT NOT NULL REFERENCES services(id),
    severity    TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title       TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ            -- NULL = still open
);

CREATE TABLE deployments (
    id          SERIAL PRIMARY KEY,
    service_id  INT NOT NULL REFERENCES services(id),
    version     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('success', 'failed', 'rolled_back')),
    deployed_at TIMESTAMPTZ NOT NULL,
    deployed_by TEXT NOT NULL
);

CREATE INDEX ON incidents (service_id, started_at);
CREATE INDEX ON deployments (service_id, deployed_at);
