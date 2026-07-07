-- Adds 'system_error' to the allowed decision values.
-- A system_error row means the LLM/infra failed on that turn: the student's
-- production was never evaluated and the state machine did not move.
-- Without this, the engine's system_error INSERT would violate the CHECK and
-- be silently swallowed by the repository's except — losing observability.
ALTER TABLE public.decision_logs
    DROP CONSTRAINT decision_logs_decision_check;

ALTER TABLE public.decision_logs
    ADD CONSTRAINT decision_logs_decision_check
    CHECK (decision IN ('advance', 'stay_clean', 'stay_error', 'system_error'));
