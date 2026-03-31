"""
Alpha Edge AI — Supabase Auth Module
Handles user registration, login, logout, and per-user data isolation.
Requires Supabase project with Auth enabled.
"""
import streamlit as st
import requests
import json

# ── Supabase Auth Endpoints ────────────────────────────────
def _get_secret(key, default=""):
    try:
        val = st.secrets.get(key, "")
        if val: return str(val).strip()
    except Exception:
        pass
    import os
    return os.getenv(key, default).strip()

def _sb_url():
    return _get_secret("SUPABASE_URL")

def _sb_key():
    return _get_secret("SUPABASE_KEY")

def _auth_url():
    return f"{_sb_url()}/auth/v1"

def _auth_headers():
    return {
        "apikey": _sb_key(),
        "Content-Type": "application/json",
    }

def _auth_headers_with_token(access_token):
    return {
        "apikey": _sb_key(),
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

# ── Core Auth Functions ────────────────────────────────────

def sign_up(email: str, password: str) -> dict:
    """Register a new user. Returns {"user": ..., "session": ...} or {"error": ...}."""
    try:
        r = requests.post(
            f"{_auth_url()}/signup",
            headers=_auth_headers(),
            json={"email": email, "password": password},
            timeout=10,
        )
        data = r.json()
        if r.status_code in (200, 201):
            return {"success": True, "data": data}
        else:
            msg = data.get("error_description") or data.get("msg") or data.get("message") or str(data)
            return {"success": False, "error": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sign_in(email: str, password: str) -> dict:
    """Login an existing user. Returns session with access_token."""
    try:
        r = requests.post(
            f"{_auth_url()}/token?grant_type=password",
            headers=_auth_headers(),
            json={"email": email, "password": password},
            timeout=10,
        )
        data = r.json()
        if r.status_code == 200 and "access_token" in data:
            return {"success": True, "data": data}
        else:
            msg = data.get("error_description") or data.get("msg") or data.get("message") or "Invalid credentials"
            return {"success": False, "error": msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_user(access_token: str) -> dict:
    """Get current user info from access token."""
    try:
        r = requests.get(
            f"{_auth_url()}/user",
            headers=_auth_headers_with_token(access_token),
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def sign_out(access_token: str):
    """Logout the user."""
    try:
        requests.post(
            f"{_auth_url()}/logout",
            headers=_auth_headers_with_token(access_token),
            timeout=10,
        )
    except Exception:
        pass


def refresh_token(refresh_tok: str) -> dict:
    """Refresh an expired access token."""
    try:
        r = requests.post(
            f"{_auth_url()}/token?grant_type=refresh_token",
            headers=_auth_headers(),
            json={"refresh_token": refresh_tok},
            timeout=10,
        )
        data = r.json()
        if r.status_code == 200 and "access_token" in data:
            return {"success": True, "data": data}
    except Exception:
        pass
    return {"success": False}


# ── User Settings (per-user data in Supabase) ─────────────

def _rest_headers(access_token=None):
    """Headers for Supabase REST API with user's JWT for RLS."""
    h = {
        "apikey": _sb_key(),
        "Authorization": f"Bearer {access_token or _sb_key()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    return h


def get_user_settings(user_id: str, access_token: str = None) -> dict:
    """Fetch user settings from user_settings table."""
    try:
        url = f"{_sb_url()}/rest/v1/user_settings?user_id=eq.{user_id}&select=*"
        r = requests.get(url, headers=_rest_headers(access_token), timeout=10)
        if r.status_code == 200:
            rows = r.json()
            if rows:
                return rows[0]
    except Exception:
        pass
    return {}


def save_user_settings(user_id: str, settings: dict, access_token: str = None) -> bool:
    """Upsert user settings."""
    try:
        data = {"user_id": user_id, **settings}
        url = f"{_sb_url()}/rest/v1/user_settings"
        headers = _rest_headers(access_token)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        r = requests.post(url, headers=headers, json=data, timeout=10)
        return r.status_code in (200, 201)
    except Exception:
        return False


# ── Session State Helpers ──────────────────────────────────

def is_logged_in() -> bool:
    """Check if user is currently logged in."""
    return bool(st.session_state.get("auth_access_token"))


def get_current_user_id() -> str:
    """Get the current user's ID."""
    return st.session_state.get("auth_user_id", "")


def get_current_email() -> str:
    """Get the current user's email."""
    return st.session_state.get("auth_email", "")


def store_session(data: dict):
    """Store auth session in Streamlit session state."""
    st.session_state["auth_access_token"] = data.get("access_token", "")
    st.session_state["auth_refresh_token"] = data.get("refresh_token", "")
    user = data.get("user", {})
    st.session_state["auth_user_id"] = user.get("id", "")
    st.session_state["auth_email"] = user.get("email", "")


def clear_session():
    """Clear auth session."""
    for key in ["auth_access_token", "auth_refresh_token", "auth_user_id", "auth_email"]:
        st.session_state.pop(key, None)


# ── Auth UI Component ──────────────────────────────────────

def render_auth_page():
    """Render the login/register page. Returns True if authenticated, False otherwise."""
    if is_logged_in():
        return True

    # Check if Supabase is configured
    if not _sb_url() or not _sb_key():
        st.warning("Supabase not configured. Running in single-user mode.")
        return True  # fallback to single-user

    # Auth page styling
    st.markdown("""<style>
    .auth-container{max-width:420px;margin:60px auto;padding:40px;
    background:linear-gradient(135deg,#0d1117 0%,#111827 100%);
    border:1px solid rgba(0,212,170,0.15);border-radius:16px;text-align:center;}
    .auth-logo{font-size:28px;font-weight:800;margin-bottom:4px;}
    .auth-logo span{color:#00d4aa;}
    .auth-sub{color:#8b9ab0;font-size:14px;margin-bottom:32px;}
    div[data-testid="stTabs"] button{font-weight:600;}
    </style>""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-top:40px;margin-bottom:20px;">
            <div class="auth-logo">◈ Alpha<span>Edge</span> AI</div>
            <div class="auth-sub">AI-Powered Forex & Gold Trading Terminal</div>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔐 Login", "📝 Register"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="your@email.com", key="login_email")
                password = st.text_input("Password", type="password", placeholder="Your password", key="login_pw")
                submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

                if submitted:
                    if not email or not password:
                        st.error("Please fill in all fields.")
                    else:
                        with st.spinner("Logging in..."):
                            result = sign_in(email, password)
                        if result["success"]:
                            store_session(result["data"])
                            st.success(f"Welcome back! 🎉")
                            st.rerun()
                        else:
                            st.error(f"Login failed: {result['error']}")

        with tab_register:
            with st.form("register_form"):
                reg_email = st.text_input("Email", placeholder="your@email.com", key="reg_email")
                reg_pw = st.text_input("Password", type="password", placeholder="Min 6 characters", key="reg_pw")
                reg_pw2 = st.text_input("Confirm Password", type="password", placeholder="Repeat password", key="reg_pw2")
                reg_submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")

                if reg_submitted:
                    if not reg_email or not reg_pw:
                        st.error("Please fill in all fields.")
                    elif len(reg_pw) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif reg_pw != reg_pw2:
                        st.error("Passwords don't match.")
                    else:
                        with st.spinner("Creating account..."):
                            result = sign_up(reg_email, reg_pw)
                        if result["success"]:
                            # Some Supabase configs require email confirmation
                            data = result["data"]
                            if data.get("access_token"):
                                store_session(data)
                                st.success("Account created! Welcome! 🎉")
                                st.rerun()
                            else:
                                st.success("Account created! Please check your email to confirm, then login.")
                        else:
                            st.error(f"Registration failed: {result['error']}")

        st.markdown("---")
        st.markdown("<div style='text-align:center;color:#8b9ab0;font-size:12px;'>"
                    "By signing up, you agree to our Terms of Service.<br>"
                    "© 2026 Alpha Edge AI</div>", unsafe_allow_html=True)

    st.stop()
    return False
