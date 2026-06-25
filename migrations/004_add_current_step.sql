ALTER TABLE public.user_progress
  ADD COLUMN IF NOT EXISTS current_step integer NOT NULL DEFAULT 1
    CHECK (current_step BETWEEN 1 AND 6);
