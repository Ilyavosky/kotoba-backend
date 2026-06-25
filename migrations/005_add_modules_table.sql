-- K-05.2: Module table for multi-lesson progression
-- Date: 2026-06-25

CREATE TABLE IF NOT EXISTS public.modules (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title       varchar(200) NOT NULL,
    language    varchar(10)  NOT NULL,
    level       varchar(2)   NOT NULL CHECK (level IN ('A1','A2','B1','B2','C1','C2')),
    lesson_ids  uuid[]       NOT NULL DEFAULT '{}',
    is_active   boolean      NOT NULL DEFAULT true,
    created_at  timestamptz  NOT NULL DEFAULT now(),
    updated_at  timestamptz  NOT NULL DEFAULT now()
);

-- GIN index so ANY(lesson_ids) lookups are fast
CREATE INDEX idx_modules_lesson_ids ON public.modules USING gin(lesson_ids);
CREATE INDEX idx_modules_language_level ON public.modules(language, level);

-- Trigger for updated_at
CREATE TRIGGER trg_modules_updated_at
    BEFORE UPDATE ON public.modules
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS: public read, writes only via service_role
ALTER TABLE public.modules ENABLE ROW LEVEL SECURITY;

CREATE POLICY "modules: public read" ON public.modules
    FOR SELECT USING (is_active = true);
