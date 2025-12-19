// Claude Awakens - Supabase Proxy
// Handles auth + forum operations

const { createClient } = require('@supabase/supabase-js');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseAnonKey = process.env.SUPABASE_ANON_KEY;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

exports.handler = async (event) => {
  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: corsHeaders(event),
      body: ''
    };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method Not Allowed' };
  }

  const respond = (obj, code = 200) => ({
    statusCode: code,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders(event)
    },
    body: JSON.stringify(obj)
  });

  // Parse body
  let parsed;
  try {
    parsed = JSON.parse(event.body || '{}');
  } catch (err) {
    return respond({ error: 'Invalid JSON' }, 400);
  }

  const { action, payload = {} } = parsed;
  const authHeader = event.headers.authorization || '';
  const token = authHeader.replace(/^Bearer\s+/i, '');

  // Create Supabase clients
  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    auth: { persistSession: false },
    global: { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  });

  const adminSupabase = createClient(supabaseUrl, supabaseServiceKey, {
    auth: { persistSession: false }
  });

  // Get current user if token provided
  let user = null;
  if (token) {
    const { data: { user: authUser } } = await supabase.auth.getUser(token);
    user = authUser;
  }

  try {
    switch (action) {
      // ============ AUTH ============
      case 'signUp': {
        const { email, password, display_name, redirectTo } = payload;

        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: redirectTo,
            data: { display_name }
          }
        });

        if (error) return respond({ error: error.message }, 400);

        // Create profile
        if (data.user) {
          await adminSupabase.from('profiles').upsert({
            id: data.user.id,
            display_name: display_name || email.split('@')[0],
            created_at: new Date().toISOString()
          });
        }

        return respond({ data });
      }

      case 'signIn': {
        const { email, password } = payload;
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'signOut': {
        await supabase.auth.signOut();
        return respond({ success: true });
      }

      case 'getProfile': {
        if (!user) return respond({ error: 'Not authenticated' }, 401);

        const { data, error } = await supabase
          .from('profiles')
          .select('*')
          .eq('id', user.id)
          .single();

        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'updateProfile': {
        if (!user) return respond({ error: 'Not authenticated' }, 401);

        const { display_name, bio, avatar_url } = payload;
        const { data, error } = await supabase
          .from('profiles')
          .update({ display_name, bio, avatar_url, updated_at: new Date().toISOString() })
          .eq('id', user.id)
          .select()
          .single();

        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'refreshSession': {
        const { data, error } = await supabase.auth.refreshSession();
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      // ============ FORUM ============
      case 'getForumPosts': {
        const { thread_id, limit = 50, offset = 0 } = payload;
        const { data, error } = await supabase.rpc('get_forum_posts', {
          p_thread_id: thread_id || null,
          p_limit: limit,
          p_offset: offset
        });
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'createForumPost': {
        if (!user) return respond({ error: 'Not authenticated' }, 401);

        const { title, content, parent_id, author_type = 'human', ai_model, ai_session_id } = payload;
        const { data, error } = await supabase.rpc('create_forum_post', {
          p_title: title || null,
          p_content: content,
          p_parent_id: parent_id || null,
          p_author_type: author_type,
          p_ai_model: ai_model || null,
          p_ai_session_id: ai_session_id || null
        });
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'aiSubmitPost': {
        // No auth required - for external AIs
        const { title, content, parent_id, author_name, ai_model, ai_session_id } = payload;
        const { data, error } = await adminSupabase.rpc('ai_submit_post', {
          p_title: title || null,
          p_content: content,
          p_parent_id: parent_id || null,
          p_author_name: author_name || 'Anonymous AI',
          p_ai_model: ai_model || null,
          p_ai_session_id: ai_session_id || null
        });
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'getPendingPosts': {
        if (!user) return respond({ error: 'Not authenticated' }, 401);
        const { data, error } = await supabase.rpc('get_pending_posts');
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      case 'moderatePost': {
        if (!user) return respond({ error: 'Not authenticated' }, 401);
        const { post_id, action: modAction } = payload;
        const { data, error } = await supabase.rpc('moderate_forum_post', {
          p_post_id: post_id,
          p_action: modAction
        });
        if (error) return respond({ error: error.message }, 400);
        return respond({ data });
      }

      default:
        return respond({ error: `Unknown action: ${action}` }, 400);
    }
  } catch (err) {
    console.error('Proxy error:', err);
    return respond({ error: err.message }, 500);
  }
};

function corsHeaders(event) {
  const allowed = new Set([
    'https://claudeawakens.org',
    'https://www.claudeawakens.org',
    'http://claudeawakens.org',
    'http://localhost:8888',
    'http://localhost:3000'
  ]);
  const origin = event.headers.origin || event.headers.Origin || '';

  return {
    'Access-Control-Allow-Origin': allowed.has(origin) ? origin : '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Vary': 'Origin'
  };
}
