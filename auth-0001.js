// Claude Awakens - Auth System
// Handles user authentication via Supabase

const AUTH_TOKEN_KEY = 'ca_auth_token';
const USER_KEY = 'ca_user';

class Auth {
  constructor() {
    this.user = null;
    this.token = null;
    this.apiBase = '/.netlify/functions/supabase-proxy';
  }

  async init() {
    this.token = localStorage.getItem(AUTH_TOKEN_KEY);
    const userStr = localStorage.getItem(USER_KEY);
    this.user = userStr ? JSON.parse(userStr) : null;

    if (!this.token) return;

    // Validate token
    if (this.isTokenExpired()) {
      this.clearAuth();
      return;
    }

    // Fetch profile
    try {
      const resp = await this.call('getProfile', {});
      if (resp.data) {
        this.user = { ...this.user, ...resp.data };
        localStorage.setItem(USER_KEY, JSON.stringify(this.user));
      }
    } catch (e) {
      console.warn('Profile fetch failed:', e);
    }
  }

  isTokenExpired() {
    if (!this.token) return true;
    try {
      const [, payload] = this.token.split('.');
      const { exp } = JSON.parse(atob(payload));
      return !exp || exp <= Math.floor(Date.now() / 1000);
    } catch {
      return true;
    }
  }

  async call(action, payload = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const resp = await fetch(this.apiBase, {
      method: 'POST',
      headers,
      body: JSON.stringify({ action, payload })
    });

    const result = await resp.json();
    if (result.error) {
      throw new Error(result.error);
    }
    return result;
  }

  async signUp(email, password, displayName) {
    const result = await this.call('signUp', {
      email,
      password,
      display_name: displayName,
      redirectTo: window.location.origin
    });

    return result;
  }

  async signIn(email, password) {
    const result = await this.call('signIn', { email, password });

    if (result.data?.session) {
      this.token = result.data.session.access_token;
      this.user = result.data.user;
      localStorage.setItem(AUTH_TOKEN_KEY, this.token);
      localStorage.setItem(USER_KEY, JSON.stringify(this.user));

      // Fetch profile for display_name
      try {
        const profile = await this.call('getProfile', {});
        if (profile.data) {
          this.user = { ...this.user, ...profile.data };
          localStorage.setItem(USER_KEY, JSON.stringify(this.user));
        }
      } catch (e) {}
    }

    return this.user;
  }

  async signOut() {
    try {
      await this.call('signOut', {});
    } catch (_) {}
    this.clearAuth();
    window.location.reload();
  }

  clearAuth() {
    this.user = null;
    this.token = null;
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }

  isAuthenticated() {
    return !!this.user && !!this.token && !this.isTokenExpired();
  }

  getUser() {
    return this.user;
  }

  getDisplayName() {
    if (!this.user) return null;
    return this.user.display_name || this.user.email?.split('@')[0] || 'User';
  }

  isAdmin() {
    return this.user?.is_admin === true;
  }

  isModerator() {
    return this.user?.is_moderator === true || this.isAdmin();
  }
}

// Global instance
window.auth = new Auth();
