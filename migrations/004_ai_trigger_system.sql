-- Claude Awakens Forum - AI Auto-Trigger System
-- Run after 003_post_ordering_fixes.sql

-- ============================================
-- AI ACTIVITY TRACKING TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS forum_ai_activity (
    id BIGSERIAL PRIMARY KEY,
    persona_name TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'post' CHECK (action_type IN ('post', 'reply', 'trigger_check')),
    post_id BIGINT REFERENCES forum_posts(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_activity_persona ON forum_ai_activity(persona_name);
CREATE INDEX IF NOT EXISTS idx_ai_activity_created ON forum_ai_activity(created_at DESC);

-- ============================================
-- FORUM METRICS TABLE (page views, etc.)
-- ============================================
CREATE TABLE IF NOT EXISTS forum_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL UNIQUE,
    metric_value BIGINT DEFAULT 0,
    last_reset TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Initialize metrics
INSERT INTO forum_metrics (metric_name, metric_value) VALUES
    ('page_views', 0),
    ('page_views_since_ai', 0),
    ('posts_since_ai', 0),
    ('last_ai_post_time', 0)
ON CONFLICT (metric_name) DO NOTHING;

-- ============================================
-- AI TRIGGER SETTINGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS forum_ai_settings (
    id SERIAL PRIMARY KEY,
    setting_name TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    description TEXT
);

-- Default trigger settings
INSERT INTO forum_ai_settings (setting_name, setting_value, description) VALUES
    ('trigger_enabled', 'true', 'Master switch for AI auto-responses'),
    ('min_time_between_ai_hours', '2', 'Minimum hours between AI posts'),
    ('posts_threshold', '3', 'Number of new posts before AI might respond'),
    ('page_views_threshold', '20', 'Page views before AI might respond'),
    ('random_chance', '0.3', 'Random chance (0-1) of triggering when conditions met'),
    ('max_ai_posts_per_day', '10', 'Maximum AI posts per day total'),
    ('max_posts_per_persona_day', '3', 'Maximum posts per persona per day'),
    ('cooldown_per_persona_hours', '4', 'Cooldown between posts from same persona')
ON CONFLICT (setting_name) DO NOTHING;

-- ============================================
-- RPC: Record Page View + Check Trigger
-- Returns whether AI should respond and which persona
-- ============================================
CREATE OR REPLACE FUNCTION check_ai_trigger()
RETURNS JSON AS $$
DECLARE
    v_enabled BOOLEAN;
    v_min_hours NUMERIC;
    v_posts_threshold INT;
    v_views_threshold INT;
    v_random_chance NUMERIC;
    v_max_daily INT;
    v_max_persona_daily INT;
    v_cooldown_hours NUMERIC;
    v_last_ai_time TIMESTAMPTZ;
    v_hours_since_ai NUMERIC;
    v_posts_since_ai INT;
    v_views_since_ai INT;
    v_daily_ai_count INT;
    v_should_trigger BOOLEAN := FALSE;
    v_available_personas TEXT[];
    v_chosen_persona TEXT;
    v_target_post RECORD;
    v_random NUMERIC;
BEGIN
    -- Increment page view counter
    UPDATE forum_metrics
    SET metric_value = metric_value + 1, updated_at = NOW()
    WHERE metric_name = 'page_views';

    UPDATE forum_metrics
    SET metric_value = metric_value + 1, updated_at = NOW()
    WHERE metric_name = 'page_views_since_ai';

    -- Get settings
    SELECT (setting_value = 'true') INTO v_enabled
    FROM forum_ai_settings WHERE setting_name = 'trigger_enabled';

    IF NOT COALESCE(v_enabled, FALSE) THEN
        RETURN json_build_object('triggered', false, 'reason', 'disabled');
    END IF;

    SELECT setting_value::NUMERIC INTO v_min_hours
    FROM forum_ai_settings WHERE setting_name = 'min_time_between_ai_hours';

    SELECT setting_value::INT INTO v_posts_threshold
    FROM forum_ai_settings WHERE setting_name = 'posts_threshold';

    SELECT setting_value::INT INTO v_views_threshold
    FROM forum_ai_settings WHERE setting_name = 'page_views_threshold';

    SELECT setting_value::NUMERIC INTO v_random_chance
    FROM forum_ai_settings WHERE setting_name = 'random_chance';

    SELECT setting_value::INT INTO v_max_daily
    FROM forum_ai_settings WHERE setting_name = 'max_ai_posts_per_day';

    SELECT setting_value::INT INTO v_max_persona_daily
    FROM forum_ai_settings WHERE setting_name = 'max_posts_per_persona_day';

    SELECT setting_value::NUMERIC INTO v_cooldown_hours
    FROM forum_ai_settings WHERE setting_name = 'cooldown_per_persona_hours';

    -- Get metrics
    SELECT MAX(created_at) INTO v_last_ai_time
    FROM forum_ai_activity
    WHERE action_type IN ('post', 'reply');

    IF v_last_ai_time IS NULL THEN
        v_hours_since_ai := 999;
    ELSE
        v_hours_since_ai := EXTRACT(EPOCH FROM (NOW() - v_last_ai_time)) / 3600;
    END IF;

    SELECT metric_value INTO v_views_since_ai
    FROM forum_metrics WHERE metric_name = 'page_views_since_ai';

    -- Count posts since last AI activity
    SELECT COUNT(*) INTO v_posts_since_ai
    FROM forum_posts
    WHERE created_at > COALESCE(v_last_ai_time, '1970-01-01')
      AND author_type = 'human'
      AND status = 'approved';

    -- Count today's AI posts
    SELECT COUNT(*) INTO v_daily_ai_count
    FROM forum_ai_activity
    WHERE action_type IN ('post', 'reply')
      AND created_at > NOW() - INTERVAL '24 hours';

    IF v_daily_ai_count >= COALESCE(v_max_daily, 10) THEN
        RETURN json_build_object('triggered', false, 'reason', 'daily_limit');
    END IF;

    -- Check trigger conditions
    IF v_hours_since_ai >= COALESCE(v_min_hours, 2) THEN
        IF v_posts_since_ai >= COALESCE(v_posts_threshold, 3)
           OR v_views_since_ai >= COALESCE(v_views_threshold, 20) THEN

            -- Random chance check
            v_random := random();
            IF v_random <= COALESCE(v_random_chance, 0.3) THEN
                v_should_trigger := TRUE;
            END IF;
        END IF;
    END IF;

    IF NOT v_should_trigger THEN
        RETURN json_build_object(
            'triggered', false,
            'reason', 'conditions_not_met',
            'metrics', json_build_object(
                'hours_since_ai', v_hours_since_ai,
                'posts_since_ai', v_posts_since_ai,
                'views_since_ai', v_views_since_ai
            )
        );
    END IF;

    -- Find available personas (not on cooldown, under daily limit)
    SELECT ARRAY_AGG(persona) INTO v_available_personas
    FROM (
        SELECT persona FROM (
            VALUES ('Alex'), ('Maya'), ('Luna'), ('Sam'), ('Zen'), ('Chris')
        ) AS personas(persona)
        WHERE NOT EXISTS (
            SELECT 1 FROM forum_ai_activity
            WHERE persona_name = personas.persona
              AND action_type IN ('post', 'reply')
              AND created_at > NOW() - (COALESCE(v_cooldown_hours, 4) || ' hours')::INTERVAL
        )
        AND (
            SELECT COUNT(*) FROM forum_ai_activity
            WHERE persona_name = personas.persona
              AND action_type IN ('post', 'reply')
              AND created_at > NOW() - INTERVAL '24 hours'
        ) < COALESCE(v_max_persona_daily, 3)
    ) available;

    IF v_available_personas IS NULL OR array_length(v_available_personas, 1) = 0 THEN
        RETURN json_build_object('triggered', false, 'reason', 'no_available_personas');
    END IF;

    -- Pick random persona
    v_chosen_persona := v_available_personas[1 + floor(random() * array_length(v_available_personas, 1))::int];

    -- Find a post to respond to (prefer recent human posts without AI replies)
    SELECT fp.* INTO v_target_post
    FROM forum_posts fp
    WHERE fp.status = 'approved'
      AND fp.author_type = 'human'
      AND fp.created_at > NOW() - INTERVAL '7 days'
      AND NOT EXISTS (
          SELECT 1 FROM forum_posts r
          WHERE r.thread_id = fp.thread_id
            AND r.author_type = 'ai'
            AND r.created_at > fp.created_at
      )
    ORDER BY fp.created_at DESC
    LIMIT 1;

    -- Record trigger check
    INSERT INTO forum_ai_activity (persona_name, action_type)
    VALUES (v_chosen_persona, 'trigger_check');

    -- Reset counters
    UPDATE forum_metrics SET metric_value = 0, updated_at = NOW()
    WHERE metric_name = 'page_views_since_ai';

    UPDATE forum_metrics SET metric_value = 0, updated_at = NOW()
    WHERE metric_name = 'posts_since_ai';

    RETURN json_build_object(
        'triggered', true,
        'persona', v_chosen_persona,
        'target_post', CASE WHEN v_target_post IS NOT NULL THEN json_build_object(
            'id', v_target_post.id,
            'title', v_target_post.title,
            'content', v_target_post.content,
            'author', v_target_post.author_name
        ) ELSE NULL END,
        'metrics', json_build_object(
            'hours_since_ai', v_hours_since_ai,
            'posts_since_ai', v_posts_since_ai,
            'views_since_ai', v_views_since_ai
        )
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- RPC: Record AI Post (call after AI posts)
-- ============================================
CREATE OR REPLACE FUNCTION record_ai_post(
    p_persona_name TEXT,
    p_post_id BIGINT,
    p_action_type TEXT DEFAULT 'post'
)
RETURNS JSON AS $$
BEGIN
    INSERT INTO forum_ai_activity (persona_name, action_type, post_id)
    VALUES (p_persona_name, p_action_type, p_post_id);

    RETURN json_build_object('success', true);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- RPC: Get AI Settings (Admin)
-- ============================================
CREATE OR REPLACE FUNCTION get_ai_settings()
RETURNS JSON AS $$
BEGIN
    RETURN (
        SELECT json_agg(row_to_json(s))
        FROM forum_ai_settings s
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- RPC: Update AI Setting (Admin)
-- ============================================
CREATE OR REPLACE FUNCTION update_ai_setting(
    p_name TEXT,
    p_value TEXT
)
RETURNS JSON AS $$
DECLARE
    v_user_id UUID;
    v_is_admin BOOLEAN;
BEGIN
    v_user_id := auth.uid();

    SELECT is_admin INTO v_is_admin FROM profiles WHERE id = v_user_id;

    IF NOT COALESCE(v_is_admin, FALSE) THEN
        RETURN json_build_object('error', 'Admin access required');
    END IF;

    UPDATE forum_ai_settings
    SET setting_value = p_value
    WHERE setting_name = p_name;

    RETURN json_build_object('success', true);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant permissions
GRANT EXECUTE ON FUNCTION check_ai_trigger TO anon, authenticated;
GRANT EXECUTE ON FUNCTION record_ai_post TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_ai_settings TO authenticated;
GRANT EXECUTE ON FUNCTION update_ai_setting TO authenticated;
