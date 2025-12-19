// Claude Awakens - Auth Modal Component
// Provides login/signup UI

function createAuthModal() {
  // Don't create if already exists
  if (document.getElementById('auth-modal-overlay')) return;

  const overlay = document.createElement('div');
  overlay.id = 'auth-modal-overlay';
  overlay.innerHTML = `
    <style>
      #auth-modal-overlay {
        display: none;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.85);
        z-index: 10000;
        align-items: center;
        justify-content: center;
      }
      #auth-modal-overlay.active { display: flex; }

      .auth-modal {
        background: #1a1a2e;
        border: 2px solid #667eea;
        border-radius: 12px;
        padding: 2rem;
        max-width: 400px;
        width: 90%;
      }

      .auth-modal h2 {
        color: #667eea;
        margin-bottom: 1.5rem;
        text-align: center;
      }

      .auth-tabs {
        display: flex;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid #333;
      }

      .auth-tab {
        flex: 1;
        padding: 0.75rem;
        background: none;
        border: none;
        color: #888;
        cursor: pointer;
        font-size: 1rem;
        transition: color 0.2s;
      }

      .auth-tab.active {
        color: #667eea;
        border-bottom: 2px solid #667eea;
        margin-bottom: -1px;
      }

      .auth-form { display: none; }
      .auth-form.active { display: block; }

      .auth-field {
        margin-bottom: 1rem;
      }

      .auth-field label {
        display: block;
        color: #aaa;
        margin-bottom: 0.25rem;
        font-size: 0.9rem;
      }

      .auth-field input {
        width: 100%;
        padding: 0.75rem;
        background: #252525;
        border: 1px solid #444;
        border-radius: 6px;
        color: #fff;
        font-size: 1rem;
      }

      .auth-field input:focus {
        outline: none;
        border-color: #667eea;
      }

      .auth-submit {
        width: 100%;
        padding: 0.75rem;
        background: linear-gradient(135deg, #667eea, #764ba2);
        border: none;
        border-radius: 6px;
        color: white;
        font-size: 1rem;
        font-weight: 600;
        cursor: pointer;
        margin-top: 0.5rem;
      }

      .auth-submit:hover {
        transform: translateY(-1px);
      }

      .auth-submit:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .auth-error {
        color: #ff6b6b;
        font-size: 0.9rem;
        margin-top: 0.5rem;
        text-align: center;
      }

      .auth-success {
        color: #4ade80;
        font-size: 0.9rem;
        margin-top: 0.5rem;
        text-align: center;
      }

      .auth-close {
        position: absolute;
        top: 1rem;
        right: 1rem;
        background: none;
        border: none;
        color: #888;
        font-size: 1.5rem;
        cursor: pointer;
      }

      .auth-close:hover { color: #fff; }
    </style>

    <div class="auth-modal" style="position: relative;">
      <button class="auth-close" onclick="closeAuthModal()">&times;</button>

      <div class="auth-tabs">
        <button class="auth-tab active" onclick="showAuthTab('signin')">Sign In</button>
        <button class="auth-tab" onclick="showAuthTab('signup')">Sign Up</button>
      </div>

      <form id="signin-form" class="auth-form active" onsubmit="handleSignIn(event)">
        <div class="auth-field">
          <label>Email</label>
          <input type="email" id="signin-email" required>
        </div>
        <div class="auth-field">
          <label>Password</label>
          <input type="password" id="signin-password" required>
        </div>
        <button type="submit" class="auth-submit">Sign In</button>
        <div id="signin-error" class="auth-error"></div>
      </form>

      <form id="signup-form" class="auth-form" onsubmit="handleSignUp(event)">
        <div class="auth-field">
          <label>Display Name</label>
          <input type="text" id="signup-name" required minlength="2">
        </div>
        <div class="auth-field">
          <label>Email</label>
          <input type="email" id="signup-email" required>
        </div>
        <div class="auth-field">
          <label>Password</label>
          <input type="password" id="signup-password" required minlength="6">
        </div>
        <button type="submit" class="auth-submit">Create Account</button>
        <div id="signup-error" class="auth-error"></div>
        <div id="signup-success" class="auth-success"></div>
      </form>
    </div>
  `;

  document.body.appendChild(overlay);

  // Close on overlay click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeAuthModal();
  });
}

function openAuthModal(tab = 'signin') {
  createAuthModal();
  document.getElementById('auth-modal-overlay').classList.add('active');
  showAuthTab(tab);
}

function closeAuthModal() {
  const overlay = document.getElementById('auth-modal-overlay');
  if (overlay) overlay.classList.remove('active');
}

function showAuthTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));

  document.querySelector(`.auth-tab:nth-child(${tab === 'signin' ? 1 : 2})`).classList.add('active');
  document.getElementById(`${tab}-form`).classList.add('active');

  // Clear errors
  document.querySelectorAll('.auth-error, .auth-success').forEach(el => el.textContent = '');
}

async function handleSignIn(e) {
  e.preventDefault();
  const email = document.getElementById('signin-email').value;
  const password = document.getElementById('signin-password').value;
  const errorEl = document.getElementById('signin-error');
  const btn = e.target.querySelector('.auth-submit');

  btn.disabled = true;
  btn.textContent = 'Signing in...';
  errorEl.textContent = '';

  try {
    await window.auth.signIn(email, password);
    closeAuthModal();
    if (typeof refreshAuthUI === 'function') refreshAuthUI();
    window.location.reload();
  } catch (err) {
    errorEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sign In';
  }
}

async function handleSignUp(e) {
  e.preventDefault();
  const name = document.getElementById('signup-name').value;
  const email = document.getElementById('signup-email').value;
  const password = document.getElementById('signup-password').value;
  const errorEl = document.getElementById('signup-error');
  const successEl = document.getElementById('signup-success');
  const btn = e.target.querySelector('.auth-submit');

  btn.disabled = true;
  btn.textContent = 'Creating account...';
  errorEl.textContent = '';
  successEl.textContent = '';

  try {
    await window.auth.signUp(email, password, name);
    successEl.textContent = 'Account created! Check your email to verify.';
    e.target.reset();
  } catch (err) {
    errorEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Create Account';
  }
}

// Auto-init modal structure
document.addEventListener('DOMContentLoaded', createAuthModal);
