CREATE TABLE IF NOT EXISTS public.student_models (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  lesson_id uuid NOT NULL,
  vocabulary jsonb NOT NULL DEFAULT '{}',
  error_patterns jsonb NOT NULL DEFAULT '{"pronunciation": 0, "grammar": 0, "vocabulary": 0, "fluency": 0}',
  bkt jsonb NOT NULL DEFAULT '{"p_learned": 0.2, "attempts": 0, "last_updated": null}',
  session_turns integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, lesson_id)
);

CREATE INDEX idx_student_models_user_lesson
  ON public.student_models (user_id, lesson_id);

CREATE TRIGGER trg_student_models_updated_at
  BEFORE UPDATE ON public.student_models
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.student_models ENABLE ROW LEVEL SECURITY;

CREATE POLICY "student_models: select own"
  ON public.student_models
  FOR SELECT
  USING (auth.uid() = user_id);
