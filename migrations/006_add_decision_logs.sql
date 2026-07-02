-- Stores one row per engine decision, per turn.
CREATE TABLE public.decision_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    lesson_id uuid NOT NULL,
    step_before integer NOT NULL,
    step_after integer NOT NULL,
    decision varchar(20) NOT NULL CHECK (decision IN ('advance', 'stay_clean', 'stay_error')),
    error_detected text,
    full_reasoning jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);


CREATE INDEX idx_decision_logs_user_lesson
    ON public.decision_logs (user_id, lesson_id);

-- RLS: users can only read their own logs
ALTER TABLE public.decision_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own decision logs"
    ON public.decision_logs
    FOR SELECT
    USING (user_id = auth.uid());