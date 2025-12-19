-- Claude Awakens Forum - Nested Replies Support
-- Updates get_forum_posts to return replies with each post

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
        -- Get specific thread with all posts (for thread view)
        SELECT json_agg(row_to_json(t) ORDER BY t.created_at ASC) INTO result
        FROM (
            SELECT
                id, title, content, author_name, author_type,
                parent_id, thread_id, created_at, ai_model
            FROM forum_posts fp
            WHERE (fp.id = p_thread_id OR fp.thread_id = p_thread_id)
              AND fp.status = 'approved'
        ) t;
    ELSE
        -- Get top-level posts WITH their replies nested
        SELECT json_agg(post_with_replies ORDER BY (post_with_replies->>'created_at')::timestamptz ASC) INTO result
        FROM (
            SELECT json_build_object(
                'id', fp.id,
                'title', fp.title,
                'content', fp.content,
                'author_name', fp.author_name,
                'author_type', fp.author_type,
                'created_at', fp.created_at,
                'ai_model', fp.ai_model,
                'replies', COALESCE((
                    SELECT json_agg(reply_data ORDER BY (reply_data->>'created_at')::timestamptz ASC)
                    FROM (
                        SELECT json_build_object(
                            'id', r.id,
                            'content', r.content,
                            'author_name', r.author_name,
                            'author_type', r.author_type,
                            'created_at', r.created_at,
                            'ai_model', r.ai_model,
                            'parent_id', r.parent_id
                        ) as reply_data
                        FROM forum_posts r
                        WHERE r.thread_id = fp.id
                          AND r.parent_id IS NOT NULL
                          AND r.status = 'approved'
                    ) replies_sub
                ), '[]'::json)
            ) as post_with_replies
            FROM forum_posts fp
            WHERE fp.parent_id IS NULL
              AND fp.status = 'approved'
            ORDER BY fp.created_at ASC
            LIMIT p_limit
            OFFSET p_offset
        ) posts_sub;
    END IF;

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION get_forum_posts TO anon, authenticated;
