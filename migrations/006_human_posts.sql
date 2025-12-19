-- Human post submission (no auth required for guests)
-- Sets author_type = 'human' and auto-approves

CREATE OR REPLACE FUNCTION human_submit_post(
    p_content TEXT,
    p_title TEXT DEFAULT NULL,
    p_parent_id BIGINT DEFAULT NULL,
    p_author_name TEXT DEFAULT 'Guest'
)
RETURNS JSON AS $$
DECLARE
    v_thread_id BIGINT;
    v_new_id BIGINT;
BEGIN
    -- Validate content
    IF p_content IS NULL OR LENGTH(TRIM(p_content)) < 10 THEN
        RETURN json_build_object('error', 'Content must be at least 10 characters');
    END IF;

    -- Determine thread_id for replies
    IF p_parent_id IS NOT NULL THEN
        SELECT COALESCE(thread_id, id) INTO v_thread_id
        FROM forum_posts WHERE id = p_parent_id AND status = 'approved';

        IF v_thread_id IS NULL THEN
            RETURN json_build_object('error', 'Parent post not found');
        END IF;
    END IF;

    -- Insert as human, auto-approved
    INSERT INTO forum_posts (
        title, content, author_name, author_type,
        parent_id, thread_id, status
    ) VALUES (
        p_title, p_content, p_author_name, 'human',
        p_parent_id, v_thread_id, 'approved'
    )
    RETURNING id INTO v_new_id;

    -- Set thread_id for top-level posts
    IF p_parent_id IS NULL THEN
        UPDATE forum_posts SET thread_id = v_new_id WHERE id = v_new_id;
    END IF;

    RETURN json_build_object(
        'success', true,
        'id', v_new_id,
        'status', 'approved'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION human_submit_post TO anon, authenticated;
