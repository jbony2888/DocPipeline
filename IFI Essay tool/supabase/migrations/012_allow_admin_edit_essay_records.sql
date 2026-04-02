-- Allow authenticated admins to edit essay records while preserving owner-based access for regular users.
-- Admin detection uses JWT claims:
--   1) auth.jwt()->'app_metadata'->>'role' = 'admin'
--   2) auth.jwt()->>'role' = 'admin'

CREATE OR REPLACE FUNCTION public.is_admin_user()
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin', FALSE)
        OR COALESCE((auth.jwt() ->> 'role') = 'admin', FALSE);
$$;

GRANT EXECUTE ON FUNCTION public.is_admin_user() TO authenticated;

-- Submissions: keep existing owner policies and add admin-wide access policies.
DROP POLICY IF EXISTS "Admins can view all submissions" ON public.submissions;
CREATE POLICY "Admins can view all submissions"
    ON public.submissions
    FOR SELECT
    USING (public.is_admin_user());

DROP POLICY IF EXISTS "Admins can insert all submissions" ON public.submissions;
CREATE POLICY "Admins can insert all submissions"
    ON public.submissions
    FOR INSERT
    WITH CHECK (public.is_admin_user());

DROP POLICY IF EXISTS "Admins can update all submissions" ON public.submissions;
CREATE POLICY "Admins can update all submissions"
    ON public.submissions
    FOR UPDATE
    USING (public.is_admin_user())
    WITH CHECK (public.is_admin_user());

DROP POLICY IF EXISTS "Admins can delete all submissions" ON public.submissions;
CREATE POLICY "Admins can delete all submissions"
    ON public.submissions
    FOR DELETE
    USING (public.is_admin_user());

-- Essay rankings: enable authenticated admin edits.
ALTER TABLE public.essay_rankings ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.essay_rankings TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.essay_rankings_id_seq TO authenticated;

DROP POLICY IF EXISTS "Admins can manage essay rankings" ON public.essay_rankings;
CREATE POLICY "Admins can manage essay rankings"
    ON public.essay_rankings
    FOR ALL
    USING (public.is_admin_user())
    WITH CHECK (public.is_admin_user());
