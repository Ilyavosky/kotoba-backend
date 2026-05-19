ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lessons ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_progress ENABLE ROW LEVEL SECURITY;

-- users: Each one only reads, edits and sees its own registration
CREATE POLICY "users: select own" ON public.users FOR SELECT USING (auth.uid() = id);
CREATE POLICY "users: insert own" ON public.users FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "users: update own" ON public.users FOR UPDATE USING (auth.uid() = id);

-- lessons: The lecture is public, writing onlyu with service_role
CREATE POLICY "lessons: public read" ON public.lessons FOR SELECT USING (is_active = true);

-- conversation_turns: Only the owner
CREATE POLICY "turns: select own" ON public.conversation_turns FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "turns: insert own" ON public.conversation_turns FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "turns: update own" ON public.conversation_turns FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- user_progress: Only the owner
CREATE POLICY "progress: select own" ON public.user_progress FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "progress: insert own" ON public.user_progress FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "progress: update own" ON public.user_progress FOR UPDATE 
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);