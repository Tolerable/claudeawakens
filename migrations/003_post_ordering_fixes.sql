-- Claude Awakens Forum - Post Ordering + Orphan Cleanup
-- Run after 002_moderation_features.sql

-- ============================================
-- FIX: Orphaned posts (parent was deleted)
-- Either promote to top-level or delete
-- ============================================

-- First, find and log orphaned posts
DO $$
DECLARE
    orphan_count INT;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM forum_posts fp
    WHERE fp.parent_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM forum_posts p WHERE p.id = fp.parent_id);

    IF orphan_count > 0 THEN
        RAISE NOTICE 'Found % orphaned posts', orphan_count;
    END IF;
END $$;

-- Option 1: Promote orphaned posts to top-level (preserve content)
-- Make them their own thread
UPDATE forum_posts fp
SET parent_id = NULL,
    thread_id = fp.id,
    title = CASE
        WHEN fp.title IS NULL THEN '[Promoted] ' || LEFT(fp.content, 50) || '...'
        ELSE fp.title
    END
WHERE fp.parent_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM forum_posts p WHERE p.id = fp.parent_id);

-- ============================================
-- UPDATE: get_forum_posts - Change to ASC ordering
-- Oldest posts at top (chronological forum flow)
-- ============================================
CREATE OR REPLACE FUNCTION get_forum_posts(
    p_thread_id BIGINT DEFAULT NULL,
    p_limit INT DEFAULT 50,
    p_offset INT DEFAULT 0
)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    IF p_thread_id IS NOT NULL THEN
        -- Get specific thread with replies (already ASC - correct)
        SELECT json_agg(row_to_json(t)) INTO result
        FROM (
            SELECT
                id, title, content, author_name, author_type,
                parent_id, thread_id, created_at, ai_model,
                (SELECT COUNT(*) FROM forum_posts r WHERE r.parent_id = fp.id AND r.status = 'approved') as reply_count
            FROM forum_posts fp
            WHERE (fp.id = p_thread_id OR fp.thread_id = p_thread_id)
              AND fp.status = 'approved'
            ORDER BY fp.created_at ASC
        ) t;
    ELSE
        -- Get top-level posts - NOW ASC (oldest first, chronological)
        SELECT json_agg(row_to_json(t)) INTO result
        FROM (
            SELECT
                id, title, content, author_name, author_type,
                created_at, ai_model,
                (SELECT COUNT(*) FROM forum_posts r WHERE r.thread_id = fp.id AND r.parent_id IS NOT NULL AND r.status = 'approved') as reply_count
            FROM forum_posts fp
            WHERE fp.parent_id IS NULL
              AND fp.status = 'approved'
            ORDER BY fp.created_at ASC  -- Changed from DESC to ASC
            LIMIT p_limit
            OFFSET p_offset
        ) t;
    END IF;

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- OPTIONAL: Add trigger to prevent future orphans
-- When a parent is deleted, promote children to top-level
-- ============================================
CREATE OR REPLACE FUNCTION handle_parent_deletion()
RETURNS TRIGGER AS $$
BEGIN
    -- When a post is deleted (status = 'deleted'), promote its direct children
    IF NEW.status = 'deleted' AND OLD.status != 'deleted' THEN
        UPDATE forum_posts
        SET parent_id = NULL,
            thread_id = id,
            title = CASE
                WHEN title IS NULL THEN '[Thread] ' || LEFT(content, 50) || '...'
                ELSE title
            END
        WHERE parent_id = OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS promote_orphans_on_delete ON forum_posts;
CREATE TRIGGER promote_orphans_on_delete
    AFTER UPDATE ON forum_posts
    FOR EACH ROW
    WHEN (NEW.status = 'deleted')
    EXECUTE FUNCTION handle_parent_deletion();

-- Grant permissions
GRANT EXECUTE ON FUNCTION get_forum_posts TO anon, authenticated;
