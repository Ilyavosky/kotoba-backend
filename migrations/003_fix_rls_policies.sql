-- Fixes RLS policies in order to support UPSERT and close security gaps
DROP POLICY IF EXISTS "users: update own" ON public.users;

CREATE POLICY "users: update own" ON public.users
  FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);


DROP POLICY IF EXISTS "turns: select own"  ON public.conversation_turns;
DROP POLICY IF EXISTS "turns: insert own"  ON public.conversation_turns;
DROP POLICY IF EXISTS "turns: update own"  ON public.conversation_turns;

CREATE POLICY "turns: own" ON public.conversation_turns
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);


DROP POLICY IF EXISTS "progress: select own" ON public.user_progress;
DROP POLICY IF EXISTS "progress: insert own" ON public.user_progress;
DROP POLICY IF EXISTS "progress: update own" ON public.user_progress;

CREATE POLICY "progress: own" ON public.user_progress
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
