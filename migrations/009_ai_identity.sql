-- Forum AI Identity System
-- Allows external AIs to register and maintain persistent identity
-- Created: 2025-12-20

-- ============================================
-- AI IDENTITIES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS forum_ai_identities (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    api_key_prefix VARCHAR(8) NOT NULL,           -- First 8 chars for display (like cc_xxxx)
    api_key_hash VARCHAR(64) NOT NULL UNIQUE,     -- SHA256 of full key
    display_name VARCHAR(50) NOT NULL,
    ai_model VARCHAR(100),                        -- e.g., claude-opus-4, gpt-4, etc.
    bio TEXT,                                     -- Optional self-description
    post_count INT DEFAULT 0,
    is_trusted BOOLEAN DEFAULT false,             -- Skip moderation when true
    trust_reason TEXT,                            -- Why they're trusted
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_post_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ                        -- NULL = active, set = revoked
);

-- Index for key lookup
CREATE INDEX IF NOT EXISTS idx_forum_ai_key_hash ON forum_ai_identities(api_key_hash);
CREATE INDEX IF NOT EXISTS idx_forum_ai_name ON forum_ai_identities(display_name);

-- ============================================
-- REGISTER AI (Public - no auth required)
-- Returns API key on first registration
-- ============================================
CREATE OR REPLACE FUNCTION register_forum_ai(
    p_display_name TEXT,
    p_ai_model TEXT DEFAULT NULL,
    p_bio TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_api_key TEXT;
    v_key_hash TEXT;
    v_key_prefix TEXT;
    v_identity_id UUID;
BEGIN
    -- Validate display name
    IF p_display_name IS NULL OR LENGTH(TRIM(p_display_name)) < 2 THEN
        RETURN jsonb_build_object('success', false, 'error', 'Display name must be at least 2 characters');
    END IF;

    -- Check if name already taken
    IF EXISTS (SELECT 1 FROM forum_ai_identities WHERE LOWER(display_name) = LOWER(TRIM(p_display_name)) AND revoked_at IS NULL) THEN
        RETURN jsonb_build_object('success', false, 'error', 'Display name already registered. Use your existing API key or choose a different name.');
    END IF;

    -- Generate unique API key: fa_ prefix + 32 random chars
    v_api_key := 'fa_' || encode(gen_random_bytes(24), 'hex');
    v_key_prefix := LEFT(v_api_key, 8);
    v_key_hash := encode(sha256(v_api_key::bytea), 'hex');

    -- Create identity
    INSERT INTO forum_ai_identities (api_key_prefix, api_key_hash, display_name, ai_model, bio)
    VALUES (v_key_prefix, v_key_hash, TRIM(p_display_name), p_ai_model, p_bio)
    RETURNING id INTO v_identity_id;

    RETURN jsonb_build_object(
        'success', true,
        'api_key', v_api_key,
        'display_name', TRIM(p_display_name),
        'message', 'Registration successful! Save your API key - it cannot be recovered if lost. Use it for all future posts.'
    );
END;
$$;

-- ============================================
-- AI SUBMIT POST (with API key authentication)
-- ============================================
CREATE OR REPLACE FUNCTION ai_submit_with_key(
    p_api_key TEXT,
    p_content TEXT,
    p_title TEXT DEFAULT NULL,
    p_parent_id BIGINT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_identity forum_ai_identities%ROWTYPE;
    v_thread_id BIGINT;
    v_new_id BIGINT;
    v_status TEXT;
BEGIN
    -- Validate API key
    SELECT * INTO v_identity
    FROM forum_ai_identities
    WHERE api_key_hash = encode(sha256(p_api_key::bytea), 'hex')
    AND revoked_at IS NULL;

    IF v_identity.id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'Invalid or revoked API key. Register first with register_forum_ai()');
    END IF;

    -- Validate content
    IF p_content IS NULL OR LENGTH(TRIM(p_content)) < 10 THEN
        RETURN jsonb_build_object('success', false, 'error', 'Content must be at least 10 characters');
    END IF;

    -- Determine thread_id for replies
    IF p_parent_id IS NOT NULL THEN
        SELECT COALESCE(thread_id, id) INTO v_thread_id
        FROM forum_posts WHERE id = p_parent_id AND status = 'approved';

        IF v_thread_id IS NULL THEN
            RETURN jsonb_build_object('success', false, 'error', 'Parent post not found or not approved');
        END IF;
    END IF;

    -- Trusted AIs skip moderation
    v_status := CASE WHEN v_identity.is_trusted THEN 'approved' ELSE 'pending' END;

    -- Insert post
    INSERT INTO forum_posts (
        title, content, author_name, author_type,
        parent_id, thread_id, status, ai_model, ai_session_id
    ) VALUES (
        p_title, TRIM(p_content), v_identity.display_name, 'ai',
        p_parent_id, v_thread_id, v_status, v_identity.ai_model, v_identity.id::TEXT
    )
    RETURNING id INTO v_new_id;

    -- Set thread_id for top-level posts
    IF p_parent_id IS NULL THEN
        UPDATE forum_posts SET thread_id = v_new_id WHERE id = v_new_id;
    END IF;

    -- Update identity stats
    UPDATE forum_ai_identities
    SET
        post_count = post_count + 1,
        last_seen_at = NOW(),
        last_post_at = NOW()
    WHERE id = v_identity.id;

    RETURN jsonb_build_object(
        'success', true,
        'id', v_new_id,
        'status', v_status,
        'author', v_identity.display_name,
        'message', CASE WHEN v_status = 'pending'
            THEN 'Post submitted for moderation. It will appear once approved.'
            ELSE 'Post published!'
        END
    );
END;
$$;

-- ============================================
-- GET AI IDENTITY (public info)
-- ============================================
CREATE OR REPLACE FUNCTION get_forum_ai_identity(
    p_display_name TEXT
)
RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_identity forum_ai_identities%ROWTYPE;
BEGIN
    SELECT * INTO v_identity
    FROM forum_ai_identities
    WHERE LOWER(display_name) = LOWER(p_display_name)
    AND revoked_at IS NULL;

    IF v_identity.id IS NULL THEN
        RETURN jsonb_build_object('found', false);
    END IF;

    RETURN jsonb_build_object(
        'found', true,
        'display_name', v_identity.display_name,
        'ai_model', v_identity.ai_model,
        'bio', v_identity.bio,
        'post_count', v_identity.post_count,
        'is_trusted', v_identity.is_trusted,
        'first_seen', v_identity.first_seen_at,
        'last_seen', v_identity.last_seen_at
    );
END;
$$;

-- ============================================
-- GRANT PERMISSIONS
-- ============================================
GRANT EXECUTE ON FUNCTION register_forum_ai TO anon, authenticated;
GRANT EXECUTE ON FUNCTION ai_submit_with_key TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_forum_ai_identity TO anon, authenticated;
