CREATE TABLE IF NOT EXISTS public.users (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name varchar(100) NOT NULL CHECK (trim(display_name) <> ''),
  native_language varchar(10) NOT NULL CHECK (char_length(native_language) BETWEEN 2 AND 10),
  target_language varchar(10) NOT NULL CHECK (char_length(target_language) BETWEEN 2 AND 10),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.lessons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title varchar(200)  NOT NULL,
  description text NOT NULL DEFAULT '',
  language varchar(10) NOT NULL,
  level varchar(2) NOT NULL CHECK (level IN ('A1','A2','B1','B2','C1','C2')),
  content jsonb NOT NULL DEFAULT '{}',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS public.conversation_turns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  lesson_id uuid NOT NULL REFERENCES public.lessons(id) ON DELETE RESTRICT,
  role varchar(10) NOT NULL CHECK (role IN ('user', 'assistant')),
  content text NOT NULL,
  audio_url text,
  turn_number integer NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE IF NOT EXISTS public.user_progress (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  lesson_id uuid NOT NULL REFERENCES public.lessons(id) ON DELETE CASCADE,
  status varchar(20) NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','completed')),
  score numeric(5,2),
  turns_count integer NOT NULL DEFAULT 0,
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, lesson_id)
);

CREATE INDEX idx_conversation_turns_user_id ON public.conversation_turns(user_id);
CREATE INDEX idx_conversation_turns_lesson_id ON public.conversation_turns(lesson_id);
CREATE INDEX idx_user_progress_user_id ON public.user_progress(user_id);
CREATE INDEX idx_user_progress_lesson_id ON public.user_progress(lesson_id);
CREATE INDEX idx_lessons_language_level ON public.lessons(language, level);
CREATE INDEX idx_lessons_is_active ON public.lessons(is_active);

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_lessons_updated_at
  BEFORE UPDATE ON public.lessons
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_user_progress_updated_at
  BEFORE UPDATE ON public.user_progress
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();