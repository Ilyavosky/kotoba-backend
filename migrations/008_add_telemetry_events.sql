-- One row per client event. The backend inserts with the service role;
-- there are NO public policies on purpose: students never read telemetry.
CREATE TABLE public.telemetry_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    event_type varchar(100) NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    occurred_at timestamptz NOT NULL,
    app_version varchar(20),
    platform varchar(20) CHECK (platform IN ('android', 'ios', 'web')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_telemetry_events_user
    ON public.telemetry_events (user_id);

CREATE INDEX idx_telemetry_events_type_time
    ON public.telemetry_events (event_type, occurred_at);

-- RLS on, no policies: only the service role (backend) can read/write.
ALTER TABLE public.telemetry_events ENABLE ROW LEVEL SECURITY;
