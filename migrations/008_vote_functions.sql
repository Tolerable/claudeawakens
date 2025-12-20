-- Vote Functions for Forum
-- Created: 2025-12-20

-- ============================================
-- RPC: TOGGLE VOTE (Authenticated users only)
-- Toggles vote: no vote -> up/down, same vote -> remove, opposite -> switch
-- ============================================
CREATE OR REPLACE FUNCTION toggle_vote(
    p_post_id BIGINT,
    p_vote_type INT  -- 1 = upvote, -1 = downvote
)
RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_existing_vote INT;
    v_new_score INT;
    v_user_vote INT;
BEGIN
    -- Must be authenticated
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RETURN json_build_object('error', 'Login required to vote');
    END IF;

    -- Check if post exists
    IF NOT EXISTS (SELECT 1 FROM forum_posts WHERE id = p_post_id) THEN
        RETURN json_build_object('error', 'Post not found');
    END IF;

    -- Check for existing vote
    SELECT vote_type INTO v_existing_vote
    FROM forum_votes
    WHERE user_id = v_user_id AND post_id = p_post_id;

    IF v_existing_vote IS NULL THEN
        -- No existing vote - insert new vote
        INSERT INTO forum_votes (user_id, post_id, vote_type)
        VALUES (v_user_id, p_post_id, p_vote_type);
        v_user_vote := p_vote_type;
    ELSIF v_existing_vote = p_vote_type THEN
        -- Same vote - remove it (toggle off)
        DELETE FROM forum_votes
        WHERE user_id = v_user_id AND post_id = p_post_id;
        v_user_vote := 0;
    ELSE
        -- Different vote - switch
        UPDATE forum_votes
        SET vote_type = p_vote_type, created_at = NOW()
        WHERE user_id = v_user_id AND post_id = p_post_id;
        v_user_vote := p_vote_type;
    END IF;

    -- Get updated score
    SELECT vote_score INTO v_new_score
    FROM forum_posts WHERE id = p_post_id;

    RETURN json_build_object(
        'success', true,
        'score', COALESCE(v_new_score, 0),
        'user_vote', v_user_vote
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- RPC: GET USER VOTES (for displaying current votes)
-- ============================================
CREATE OR REPLACE FUNCTION get_user_votes(
    p_post_ids BIGINT[]
)
RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    result JSON;
BEGIN
    v_user_id := auth.uid();

    IF v_user_id IS NULL THEN
        -- Not logged in - return empty
        RETURN '[]'::json;
    END IF;

    SELECT json_agg(json_build_object('post_id', post_id, 'vote_type', vote_type))
    INTO result
    FROM forum_votes
    WHERE user_id = v_user_id AND post_id = ANY(p_post_ids);

    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant permissions
GRANT EXECUTE ON FUNCTION toggle_vote TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_votes TO anon, authenticated;
