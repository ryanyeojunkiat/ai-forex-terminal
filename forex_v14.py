"""
ALPHA EDGE AI TERMINAL  v15.0  (Hybrid Engine V3)
Stable direction (H4-first), anti-chase, regime-aware scoring
ADX regime detection, pullback-quality scoring, no grade inflation
Auth: Supabase Auth for multi-user, per-user MT5 & trade data
"""
import os, json, re, uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import streamlit.components.v1 as stc
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

st.set_page_config(page_title="Alpha Edge AI Terminal", page_icon="◈",
                   layout="wide", initial_sidebar_state="expanded")

# ============================================================
# AUTH GATE (Supabase Auth — multi-user)
# ============================================================
try:
    from auth import render_auth_page, is_logged_in, get_current_user_id, get_current_email, clear_session, sign_out, get_user_settings, save_user_settings
    _AUTH_AVAILABLE = True
except ImportError:
    _AUTH_AVAILABLE = False

def _check_auth():
    """Multi-user auth gate using Supabase Auth. Falls back to password if auth module unavailable."""
    if _AUTH_AVAILABLE:
        render_auth_page()  # blocks with st.stop() if not logged in
        return True
    # Fallback: simple password gate
    _pw = os.getenv("APP_PASSWORD", "")
    try:
        _pw = st.secrets.get("APP_PASSWORD", _pw) or _pw
    except Exception:
        pass
    if not _pw:
        return True
    if st.session_state.get("_authenticated"):
        return True
    st.markdown("""<style>
    .login-box{max-width:360px;margin:120px auto;padding:32px;background:#0d1117;
    border:1px solid rgba(0,212,170,0.2);border-radius:12px;text-align:center;}
    .login-title{color:#00d4aa;font-family:'Space Mono',monospace;font-size:18px;margin-bottom:24px;}
    </style>""", unsafe_allow_html=True)
    st.markdown('<div class="login-box"><div class="login-title">◈ AI FOREX TERMINAL</div></div>',
                unsafe_allow_html=True)
    pw_input = st.text_input("Password", type="password", placeholder="Enter access password…")
    if st.button("Enter"):
        if pw_input == _pw:
            st.session_state["_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

_check_auth()

# Helper: get current user ID for per-user data isolation
def _uid():
    """Return current user ID for filtering data. Empty string if no auth."""
    if _AUTH_AVAILABLE and is_logged_in():
        return get_current_user_id()
    return ""

# ============================================================
# CSS
# ============================================================
st.markdown("""<style>
html,body,[data-testid="stAppViewContainer"]{background:#080c10!important;color:#e8edf2!important;font-family:'DM Sans','Segoe UI',sans-serif;}
[data-testid="stSidebar"]{background:#0d1117!important;border-right:1px solid rgba(255,255,255,0.06)!important;}
[data-testid="stHeader"]{background:transparent!important;}
.stButton>button{background:rgba(0,212,170,0.08)!important;border:1px solid rgba(0,212,170,0.25)!important;color:#00d4aa!important;font-family:'Space Mono',monospace!important;border-radius:6px!important;font-size:12px!important;}
.stSelectbox>div>div,.stNumberInput>div>div{background:#131a22!important;border-color:rgba(255,255,255,0.1)!important;color:#e8edf2!important;border-radius:6px!important;}
.panel{background:#0d1117;border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:12px 14px;margin-bottom:10px;}
.mono-title{color:#00d4aa;font-size:11px;font-family:'Space Mono',monospace;letter-spacing:.12em;margin-bottom:8px;}
.kv{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:13px;}
.kv:last-child{border-bottom:none;}
.muted{color:#8b9ab0;}.good{color:#10b981;}.bad{color:#ef4444;}.warn{color:#f59e0b;}.info{color:#0ea5e9;}
.ai-bubble{background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);border-left:3px solid #6366f1;border-radius:8px;padding:12px 14px;margin:8px 0;font-size:12px;color:#c7d2fe;line-height:1.75;}
.grade-aplus{color:#00d4aa;font-weight:700;} .grade-a{color:#10b981;font-weight:700;}
.grade-b{color:#84cc16;font-weight:700;}    .grade-c{color:#f59e0b;font-weight:700;}
.grade-d{color:#ef4444;font-weight:700;}
@keyframes alertpulse{0%,100%{box-shadow:0 0 18px #ef444444;}50%{box-shadow:0 0 36px #ef4444aa;}}
</style>""", unsafe_allow_html=True)

# ============================================================
# CONSTANTS
# ============================================================
APP_VERSION = "V14.0"

# ── Signal alert via browser (sound + notification) ──────────
_SIGNAL_ALERT_JS = """
<script>
(function() {
  // ── Sound: generated beep using Web Audio API ──
  function playAlertBeep(times) {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    var t = ctx.currentTime;
    for (var i = 0; i < times; i++) {
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 880;
      osc.type = "sine";
      gain.gain.setValueAtTime(0.4, t + i*0.35);
      gain.gain.exponentialRampToValueAtTime(0.001, t + i*0.35 + 0.25);
      osc.start(t + i*0.35);
      osc.stop(t + i*0.35 + 0.3);
    }
  }
  // ── Browser notification ──
  function sendNotification(title, body) {
    if (!("Notification" in window)) return;
    if (Notification.permission === "granted") {
      new Notification(title, {body: body, icon: ""});
    } else if (Notification.permission !== "denied") {
      Notification.requestPermission().then(function(p) {
        if (p === "granted") new Notification(title, {body: body});
      });
    }
  }
  // Fire!
  playAlertBeep(BEEP_COUNT);
  sendNotification("ALERT_TITLE", "ALERT_BODY");
})();
</script>
"""

def _fire_browser_alert(title: str, body: str, beeps: int = 2):
    """Generic browser beep + notification helper."""
    js = (_SIGNAL_ALERT_JS
          .replace("BEEP_COUNT", str(beeps))
          .replace("ALERT_TITLE", title)
          .replace("ALERT_BODY",  body))
    stc.html(js, height=0)

def fire_signal_alert(symbol, grade, direction, score):
    """Play beep + send browser notification for AI-verified A/A+ signals."""
    beeps = 3 if grade == "A+" else 2
    _fire_browser_alert(f"🚨 {grade} SIGNAL — {symbol}", f"{direction} | Score {score}/100", beeps)

def fire_danger_alert(symbol, sl_pips, sl_pct):
    """Browser alert when price is dangerously close to SL."""
    _fire_browser_alert(
        f"⚠️ DANGER ZONE — {symbol}",
        f"Only {sl_pips:.0f} pips from SL ({int(sl_pct)}% remaining). Consider EXIT or MOVE SL.",
        beeps=3
    )

def fire_tp_alert(symbol, tp_label, tp_price, tp2_price=None):
    """Browser alert when TP1 is hit — suggest going for TP2 or exiting."""
    body = f"Price hit {tp_label}! Consider taking profit or trailing to TP2"
    if tp2_price:
        body += f" @ {tp2_price}"
    _fire_browser_alert(f"🎯 {tp_label} HIT — {symbol}", body, beeps=2)

def get_historical_context(symbol: str, direction: str, min_trades: int = 5) -> str:
    """
    Query Supabase for this trader's past performance on similar trades.
    Returns a context string injected into Grok prompts for personalised advice.
    Requires at least min_trades records to avoid misleading small-sample bias.
    """
    if not _sb_ok(): return ""
    try:
        rows = sb_get("journal", f"symbol=eq.{symbol}&direction=eq.{direction}&order=closed_at.desc&limit=100")
        if len(rows) < min_trades: return ""
        df = pd.DataFrame(rows)
        df["pnl_r"] = pd.to_numeric(df["pnl_r"], errors="coerce").fillna(0)
        total = len(df); wins = (df["outcome"]=="WIN").sum()
        wr    = round(wins/total*100, 1); avg_r = round(df["pnl_r"].mean(), 2)
        # Grade breakdown
        grade_info = ""
        if "grade" in df.columns:
            gd = df.groupby("grade").apply(
                lambda x: f"{(x['outcome']=='WIN').sum()}/{len(x)}"
            ).to_dict()
            grade_info = "  Grade breakdown: " + ", ".join(f"{k}:{v}" for k,v in gd.items()) + "."
        # Session breakdown
        sess_info = ""
        if "session" in df.columns and df["session"].notna().any():
            sd = df.groupby("session")["outcome"].apply(
                lambda x: f"{(x=='WIN').sum()}/{len(x)}"
            ).to_dict()
            sess_info = "  By session: " + ", ".join(f"{k}:{v}" for k,v in sd.items()) + "."
        # Recent streak
        recent = df.head(5)["outcome"].tolist()
        streak = "  Recent 5: " + " → ".join(recent) + "."
        return (
            f"\n\n📊 TRADER'S PERSONAL HISTORY ({symbol} {direction}, last {total} trades):\n"
            f"Win rate: {wr}%  |  Avg R: {avg_r:+.2f}R{grade_info}{sess_info}{streak}\n"
            f"Use this personal data to calibrate your recommendation — it reflects how THIS trader actually performs."
        )
    except Exception:
        return ""

def verify_signal_with_ai(symbol, grade, direction, score, analysis) -> bool:
    """
    Ask Grok to verify if a new Grade A/A+ signal is worth entering.
    Injects trader's personal history for personalised judgement.
    Returns True if valid, False if AI rejects. Falls back to True if no key.
    """
    key = get_xai_key()
    if not key: return True
    rsi  = fmt_num(analysis.get("rsi", 50), 1)
    h4   = analysis.get("h4_trend", "?")
    atr  = fmt_num(analysis.get("atr", 0), 5)
    sess = analysis.get("session", "?")
    hist = get_historical_context(symbol, direction, min_trades=5)
    msg = (
        f"NEW SIGNAL VERIFICATION — Should I enter this trade?\n"
        f"Symbol: {symbol}  Grade: {grade}  Direction: {direction}  Score: {score}/100\n"
        f"RSI14: {rsi}  H4 Trend: {h4}  ATR: {atr}  Session: {sess}"
        f"{hist}\n\n"
        f"Reply on the FIRST line with exactly: VALID or INVALID\n"
        f"Then 1 sentence explaining why.\n"
        f"Be strict: INVALID if RSI is extreme, H4 conflicts, session is low liquidity, "
        f"or the trader's personal history shows poor results in these conditions."
    )
    resp = _grok([
        {"role": "system", "content":
         "You are a concise forex signal validator who uses the trader's personal performance data. UTC: "
         + pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M")},
        {"role": "user", "content": msg}
    ], max_tokens=100, temperature=0.1, api_key=key) or ""
    return "INVALID" not in resp.upper()[:40]
# Read from env OR Streamlit Cloud secrets (for deployment)
def _get_secret(key, default=""):
    try:
        val = st.secrets.get(key, "")
        if val: return str(val).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()

_ENV_TD  = _get_secret("TWELVE_DATA_API_KEY")
_ENV_XAI = _get_secret("XAI_API_KEY")
_ENV_TE  = _get_secret("TRADING_ECONOMICS_KEY")
_ENV_MA_TOKEN   = _get_secret("METAAPI_TOKEN")
_ENV_MA_ACCOUNT = _get_secret("METAAPI_ACCOUNT")
_ENV_SB_URL     = _get_secret("SUPABASE_URL")
_ENV_SB_KEY     = _get_secret("SUPABASE_KEY")

# Owner email — used to identify admin/owner account
OWNER_EMAIL = "junkiatyeo96@gmail.com"

def _is_owner():
    """Check if current logged-in user is the platform owner."""
    if _AUTH_AVAILABLE and is_logged_in():
        return get_current_email() == OWNER_EMAIL
    return False

# Auto-populate session state from secrets on startup (shared API keys for all users)
if _ENV_TD  and not st.session_state.get("td_key"):      st.session_state["td_key"]      = _ENV_TD
if _ENV_XAI and not st.session_state.get("xai_key"):     st.session_state["xai_key"]     = _ENV_XAI
if _ENV_TE  and not st.session_state.get("te_key"):      st.session_state["te_key"]      = _ENV_TE

# Per-user MT5 credentials: load from Supabase user_settings on first login
# (shared/default MT5 only used if no user-specific settings exist)
def _load_user_mt5_settings():
    """Load per-user MT5 credentials from Supabase user_settings table."""
    if not (_AUTH_AVAILABLE and is_logged_in()): return
    if st.session_state.get("_user_settings_loaded"): return
    try:
        uid = get_current_user_id()
        _tok = st.session_state.get("auth_access_token", "")
        settings = get_user_settings(uid, access_token=_tok)
        if settings:
            if settings.get("ma_token") and not st.session_state.get("ma_token"):
                st.session_state["ma_token"] = settings["ma_token"]
            if settings.get("ma_account") and not st.session_state.get("ma_account"):
                st.session_state["ma_account"] = settings["ma_account"]
            if settings.get("ma_sym_suffix"):
                st.session_state["ma_sym_suffix"] = settings["ma_sym_suffix"]
            if settings.get("balance"):
                st.session_state["balance"] = float(settings["balance"])
            if settings.get("risk_pct"):
                st.session_state["risk_pct"] = float(settings["risk_pct"])
    except Exception:
        pass
    # Owner fallback: if no user_settings saved yet, load from env (Streamlit Secrets)
    if _is_owner():
        if _ENV_MA_TOKEN and not st.session_state.get("ma_token"):
            st.session_state["ma_token"] = _ENV_MA_TOKEN
        if _ENV_MA_ACCOUNT and not st.session_state.get("ma_account"):
            st.session_state["ma_account"] = _ENV_MA_ACCOUNT
    st.session_state["_user_settings_loaded"] = True

_load_user_mt5_settings()

# Shared MT5 for PRICE DATA (all users get live prices from owner's MT5)
# Per-user MT5 for TRADING/POSITIONS (only visible to that user via RLS)

JOURNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.json")

# ============================================================
# SUPABASE DATABASE (multi-user: auto-injects user_id)
# ============================================================
def _sb_ok(): return bool(_ENV_SB_URL and _ENV_SB_KEY)

_ENV_SB_SERVICE_KEY = _get_secret("SUPABASE_SERVICE_KEY")  # service_role key — bypasses RLS

def _sb_headers(extra=None):
    h = {"apikey": _ENV_SB_KEY, "Authorization": f"Bearer {_ENV_SB_KEY}",
         "Content-Type": "application/json", "Prefer": "return=representation"}
    if extra: h.update(extra)
    return h

def _sb_admin_headers(extra=None):
    """Headers using service_role key — bypasses RLS for admin/owner queries."""
    key = _ENV_SB_SERVICE_KEY or _ENV_SB_KEY
    h = {"apikey": key, "Authorization": f"Bearer {key}",
         "Content-Type": "application/json", "Prefer": "return=representation"}
    if extra: h.update(extra)
    return h

def admin_get_all(table: str, filters: str = "", limit: int = 1000) -> list:
    """Admin-only: fetch ALL rows from a table (bypasses RLS). Owner only."""
    if not (_sb_ok() and _is_owner()): return []
    try:
        url = f"{_ENV_SB_URL}/rest/v1/{table}?select=*&limit={limit}"
        if filters: url += f"&{filters}"
        r = requests.get(url, headers=_sb_admin_headers(), timeout=15)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return []

def admin_get_user_count() -> int:
    """Get total registered user count from auth.users via user_settings."""
    if not (_sb_ok() and _is_owner()): return 0
    try:
        url = f"{_ENV_SB_URL}/rest/v1/user_settings?select=user_id"
        r = requests.get(url, headers=_sb_admin_headers(), timeout=10)
        if r.status_code == 200: return len(r.json())
    except Exception: pass
    return 0

def sb_get(table: str, filters: str = "") -> list:
    if not _sb_ok(): return []
    try:
        uid = _uid()
        uid_filter = f"user_id=eq.{uid}" if uid else ""
        all_filters = "&".join(f for f in [filters, uid_filter] if f)
        url = f"{_ENV_SB_URL}/rest/v1/{table}?select=*" + (f"&{all_filters}" if all_filters else "")
        r = requests.get(url, headers=_sb_headers(), timeout=10)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return []

def sb_upsert(table: str, data: dict) -> bool:
    if not _sb_ok(): return False
    try:
        uid = _uid()
        if uid and "user_id" not in data:
            data["user_id"] = uid
        h = _sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
        r = requests.post(f"{_ENV_SB_URL}/rest/v1/{table}", headers=h, json=data, timeout=10)
        return r.status_code in (200, 201)
    except Exception: return False

def sb_insert(table: str, data: dict) -> bool:
    if not _sb_ok(): return False
    try:
        uid = _uid()
        if uid and "user_id" not in data:
            data["user_id"] = uid
        h = _sb_headers({"Prefer": "return=minimal"})
        r = requests.post(f"{_ENV_SB_URL}/rest/v1/{table}", headers=h, json=data, timeout=10)
        return r.status_code in (200, 201)
    except Exception: return False

def sb_delete(table: str, filters: str) -> bool:
    if not _sb_ok(): return False
    try:
        uid = _uid()
        uid_filter = f"user_id=eq.{uid}" if uid else ""
        all_filters = "&".join(f for f in [filters, uid_filter] if f)
        r = requests.delete(f"{_ENV_SB_URL}/rest/v1/{table}?{all_filters}",
                            headers=_sb_headers(), timeout=10)
        return r.status_code in (200, 204)
    except Exception: return False

def log_signal_to_db(symbol, direction, grade, score, ai_confirmed, session, rsi, h4):
    sb_insert("signals", {
        "symbol": symbol, "direction": direction, "grade": grade,
        "score": int(score), "ai_confirmed": bool(ai_confirmed),
        "session": session, "rsi": float(rsi), "h4_trend": h4
    })

def fetch_mt5_history_deals(token, account_id, since_hours=72):
    """Fetch recently closed deals from MetaApi to get exit prices."""
    region = _ma_get_region(token, account_id)
    base = f"https://mt-client-api-v1.{region}.agiliumtrade.ai"
    end_dt = pd.Timestamp.utcnow()
    start_dt = end_dt - pd.Timedelta(hours=since_hours)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_iso   = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    try:
        url = f"{base}/users/current/accounts/{account_id}/history-deals/time/{start_iso}/{end_iso}"
        r = requests.get(url, headers={"auth-token": token}, timeout=20)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return []

def sync_mt5_to_db():
    """
    Auto-sync MT5 positions with Supabase:
    - New MT5 position  → insert to trades table
    - Closed position   → find exit price → move to journal
    Returns current active trades list from DB.
    """
    if not _sb_ok(): return []
    ma_tok = get_ma_token(); ma_acc = get_ma_account()
    if not ma_tok or not ma_acc: return sb_get("trades")

    # Current MT5 open positions
    mt5_positions = fetch_mt5_positions(ma_tok, ma_acc)
    mt5_ticket_map = {}
    for p in mt5_positions:
        tid = str(p.get("id") or p.get("positionId") or "")
        if tid: mt5_ticket_map[tid] = p

    # Stored trades in DB
    db_trades = sb_get("trades")
    db_ticket_set = {t["mt5_ticket"] for t in db_trades if t.get("mt5_ticket")}

    # 1 ── New MT5 positions → insert to DB
    for ticket, pos in mt5_ticket_map.items():
        if ticket not in db_ticket_set:
            sym  = norm(pos.get("symbol","")).replace(".R","").replace(".r","")
            dir_ = "Buy" if "BUY" in pos.get("type","").upper() else "Sell"
            sl   = float(pos.get("stopLoss") or 0)
            tp   = float(pos.get("takeProfit") or 0)
            entry = float(pos.get("openPrice") or 0)
            sb_upsert("trades", {
                "id": str(uuid.uuid4()), "mt5_ticket": ticket,
                "symbol": sym, "direction": dir_,
                "entry": entry, "sl": sl, "tp1": tp, "tp2": tp,
                "lot": float(pos.get("volume") or 0.01),
                "locked_grade": "MT5-AUTO", "locked_score": 0,
                "opened_at": pos.get("time", pd.Timestamp.utcnow().isoformat()),
            })

    # 2 ── Closed positions → move to journal
    if db_trades:
        deals = fetch_mt5_history_deals(ma_tok, ma_acc, since_hours=72)
        deal_map = {}  # positionId → closing deal
        for d in deals:
            if "OUT" in d.get("entryType",""):
                pid = str(d.get("positionId",""))
                if pid: deal_map[pid] = d

        for trade in db_trades:
            ticket = trade.get("mt5_ticket","")
            if ticket and ticket not in mt5_ticket_map:
                # Position closed
                deal = deal_map.get(ticket)
                exit_price = float(deal["price"]) if deal else float(trade.get("entry",0))
                pnl_usd    = float(deal["profit"]) if deal else None
                entry = float(trade.get("entry",0))
                sl    = float(trade.get("sl") or 0)
                risk  = abs(entry - sl) if sl else 1
                move  = (exit_price - entry) if trade.get("direction")=="Buy" else (entry - exit_price)
                pnl_r = round(move/risk, 2) if risk > 0 else 0
                outcome = "WIN" if pnl_r > 0 else ("LOSS" if pnl_r < 0 else "BREAKEVEN")
                sb_insert("journal", {
                    "mt5_ticket": ticket, "symbol": trade.get("symbol"),
                    "direction": trade.get("direction"),
                    "entry": entry, "exit_price": exit_price,
                    "sl": sl, "tp1": trade.get("tp1"), "tp2": trade.get("tp2"),
                    "lot": trade.get("lot"), "pnl_r": pnl_r, "pnl_usd": pnl_usd,
                    "outcome": outcome, "grade": trade.get("locked_grade"),
                    "score": trade.get("locked_score"),
                    "opened_at": trade.get("opened_at"),
                })
                sb_delete("trades", f"mt5_ticket=eq.{ticket}")

    return sb_get("trades")

# ── Symbol-specific configs ─────────────────────────────────
# atr_sl / atr_tp1 / atr_tp2: ATR multipliers for SL and TP levels
# grade_aplus / grade_a / grade_b: minimum score for each grade
# H4 alignment is a HARD requirement for A / A+
SYMBOL_CONFIG: Dict[str, Dict] = {
    # ── FOREX ──────────────────────────────────────────────────
    "EURUSD": dict(name="EUR/USD",  pip=0.0001, dec=5, atr_sl=1.5, atr_tp1=2.5, atr_tp2=4.5,
                   grade_aplus=88, grade_a=76, grade_b=62, min_rr=2.0,
                   sessions=["London","Overlap","NewYork"], asset_class="forex",
                   note="Best during London/NY. Avoid Asian session."),
    "GBPUSD": dict(name="GBP/USD",  pip=0.0001, dec=5, atr_sl=1.8, atr_tp1=3.0, atr_tp2=5.0,
                   grade_aplus=90, grade_a=78, grade_b=64, min_rr=2.0,
                   sessions=["London","Overlap"], asset_class="forex",
                   note="Very volatile. Strict confirmation required."),
    "USDJPY": dict(name="USD/JPY",  pip=0.01,   dec=3, atr_sl=1.5, atr_tp1=2.5, atr_tp2=4.0,
                   grade_aplus=86, grade_a=74, grade_b=60, min_rr=1.8,
                   sessions=["Asian","London","Overlap"], asset_class="forex",
                   note="Tokyo active. Watch BOJ intervention risk."),
    "AUDUSD": dict(name="AUD/USD",  pip=0.0001, dec=5, atr_sl=1.5, atr_tp1=2.5, atr_tp2=4.0,
                   grade_aplus=88, grade_a=76, grade_b=62, min_rr=2.0,
                   sessions=["Asian","London"], asset_class="forex",
                   note="RBA sensitive. Commodity-linked."),
    "NZDUSD": dict(name="NZD/USD",  pip=0.0001, dec=5, atr_sl=1.5, atr_tp1=2.5, atr_tp2=4.0,
                   grade_aplus=88, grade_a=76, grade_b=62, min_rr=2.0,
                   sessions=["Asian","London"], asset_class="forex",
                   note="Dairy-linked. Best in Asian/London."),
    "EURCHF": dict(name="EUR/CHF",  pip=0.0001, dec=5, atr_sl=2.0, atr_tp1=2.5, atr_tp2=4.0,
                   grade_aplus=90, grade_a=78, grade_b=64, min_rr=1.8,
                   sessions=["London","Overlap"], asset_class="forex",
                   note="Low volatility. SNB intervention risk."),
    "GBPJPY": dict(name="GBP/JPY",  pip=0.01,   dec=3, atr_sl=2.0, atr_tp1=3.5, atr_tp2=6.0,
                   grade_aplus=92, grade_a=80, grade_b=66, min_rr=2.0,
                   sessions=["London","Overlap"], asset_class="forex",
                   note="'The Beast' — extremely volatile. Tight risk management required."),
    "EURJPY": dict(name="EUR/JPY",  pip=0.01,   dec=3, atr_sl=1.8, atr_tp1=3.0, atr_tp2=5.0,
                   grade_aplus=90, grade_a=78, grade_b=64, min_rr=2.0,
                   sessions=["London","Overlap","Asian"], asset_class="forex",
                   note="Carry trade pair. Strong trends."),
    # ── GOLD ───────────────────────────────────────────────────
    "XAUUSD": dict(name="Gold",     pip=0.1,    dec=2, atr_sl=2.0, atr_tp1=3.0, atr_tp2=5.5,
                   grade_aplus=88, grade_a=76, grade_b=62, min_rr=1.5,
                   sessions=["London","Overlap","NewYork"], asset_class="gold",
                   note="Multi-TF Smart Money hybrid. Best London/NY Killzones."),
    # ── CRUDE OIL ──────────────────────────────────────────────
    "XTIUSD": dict(name="WTI Oil",  pip=0.01,   dec=2, atr_sl=2.0, atr_tp1=3.5, atr_tp2=6.0,
                   grade_aplus=88, grade_a=76, grade_b=62, min_rr=2.0,
                   sessions=["London","Overlap","NewYork"], asset_class="oil",
                   note="News-driven. EIA/OPEC events cause spikes. Trade NY session."),
}
ACTIVE_SYMBOLS = list(SYMBOL_CONFIG.keys())

API_SYMBOL_MAP = {
    "EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY",
    "XAUUSD":"XAU/USD","EURCHF":"EUR/CHF","AUDUSD":"AUD/USD",
    "NZDUSD":"NZD/USD","GBPJPY":"GBP/JPY","EURJPY":"EUR/JPY",
    "XTIUSD":"XTI/USD",
}
INTERVAL_OPTIONS = {"5 Min":"5min","15 Min":"15min","30 Min":"30min","1 Hour":"1h","4 Hours":"4h"}
SESSIONS_UTC = {"London":(7,16),"NewYork":(12,21),"Overlap":(12,16),"Asian":(22,7)}

_MA_PROVISION_URL = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
_GROK_MODELS = ["grok-4-1-fast-non-reasoning","grok-4-1-fast-reasoning",
                "grok-4.20-0309-non-reasoning","grok-4.20-0309-reasoning"]

# MetaApi interval → timeframe string
MA_TIMEFRAME_MAP = {"5min":"5m","15min":"15m","30min":"30m","1h":"1h","4h":"4h","1d":"1d"}
# Interval → minutes (for startTime calculation)
MA_INTERVAL_MINS = {"5min":5,"15min":15,"30min":30,"1h":60,"4h":240,"1d":1440}

# ============================================================
# HELPERS
# ============================================================
def norm(s): return str(s).upper().replace("/","").strip()
def cfg(sym): return SYMBOL_CONFIG.get(norm(sym), SYMBOL_CONFIG["EURUSD"])
def to_api_sym(s): return API_SYMBOL_MAP.get(norm(s), norm(s))
def get_td_key():  return st.session_state.get("td_key","") or _ENV_TD
def get_xai_key(): return st.session_state.get("xai_key","") or _ENV_XAI
def get_te_key():  return st.session_state.get("te_key","")  or _ENV_TE
def get_grok_model(): return st.session_state.get("grok_model", _GROK_MODELS[0])
# Shared MT5 for PRICE DATA — all users see live prices via owner's MT5
def get_ma_token_price():   return _ENV_MA_TOKEN or ""
def get_ma_account_price(): return _ENV_MA_ACCOUNT or ""

# Per-user MT5 for TRADING — owner gets env fallback, others need own credentials
def get_ma_token():
    user_tok = st.session_state.get("ma_token", "")
    return user_tok or (_ENV_MA_TOKEN if _is_owner() else "")
def get_ma_account():
    user_acc = st.session_state.get("ma_account", "")
    return user_acc or (_ENV_MA_ACCOUNT if _is_owner() else "")

def fmt_price(v, sym=""):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    d = cfg(sym).get("dec",5)
    return f"{float(v):.{d}f}"

def fmt_num(v, d=2):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    return f"{float(v):.{d}f}"

def grade_color(g):
    return {"A+":"#00d4aa","A":"#10b981","B":"#84cc16","C":"#f59e0b","D":"#ef4444"}.get(str(g),"#8b9ab0")

def market_is_open(sym):
    if cfg(sym).get("asset_class") == "crypto":
        return True, "24/7"
    now = pd.Timestamp.utcnow(); wd = now.weekday()
    if wd == 5: return False, "CLOSED"
    if wd == 6 and now.hour < 22: return False, "CLOSED"
    return True, "LIVE"

def get_session_now():
    h = pd.Timestamp.utcnow().hour
    if 12 <= h < 16: return "London/NY Overlap"
    if 7  <= h < 16: return "London"
    if 12 <= h < 21: return "New York"
    return "Asian/Off-peak"

def session_ok(sym):
    """Returns True if current time is a preferred session for this symbol."""
    h = pd.Timestamp.utcnow().hour
    s = SYMBOL_CONFIG.get(norm(sym), {}).get("sessions", ["London","NewYork"])
    if "Overlap" in s and 12 <= h < 16: return True, "London/NY Overlap"
    if "London"  in s and 7  <= h < 16: return True, "London"
    if "NewYork" in s and 12 <= h < 21: return True, "New York"
    if "Asian"   in s and (h >= 22 or h < 7): return True, "Asian"
    return False, "Off-peak"

# ============================================================
# METAAPI
# ============================================================
@st.cache_data(ttl=120)
def _ma_get_region(token, account_id):
    try:
        r = requests.get(f"{_MA_PROVISION_URL}/users/current/accounts/{account_id}",
                         headers={"auth-token":token}, timeout=8)
        if r.status_code == 200:
            return r.json().get("region","new-york")
    except: pass
    return "new-york"

def _ma_base(token, account_id):
    return f"https://mt-client-api-v1.{_ma_get_region(token, account_id)}.agiliumtrade.ai"

def _mt5_sym(s):
    suffix = st.session_state.get("ma_sym_suffix","")
    return norm(s) + suffix

@st.cache_data(ttl=3)
def fetch_mt5_price(symbol, token, account_id):
    if not token or not account_id: return None
    base = _ma_base(token, account_id)
    for sym in [_mt5_sym(symbol), norm(symbol)]:
        try:
            r = requests.get(f"{base}/users/current/accounts/{account_id}/symbols/{sym}/current-price",
                             headers={"auth-token":token}, timeout=5)
            if r.status_code == 200:
                d = r.json()
                bid = float(d.get("bid",0)); ask = float(d.get("ask",0))
                ps = cfg(symbol).get("pip",0.0001)
                spread = round(abs(ask-bid)/ps, 1) if ps else 0
                return {"bid":bid,"ask":ask,"mid":(bid+ask)/2,"spread_pips":spread,"mt5_sym":sym}
        except: pass
    return None

@st.cache_data(ttl=5)
def fetch_mt5_positions(token, account_id):
    if not token or not account_id: return []
    try:
        r = requests.get(f"{_ma_base(token,account_id)}/users/current/accounts/{account_id}/positions",
                         headers={"auth-token":token}, timeout=5)
        if r.status_code == 200: return r.json()
    except: pass
    return []

@st.cache_data(ttl=30)
def fetch_mt5_account_info(token, account_id):
    if not token or not account_id: return None
    try:
        r = requests.get(f"{_ma_base(token,account_id)}/users/current/accounts/{account_id}/account-information",
                         headers={"auth-token":token}, timeout=5)
        if r.status_code == 200: return r.json()
    except: pass
    return None

def test_mt5_connection(token, account_id):
    headers = {"auth-token": token}
    prov_url = f"{_MA_PROVISION_URL}/users/current/accounts/{account_id}"
    region = "new-york"
    try:
        rp = requests.get(prov_url, headers=headers, timeout=8)
        if rp.status_code == 401: return False, "❌ 401 Unauthorised — token wrong or expired"
        if rp.status_code == 404: return False, "❌ 404 Account not found — check Account ID"
        if rp.status_code == 200:
            acc = rp.json(); region = acc.get("region","new-york")
            state = acc.get("state","?")
            if state == "UNDEPLOYED":
                return False, f"❌ Account UNDEPLOYED — click ▶ Deploy first (region={region})"
    except Exception as e:
        return False, f"❌ Provisioning error: {e}"
    client_url = f"https://mt-client-api-v1.{region}.agiliumtrade.ai"
    try:
        rc = requests.get(f"{client_url}/users/current/accounts/{account_id}/account-information",
                          headers=headers, timeout=8)
        if rc.status_code == 200:
            d = rc.json()
            return True, f"✅ Connected — {d.get('name','?')}  Balance: {d.get('balance','?')} {d.get('currency','USD')}"
        return False, f"❌ Client API HTTP {rc.status_code}: {rc.text[:120]}"
    except Exception as e:
        return False, f"❌ Client error: {e}"

def deploy_mt5_account(token, account_id):
    try:
        r = requests.post(f"{_MA_PROVISION_URL}/users/current/accounts/{account_id}/deploy",
                          headers={"auth-token":token}, timeout=10)
        if r.status_code in (200,204):
            return True, "✅ Deploy sent. Wait 30s then Test MT5."
        return False, f"Deploy failed HTTP {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return False, f"Deploy error: {e}"

def _ma_market_data_base(token, account_id):
    """Market-data API uses a different subdomain from client API."""
    region = _ma_get_region(token, account_id)
    return f"https://mt-market-data-client-api-v1.{region}.agiliumtrade.ai"

@st.cache_data(ttl=60)
def fetch_bars_ma(symbol, interval, bars, token, account_id):
    """Fetch OHLCV bars from MetaApi historical candles endpoint.
    Returns a DataFrame identical in structure to fetch_bars(), or raises on error."""
    if not token or not account_id:
        raise ValueError("MetaApi token/account not configured")
    tf = MA_TIMEFRAME_MAP.get(interval)
    if not tf:
        raise ValueError(f"Unsupported interval for MetaApi: {interval}")
    mins  = MA_INTERVAL_MINS.get(interval, 15)
    # startTime = now minus (bars * interval) with 20% buffer for weekends/gaps
    delta_mins = int(bars * mins * 1.4)
    start_dt   = pd.Timestamp.utcnow() - pd.Timedelta(minutes=delta_mins)
    start_iso  = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    mt_sym = _mt5_sym(symbol)
    base   = _ma_market_data_base(token, account_id)
    url    = (f"{base}/users/current/accounts/{account_id}"
              f"/historical-market-data/symbols/{mt_sym}/timeframes/{tf}/candles"
              f"?startTime={start_iso}&limit={bars}")
    r = requests.get(url, headers={"auth-token": token}, timeout=30)
    if r.status_code == 404:
        # Try without broker suffix
        url2 = url.replace(f"/symbols/{mt_sym}/", f"/symbols/{norm(symbol)}/")
        r = requests.get(url2, headers={"auth-token": token}, timeout=30)
    if r.status_code == 504 or (r.status_code != 200 and "not connected" in r.text.lower()):
        raise ValueError("MetaApi account not connected — click Deploy in sidebar")
    if r.status_code != 200:
        raise ValueError(f"MetaApi candles HTTP {r.status_code}: {r.text[:120]}")
    candles = r.json()
    if not candles:
        raise ValueError(f"MetaApi returned 0 candles for {symbol} {interval}")
    df = pd.DataFrame(candles)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    for c in ["open","high","low","close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "tickVolume" in df.columns:
        df["volume"] = pd.to_numeric(df["tickVolume"], errors="coerce")
    return df.sort_values("time").dropna(subset=["time","open","high","low","close"]).reset_index(drop=True)

# ============================================================
# GROK
# ============================================================
def _grok(messages, max_tokens=400, temperature=0.25, api_key="", model=""):
    key = api_key or get_xai_key()
    if not key: return None
    mdl = model or get_grok_model()
    try:
        r = requests.post("https://api.x.ai/v1/chat/completions",
                          headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                          json={"model":mdl,"messages":messages,"max_tokens":max_tokens,
                                "temperature":float(max(0.0,min(1.0,temperature)))},
                          timeout=25)
        if r.status_code != 200:
            try: msg = r.json().get("error",{}).get("message") or r.text[:120]
            except: msg = r.text[:120]
            return f"[Grok {r.status_code}: {msg}]"
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[Grok error: {e}]"

@st.cache_data(ttl=90)
def get_news_sentiment(symbol, xai_key):
    if not xai_key:
        return {"risk":"LOW","adj":0,"bias":"neutral","summary":"No xAI key","events":[],"ok":False}
    sym_name = SYMBOL_CONFIG.get(norm(symbol),{}).get("name", symbol)
    # Build precise session context so Grok doesn't hallucinate market hours
    now_utc   = pd.Timestamp.utcnow()
    utc_str   = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    utc_h     = now_utc.hour + now_utc.minute / 60
    active_sessions = []
    if 7  <= utc_h < 16: active_sessions.append("London")
    if 12 <= utc_h < 21: active_sessions.append("New York")
    if 12 <= utc_h < 16: active_sessions.append("London-NY Overlap")
    if utc_h >= 22 or utc_h < 7: active_sessions.append("Asian")
    if not active_sessions: active_sessions.append("Off-peak (21:00-22:00 UTC)")
    sess_str  = ", ".join(active_sessions)
    ny_close_h = 21
    if utc_h < ny_close_h:
        ny_left = round(ny_close_h - utc_h, 1)
        ny_str  = f"New York closes in {ny_left:.1f}h (at 21:00 UTC)"
    else:
        ny_str  = "New York session is CLOSED"
    raw = _grok([
        {"role":"system","content":(
            f"You are a forex analyst with REAL-TIME market awareness.\n"
            f"EXACT TIME NOW: {utc_str}\n"
            f"ACTIVE SESSIONS: {sess_str}\n"
            f"{ny_str}\n"
            f"RULE: Do NOT guess or approximate market hours. Use ONLY the exact times above. "
            f"If you mention session timing, it must match these numbers exactly."
        )},
        {"role":"user","content":
         f"Analyze CURRENT news sentiment for {sym_name}.\n"
         f"Current time: {utc_str}. Active: {sess_str}.\n"
         f'Return ONLY JSON: {{"risk":"HIGH|MEDIUM|LOW","adj":<-15 to 15>,"bias":"bull|bear|neutral",'
         f'"summary":"<20 words max>","events":["ev1","ev2","ev3"]}}\n'
         f"HIGH=major event within 2h (NFP/FOMC/CPI/CB). Negative adj for imminent HIGH-risk events.\n"
         f"DO NOT mention session timing unless directly relevant to a news event."}
    ], max_tokens=200, temperature=0.1, api_key=xai_key)
    if not raw or raw.startswith("[Grok"):
        return {"risk":"LOW","adj":0,"bias":"neutral","summary":raw or "Error","events":[],"ok":False}
    try:
        obj = json.loads(re.sub(r"```json|```","",raw).strip())
        return {"risk":obj.get("risk","LOW"),"adj":int(obj.get("adj",0)),
                "bias":obj.get("bias","neutral"),"summary":obj.get("summary",""),
                "events":obj.get("events",[]),"ok":True}
    except:
        return {"risk":"LOW","adj":0,"bias":"neutral","summary":raw[:100],"events":[],"ok":False}

def get_ai_analysis(symbol, direction, score, grade, entry, sl, tp1, tp2,
                    atr, rsi, macd_hist, session, news, df_tail):
    key = get_xai_key()
    if not key: return "⚠ No xAI key."
    recent = df_tail[["open","high","low","close"]].round(cfg(symbol)["dec"]).to_string(index=False)
    n_info = f"Risk={news['risk']}, bias={news['bias']}, {news['summary']}" if news and news.get("ok") else "no data"
    msg = (f"Symbol: {symbol}  Dir: {direction}  Grade: {grade} ({score}/100)\n"
           f"Entry: {fmt_price(entry,symbol)}  SL: {fmt_price(sl,symbol)}  TP1: {fmt_price(tp1,symbol)}  TP2: {fmt_price(tp2,symbol)}\n"
           f"ATR: {fmt_num(atr,5)}  RSI: {fmt_num(rsi,1)}  MACD_hist: {fmt_num(macd_hist,5)}\n"
           f"Session: {session}  News: {n_info}\nLast 10 bars:\n{recent}\n"
           f"→ Is this a valid {direction} setup? Key risks? 3-4 sentences max.")
    return _grok([{"role":"system","content":"You are a professional forex risk manager. Be direct."},
                  {"role":"user","content":msg}], max_tokens=300, temperature=0.3, api_key=key) or "No response."

# ============================================================
# GROK-PRIMARY SIGNAL ENGINE — AI decides, Calculator backs up
# ============================================================
@st.cache_data(ttl=120)
def grok_primary_analysis(symbol, close, atr, rsi, macd_val, macd_hist,
                          ema20, ema50, ema200, h4_trend, session_name,
                          calc_direction, calc_score, calc_grade,
                          sl_calc, tp1_calc, tp2_calc,
                          last_10_bars_str, xai_key, bb_upper=0, bb_lower=0):
    """
    GROK-PRIMARY: Grok receives ALL technical data + calculator score,
    then makes the FINAL trading decision with its own AI Rating.
    Returns dict with: ai_rating, direction, action, entry, sl, tp1, tp2,
    reasoning, confidence, key_factors
    """
    if not xai_key:
        return {"ai_rating": 0, "direction": calc_direction, "action": "WAIT",
                "reasoning": "No xAI key — using calculator only.", "confidence": "LOW",
                "key_factors": [], "error": True}

    c = cfg(symbol)
    sym_name = c.get("name", symbol)
    asset_class = c.get("asset_class", "forex")
    pip_size = c.get("pip", 0.0001)
    dec = c.get("dec", 5)

    # Build time context
    now_utc = pd.Timestamp.utcnow()
    utc_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    day_of_week = now_utc.strftime("%A")

    prompt = f"""You are an elite institutional forex & commodities trader with 20 years of experience.
You have access to REAL technical data below. Combine this with your knowledge of:
- Current global macro environment, central bank policies, geopolitical events
- Typical price behavior patterns for {sym_name} ({asset_class})
- Session liquidity ({session_name}), day-of-week effects ({day_of_week})
- News impact, risk-on/risk-off sentiment, intermarket correlations

═══ TECHNICAL DATA FOR {symbol} ═══
Time: {utc_str} ({day_of_week})
Session: {session_name}
Asset: {sym_name} ({asset_class})

PRICE: {close:.{dec}f}
ATR(14): {atr:.{dec}f}
RSI(14): {rsi:.1f}
MACD: {macd_val:.{dec}f} | Histogram: {macd_hist:.{dec}f}
EMA20: {ema20:.{dec}f} | EMA50: {ema50:.{dec}f} | EMA200: {ema200:.{dec}f}
Bollinger Upper: {bb_upper:.{dec}f} | Lower: {bb_lower:.{dec}f}
H4 Trend: {h4_trend}

CALCULATOR BACKUP (rule-based):
Direction: {calc_direction} | Score: {calc_score}/100 | Grade: {calc_grade}
SL: {sl_calc:.{dec}f} | TP1: {tp1_calc:.{dec}f} | TP2: {tp2_calc:.{dec}f}

LAST 10 CANDLES:
{last_10_bars_str}

═══ YOUR TASK ═══
Analyze ALL the above + your macro/news knowledge. Return ONLY valid JSON:
{{
  "ai_rating": <1-10 scale: 1=terrible, 5=neutral, 8=strong, 10=perfect setup>,
  "direction": "BUY" or "SELL" or "WAIT",
  "action": "STRONG BUY" or "BUY" or "WAIT" or "SELL" or "STRONG SELL",
  "entry": <optimal entry price based on SMART ENTRY ENGINE levels>,
  "entry_type": "MARKET" or "LIMIT" or "WAIT",
  "sl": <stop loss price>,
  "tp1": <take profit 1>,
  "tp2": <take profit 2>,
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "reasoning": "<2-3 sentence analysis combining technicals + fundamentals>",
  "key_factors": ["factor1", "factor2", "factor3"],
  "news_impact": "<1 sentence on current news/macro affecting this pair>",
  "agrees_with_calculator": true or false,
  "risk_warning": "<1 sentence if any major risk>"
}}

RULES:
- ai_rating 8+ = strong trade, 6-7 = decent, 5 = neutral, below 5 = avoid
- If session is off-peak, reduce rating by 1-2 points
- If major news event within 2h, add risk_warning
- Be HONEST — if no clear setup, say WAIT. Don't force trades.
- ENTRY MUST be at a technical level (EMA20, support/resistance, BB band), NOT just current price ± small offset
- entry_type: MARKET = enter now (price at ideal level), LIMIT = set pending order at key level, WAIT = no good entry yet
- If price is far from any key level, set entry_type to WAIT or LIMIT at the nearest key level
- SL/TP must be realistic based on ATR. SL behind the key level, TP at next key level
"""

    raw = _grok([
        {"role": "system", "content": (
            "You are an elite institutional trader. Return ONLY valid JSON. "
            "No markdown, no code blocks, no explanation outside JSON. "
            "Be brutally honest — bad setups get low ratings."
        )},
        {"role": "user", "content": prompt}
    ], max_tokens=400, temperature=0.2, api_key=xai_key)

    if not raw or raw.startswith("[Grok"):
        return {"ai_rating": 0, "direction": calc_direction, "action": "WAIT",
                "reasoning": raw or "Grok error", "confidence": "LOW",
                "key_factors": [], "error": True}

    try:
        cleaned = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(cleaned)
        # Normalize direction
        d = result.get("direction", "WAIT").upper()
        result["direction"] = "Buy" if d in ("BUY","LONG") else ("Sell" if d in ("SELL","SHORT") else "Wait")
        # Ensure numeric fields
        result["ai_rating"] = max(1, min(10, int(result.get("ai_rating", 5))))
        for k in ("entry", "sl", "tp1", "tp2"):
            if k in result:
                result[k] = float(result[k])
            else:
                result[k] = {"entry": close, "sl": sl_calc, "tp1": tp1_calc, "tp2": tp2_calc}[k]
        # entry_type from Grok
        if "entry_type" not in result or result.get("entry_type") not in ("MARKET","LIMIT","WAIT"):
            result["entry_type"] = "MARKET"
        result["error"] = False
        # Add calculator comparison
        result["calc_score"] = calc_score
        result["calc_grade"] = calc_grade
        result["calc_direction"] = calc_direction
        return result
    except Exception as e:
        return {"ai_rating": 5, "direction": calc_direction, "action": "WAIT",
                "reasoning": f"Parse error: {raw[:200]}", "confidence": "LOW",
                "key_factors": [], "error": True,
                "calc_score": calc_score, "calc_grade": calc_grade, "calc_direction": calc_direction}

def get_ai_trade_advice(trade: dict, live_price: float, analysis: dict, news: dict) -> str:
    """
    Active trade advisor: asks Grok whether to HOLD, EXIT, or MOVE SL.
    Returns a clear recommendation with reasoning.
    """
    key = get_xai_key()
    if not key: return "⚠ No xAI key — add it in the sidebar."
    sym    = trade.get("symbol","?")
    dir_   = trade["direction"]
    entry  = float(trade["entry"]); sl = float(trade["sl"])
    tp1    = float(trade.get("tp1", entry)); tp2 = float(trade.get("tp2", entry))
    risk   = abs(entry - sl)
    move   = (live_price - entry) if dir_=="Buy" else (entry - live_price)
    pnl_r  = round(move/risk, 2) if risk > 0 else 0
    # Distance to SL and TP in pips
    ps     = cfg(sym).get("pip", 0.0001)
    sl_dist_pips  = round(abs(live_price - sl) / ps, 1)
    tp1_dist_pips = round(abs(live_price - tp1) / ps, 1)
    # Context from analysis
    rsi       = fmt_num(analysis.get("rsi", 50), 1)
    macd_hist = fmt_num(analysis.get("macd_hist", 0), 5)
    h4_trend  = analysis.get("h4_trend","?")
    session   = analysis.get("session","?")
    n_info    = f"Risk={news['risk']}, bias={news['bias'].upper()}, {news['summary']}" if news and news.get("ok") else "no news data"
    hist = get_historical_context(sym, dir_, min_trades=5)
    msg = (
        f"ACTIVE TRADE — HOLD / EXIT / MOVE SL?\n"
        f"Symbol: {sym}  Direction: {dir_}\n"
        f"Entry: {fmt_price(entry,sym)}  |  Current Price: {fmt_price(live_price,sym)}\n"
        f"SL: {fmt_price(sl,sym)} ({sl_dist_pips} pips away)  |  TP1: {fmt_price(tp1,sym)} ({tp1_dist_pips} pips away)\n"
        f"Current P&L: {pnl_r:+.2f}R\n"
        f"RSI14: {rsi}  |  MACD Hist: {macd_hist}  |  H4 Trend: {h4_trend}\n"
        f"Session: {session}  |  News: {n_info}"
        f"{hist}\n\n"
        f"Give a CLEAR recommendation:\n"
        f"1. Action: HOLD / EXIT NOW / MOVE SL TO BREAKEVEN / PARTIAL EXIT\n"
        f"2. Reason: 2-3 sentences why\n"
        f"3. Risk: What is the main danger right now?\n"
        f"Be direct and specific. Factor in the trader's personal history above if available."
    )
    return _grok([
        {"role":"system","content":"You are a professional forex risk manager who uses the trader's personal performance history to give personalised advice. UTC: "
         + pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M")},
        {"role":"user","content":msg}
    ], max_tokens=400, temperature=0.2, api_key=key) or "No response from Grok."

# ============================================================
# TRADING ECONOMICS — Real Economic Calendar
# ============================================================
# Currency → relevant TE country codes
_TE_CURRENCY_MAP = {
    "EUR": ["euro area","european union"],
    "USD": ["united states"],
    "GBP": ["united kingdom"],
    "JPY": ["japan"],
    "AUD": ["australia"],
    "CHF": ["switzerland"],
    "NZD": ["new zealand"],
    "XAU": ["united states"],
    "XTI": ["united states"],
    "BTC": ["united states"],
    "ETH": ["united states"],
}
# Symbol → currencies involved
_TE_SYMBOL_CURRENCIES = {
    "EURUSD": ["EUR","USD"], "GBPUSD": ["GBP","USD"],
    "USDJPY": ["USD","JPY"], "XAUUSD": ["XAU","USD"],
    "AUDUSD": ["AUD","USD"], "EURCHF": ["EUR","CHF"],
    "NZDUSD": ["NZD","USD"], "GBPJPY": ["GBP","JPY"],
    "EURJPY": ["EUR","JPY"], "XTIUSD": ["XTI","USD"],
    "BTCUSD": ["BTC","USD"], "ETHUSD": ["ETH","USD"],
}
# High-impact event keywords
_TE_HIGH_IMPACT = ["interest rate","cpi","nfp","non-farm","gdp","fomc","inflation",
                   "employment","unemployment","pmi","retail sales","central bank"]

@st.cache_data(ttl=3600)   # 1 hour cache — conserves 500 req/month limit
def fetch_te_calendar(te_key: str):
    """Fetch next 3 days of economic calendar from Trading Economics."""
    if not te_key:
        return []
    try:
        url = "https://api.tradingeconomics.com/calendar"
        params = {"c": te_key, "f": "json"}
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        # Keep only events in next 3 days
        now = pd.Timestamp.utcnow()
        cutoff = now + pd.Timedelta(days=3)
        events = []
        for ev in data:
            try:
                dt = pd.Timestamp(ev.get("Date",""), tz="UTC")
                if now - pd.Timedelta(hours=2) <= dt <= cutoff:
                    events.append({
                        "date": dt,
                        "country": str(ev.get("Country","")).lower(),
                        "event": str(ev.get("Event","")),
                        "importance": str(ev.get("Importance","")).upper(),
                        "actual": ev.get("Actual",""),
                        "forecast": ev.get("Forecast",""),
                        "previous": ev.get("Previous",""),
                    })
            except Exception:
                continue
        return sorted(events, key=lambda x: x["date"])
    except Exception:
        return []

def get_te_news_for_symbol(symbol: str, te_key: str) -> dict:
    """
    Returns news dict compatible with get_news_sentiment() output,
    but powered by real Trading Economics calendar data.
    """
    events = fetch_te_calendar(te_key)
    sym = norm(symbol)
    currencies = _TE_SYMBOL_CURRENCIES.get(sym, [])
    relevant_countries = []
    for c in currencies:
        relevant_countries.extend(_TE_CURRENCY_MAP.get(c, []))

    # Filter events relevant to this symbol
    rel = []
    for ev in events:
        country_match = any(rc in ev["country"] for rc in relevant_countries)
        if country_match:
            rel.append(ev)

    if not rel:
        return {"risk":"LOW","adj":0,"bias":"neutral",
                "summary":"No major events in next 3 days.",
                "events":[],"ok":True,"source":"TE"}

    # Determine risk level
    now = pd.Timestamp.utcnow()
    high_soon = [e for e in rel if e["importance"]=="HIGH"
                 and (e["date"] - now).total_seconds() < 7200]  # within 2h
    high_today = [e for e in rel if e["importance"]=="HIGH"]
    medium_events = [e for e in rel if e["importance"]=="MEDIUM"]

    if high_soon:
        risk = "HIGH"; adj = -10
    elif high_today:
        risk = "HIGH"; adj = -5
    elif medium_events:
        risk = "MEDIUM"; adj = -3
    else:
        risk = "LOW"; adj = 0

    # Build event list (max 4)
    event_strs = []
    for e in rel[:4]:
        time_str = e["date"].strftime("%a %H:%M UTC")
        imp_icon = "🔴" if e["importance"]=="HIGH" else ("🟡" if e["importance"]=="MEDIUM" else "⚪")
        actual_str = f" → Actual: {e['actual']}" if e["actual"] not in ("","None",None) else ""
        forecast_str = f" (Fcst: {e['forecast']})" if e["forecast"] not in ("","None",None) else ""
        event_strs.append(f"{imp_icon} {time_str} [{e['country'].title()}] {e['event']}{forecast_str}{actual_str}")

    # Summary
    if high_soon:
        summary = f"⚠ HIGH-RISK event within 2h: {high_soon[0]['event']}"
    elif high_today:
        summary = f"High-impact event today: {high_today[0]['event']}"
    elif medium_events:
        summary = f"{len(medium_events)} medium-impact events upcoming"
    else:
        summary = f"{len(rel)} low-impact events in next 3 days"

    return {"risk":risk,"adj":adj,"bias":"neutral",
            "summary":summary,"events":event_strs,"ok":True,"source":"TE"}

# ============================================================
# TWELVE DATA
# ============================================================
def _td_get(endpoint, params, _retries=2, _backoff=0.5):
    """Fetch from Twelve Data with automatic retry on timeout / 5xx errors."""
    import time
    key = get_td_key()
    if not key: raise ValueError("No Twelve Data key")
    p = dict(params); p["apikey"] = key
    last_err = None
    for attempt in range(_retries):
        try:
            r = requests.get(f"https://api.twelvedata.com/{endpoint}",
                             params=p, timeout=25)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("status") == "error":
                raise ValueError(data.get("message", "Twelve Data error"))
            return data
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as e:
            last_err = e
            if attempt < _retries - 1:
                time.sleep(_backoff)   # fast retry: 0.5s only
    raise last_err

def _parse_td(values):
    df = pd.DataFrame(values)
    if df.empty: return df
    col = "datetime" if "datetime" in df.columns else "date"
    df["time"] = pd.to_datetime(df[col], utc=True, errors="coerce")
    for c in ["open","high","low","close","volume"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("time").dropna(subset=["time","open","high","low","close"]).reset_index(drop=True)

@st.cache_data(ttl=60)
def fetch_bars(symbol, interval, bars, td_key):
    """Fetch OHLCV bars. Tries MetaApi first (if connected), falls back to Twelve Data."""
    ma_tok = get_ma_token(); ma_acc = get_ma_account()
    if ma_tok and ma_acc:
        try:
            df = fetch_bars_ma(symbol, interval, bars, ma_tok, ma_acc)
            if df is not None and len(df) >= 50:
                return df          # ✅ MetaApi success
        except Exception:
            pass                   # silent fallback to Twelve Data
    # ── Twelve Data fallback ──────────────────────────────────
    if not td_key:
        raise ValueError("No data source: MetaApi not connected and no Twelve Data key")
    data = _td_get("time_series", {"symbol":to_api_sym(symbol),"interval":interval,
                                   "outputsize":int(bars),"timezone":"UTC","order":"ASC"})
    v = data.get("values",[])
    if not v: raise ValueError(f"No bars from Twelve Data for {symbol}")
    return _parse_td(v)

# ============================================================
# INDICATORS
# ============================================================
def add_indicators(df):
    x = df.copy()
    x["ema9"]   = x["close"].ewm(span=9,   adjust=False).mean()
    x["ema21"]  = x["close"].ewm(span=21,  adjust=False).mean()
    x["ema20"]  = x["close"].ewm(span=20,  adjust=False).mean()
    x["ema50"]  = x["close"].ewm(span=50,  adjust=False).mean()
    x["ema200"] = x["close"].ewm(span=200, adjust=False).mean()
    tr = pd.concat([x["high"]-x["low"],
                    (x["high"]-x["close"].shift()).abs(),
                    (x["low"] -x["close"].shift()).abs()],axis=1).max(axis=1)
    x["atr14"] = tr.rolling(14).mean()
    delta = x["close"].diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    x["rsi14"] = 100-(100/(1+gain.rolling(14).mean()/loss.rolling(14).mean().replace(0,np.nan)))
    ema12 = x["close"].ewm(span=12,adjust=False).mean()
    ema26 = x["close"].ewm(span=26,adjust=False).mean()
    x["macd"]      = ema12 - ema26
    x["macd_sig"]  = x["macd"].ewm(span=9,adjust=False).mean()
    x["macd_hist"] = x["macd"] - x["macd_sig"]
    x["bb_mid"]    = x["close"].rolling(20).mean()
    bb_std = x["close"].rolling(20).std()
    x["bb_upper"]  = x["bb_mid"] + 2*bb_std
    x["bb_lower"]  = x["bb_mid"] - 2*bb_std
    # ── ADX (Average Directional Index) for market regime detection ──
    plus_dm  = x["high"].diff()
    minus_dm = -x["low"].diff()
    plus_dm  = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    _tr14    = tr.rolling(14).sum()
    _plus_di  = 100 * plus_dm.rolling(14).sum() / _tr14.replace(0, np.nan)
    _minus_di = 100 * minus_dm.rolling(14).sum() / _tr14.replace(0, np.nan)
    _dx = 100 * (_plus_di - _minus_di).abs() / (_plus_di + _minus_di).replace(0, np.nan)
    x["adx"]      = _dx.rolling(14).mean()
    x["plus_di"]  = _plus_di
    x["minus_di"] = _minus_di
    return x

# ============================================================
# SIGNAL ENGINE  — H4-first, ATR-based SL/TP
# ============================================================
def _h4_trend(df_h4):
    """Returns 'bull' | 'bear' | 'neutral' based on H4 EMAs."""
    if df_h4 is None or len(df_h4) < 50: return "neutral"
    r = df_h4.iloc[-1]
    e20 = r.get("ema20", r["close"]); e50 = r.get("ema50", r["close"])
    e200= r.get("ema200",r["close"]); close = r["close"]
    if close > e50 and e50 > e200 and e20 > e50: return "bull"
    if close < e50 and e50 < e200 and e20 < e50: return "bear"
    if close > e200: return "bull_weak"
    if close < e200: return "bear_weak"
    return "neutral"

# ============================================================
# MARKET REGIME DETECTION (NEW V2)
# ============================================================
def _detect_regime(df):
    """
    Detect market regime using ADX.
    Returns: 'trending' | 'ranging' | 'transitioning'
    """
    if len(df) < 30:
        return "transitioning"
    adx = float(df.iloc[-1].get("adx", 20) or 20)
    if adx > 25:
        return "trending"
    elif adx < 20:
        return "ranging"
    return "transitioning"

def _is_extended(df, direction, atr):
    """
    Anti-chase guard: detect if price has already moved too far.
    Returns (is_extended: bool, move_in_atr: float)
    """
    if len(df) < 6 or atr <= 0:
        return False, 0.0
    close = float(df.iloc[-1]["close"])
    close_5_ago = float(df.iloc[-6]["close"])
    move = close - close_5_ago if direction == "Buy" else close_5_ago - close
    move_atr = move / atr
    return move_atr > 2.0, round(move_atr, 1)

def _price_distance_from_ema(close, ema20, atr):
    """How far price is from EMA20 in ATR units. Positive = above, negative = below."""
    if atr <= 0:
        return 0.0
    return round((close - ema20) / atr, 2)

def _candle_score(df, direction):
    """Score candle pattern: 0-10. Engulfing, pin bars, momentum candles."""
    if len(df) < 3: return 0
    c = df.iloc[-1]; p = df.iloc[-2]
    body  = abs(float(c["close"])-float(c["open"]))
    range_= float(c["high"])-float(c["low"])
    if range_ == 0: return 0
    body_ratio = body / range_
    upper_wick = float(c["high"]) - max(float(c["close"]), float(c["open"]))
    lower_wick = min(float(c["close"]), float(c["open"])) - float(c["low"])

    if direction == "Buy":
        # Bullish engulfing
        if float(c["close"]) > float(c["open"]) and float(c["close"]) > float(p["open"]) and float(c["open"]) < float(p["close"]): return 10
        # Bullish pin bar (hammer): long lower wick, small upper wick
        if lower_wick > body * 2 and upper_wick < body * 0.5 and body > 0: return 10
        # Strong bullish candle
        if float(c["close"]) > float(c["open"]) and body_ratio > 0.65: return 5
        # Morning star (3-candle reversal)
        if len(df) >= 4:
            pp = df.iloc[-3]
            if float(pp["close"]) < float(pp["open"]) and body_ratio > 0.5 and float(c["close"]) > float(c["open"]):
                pp_body = abs(float(pp["close"]) - float(pp["open"]))
                p_body = abs(float(p["close"]) - float(p["open"]))
                if p_body < pp_body * 0.3: return 8
    else:
        # Bearish engulfing
        if float(c["close"]) < float(c["open"]) and float(c["close"]) < float(p["open"]) and float(c["open"]) > float(p["close"]): return 10
        # Bearish pin bar (shooting star): long upper wick
        if upper_wick > body * 2 and lower_wick < body * 0.5 and body > 0: return 10
        # Strong bearish candle
        if float(c["close"]) < float(c["open"]) and body_ratio > 0.65: return 5
        # Evening star
        if len(df) >= 4:
            pp = df.iloc[-3]
            if float(pp["close"]) > float(pp["open"]) and body_ratio > 0.5 and float(c["close"]) < float(c["open"]):
                pp_body = abs(float(pp["close"]) - float(pp["open"]))
                p_body = abs(float(p["close"]) - float(p["open"]))
                if p_body < pp_body * 0.3: return 8
    return 0

def score_signal(df, df_h4, symbol, direction):
    """
    SIGNAL SCORING V2 — rewards pullbacks, punishes chasing.
    Regime-aware: trending vs ranging have different scoring emphasis.
    Returns (score, breakdown_dict, grade, warning_list)
    """
    c = cfg(symbol)
    row   = df.iloc[-1]
    prev  = df.iloc[-2] if len(df) >= 2 else row
    close = float(row["close"])
    e20   = float(row.get("ema20",  close))
    e50   = float(row.get("ema50",  close))
    e200  = float(row.get("ema200", close))
    atr   = float(row.get("atr14",  0.001) or 0.001)
    rsi   = float(row.get("rsi14",  50)    or 50)
    mh    = float(row.get("macd_hist", 0)  or 0)
    mh_p  = float(prev.get("macd_hist",0)  or 0)
    bb_upper = float(row.get("bb_upper", 0) or 0)
    bb_lower = float(row.get("bb_lower", 0) or 0)
    adx   = float(row.get("adx", 20) or 20)
    bd    = {}; score = 0; warns = []
    regime = _detect_regime(df)

    # 1. H4 Trend (25 pts) — HARD GATE, non-negotiable
    h4t = _h4_trend(df_h4)
    h4_aligned = (direction=="Buy"  and h4t in ("bull","bull_weak")) or \
                 (direction=="Sell" and h4t in ("bear","bear_weak"))
    h4_opposed = (direction=="Buy"  and h4t in ("bear","bear_weak")) or \
                 (direction=="Sell" and h4t in ("bull","bull_weak"))
    if h4_aligned:          h4_pts = 25
    elif h4t == "neutral":  h4_pts = 10; warns.append("⚠ H4 neutral — no clear trend")
    else:                   h4_pts = 0;  warns.append("🚫 H4 OPPOSES this trade — high-risk")
    score += h4_pts; bd["H4 Trend"] = h4_pts

    # 2. PULLBACK QUALITY (25 pts) — THE MOST IMPORTANT FACTOR
    # Are we entering on a pullback or chasing momentum?
    ema_dist = _price_distance_from_ema(close, e20, atr)
    extended, move_atr = _is_extended(df, direction, atr)
    prev_close = float(prev["close"])
    approaching_e20 = abs(prev_close - e20) > abs(close - e20)

    if direction == "Buy":
        # Perfect: price pulled back to or below EMA20 and approaching from below
        if ema_dist <= 0 and approaching_e20:     pb = 25  # Below EMA20, bouncing up
        elif ema_dist <= 0.3 and approaching_e20: pb = 20  # Near EMA20, approaching
        elif ema_dist <= 0.5:                     pb = 15  # Close to EMA20
        elif ema_dist <= 1.0:                     pb = 8   # Slightly above
        elif ema_dist <= 1.5:                     pb = 3   # Getting far
        else:                                     pb = 0   # Chasing
        if extended: pb = max(0, pb - 15); warns.append(f"🚫 CHASING — price moved {move_atr}× ATR in 5 bars")
    else:
        if ema_dist >= 0 and approaching_e20:     pb = 25
        elif ema_dist >= -0.3 and approaching_e20: pb = 20
        elif ema_dist >= -0.5:                    pb = 15
        elif ema_dist >= -1.0:                    pb = 8
        elif ema_dist >= -1.5:                    pb = 3
        else:                                     pb = 0
        if _is_extended(df, "Sell", atr)[0]: pb = max(0, pb - 15); warns.append(f"🚫 CHASING — price already extended")
    score += pb; bd["Pullback"] = pb

    # 3. EMA Stack alignment (15 pts)
    if direction == "Buy":
        ep = (5 if e20>e50 else 0) + (5 if e50>e200 else 0) + (5 if close>e200 else 0)
    else:
        ep = (5 if e20<e50 else 0) + (5 if e50<e200 else 0) + (5 if close<e200 else 0)
    score += ep; bd["EMA Stack"] = ep

    # 4. RSI QUALITY (15 pts) — rewards ideal zones, PUNISHES extremes
    if direction == "Buy":
        if rsi < 35:        rp = 15  # Oversold in uptrend = perfect pullback
        elif rsi < 50:      rp = 12  # Below midline, good
        elif rsi < 60:      rp = 8   # Neutral, acceptable
        elif rsi < 70:      rp = 3   # Getting hot
        else:               rp = -5; warns.append(f"⚠ RSI {rsi:.0f} overbought — DON'T BUY")
    else:
        if rsi > 65:        rp = 15  # Overbought in downtrend = perfect
        elif rsi > 50:      rp = 12
        elif rsi > 40:      rp = 8
        elif rsi > 30:      rp = 3
        else:               rp = -5; warns.append(f"⚠ RSI {rsi:.0f} oversold — DON'T SELL")
    score += rp; bd["RSI"] = rp

    # 5. Candle pattern confirmation (10 pts)
    cp = _candle_score(df, direction)
    score += cp; bd["Candle"] = cp

    # 6. Session quality (5 pts)
    if c.get("asset_class") == "crypto":
        sp = 5
    else:
        sess_ok_, sess_name_ = session_ok(symbol)
        sp = 5 if sess_ok_ else 0
        if not sess_ok_: warns.append(f"⚠ Off-peak session — reduced quality")
    score += sp; bd["Session"] = sp

    # 7. MACD momentum (5 pts) — reduced weight, just confirmation
    if direction == "Buy":
        mp = 5 if mh > 0 and mh > mh_p else (2 if mh > mh_p else 0)
    else:
        mp = 5 if mh < 0 and mh < mh_p else (2 if mh < mh_p else 0)
    score += mp; bd["MACD"] = mp

    # 8. Regime bonus/penalty (store as info, not in score breakdown)
    if regime == "transitioning":
        score -= 5
        warns.append("⚠ Market transitioning (ADX 20-25) — be cautious")

    # 9. Volatility quality
    if len(df) >= 20:
        atr_arr = df["atr14"].dropna().tail(20)
        if len(atr_arr) >= 10:
            atr_mean = float(atr_arr.mean())
            atr_std = float(atr_arr.std())
            if atr_mean > 0 and atr_std / atr_mean > 0.4:
                score -= 5
                warns.append("⚠ Choppy market — ATR unstable")

    score = min(100, max(0, score))

    # Grade — H4 alignment strictly required for A/A+
    if   score >= c["grade_aplus"] and h4_pts >= 25: grade = "A+"
    elif score >= c["grade_a"]     and h4_pts >= 25: grade = "A"
    elif score >= c["grade_b"]     and h4_pts >= 10: grade = "B"
    elif score >= 45:                                 grade = "C"
    else:                                             grade = "D"

    # HARD CAP: chasing = never above B
    if extended:
        if grade in ("A+", "A"): grade = "B"

    # HARD CAP: H4 opposed = never above C
    if h4_opposed:
        if grade in ("A+", "A", "B"): grade = "C"

    return score, bd, grade, warns

def _gold_structure_check(df, direction):
    """
    Check market structure for gold: Higher-Highs/Higher-Lows for Buy,
    Lower-Highs/Lower-Lows for Sell. Uses last 30 bars.
    Returns True if structure supports direction.
    """
    if len(df) < 30:
        return False
    recent = df.tail(30)
    # Find swing points (3-bar pivot)
    highs = []; lows = []
    for idx in range(2, len(recent)-2):
        r = recent.iloc[idx]
        if r["high"] >= recent.iloc[idx-1]["high"] and r["high"] >= recent.iloc[idx-2]["high"] and \
           r["high"] >= recent.iloc[idx+1]["high"] and r["high"] >= recent.iloc[idx+2]["high"]:
            highs.append(float(r["high"]))
        if r["low"] <= recent.iloc[idx-1]["low"] and r["low"] <= recent.iloc[idx-2]["low"] and \
           r["low"] <= recent.iloc[idx+1]["low"] and r["low"] <= recent.iloc[idx+2]["low"]:
            lows.append(float(r["low"]))
    if len(highs) < 2 or len(lows) < 2:
        return True  # Not enough data, don't filter
    if direction == "Buy":
        # Higher highs AND higher lows
        hh = highs[-1] > highs[-2]
        hl = lows[-1] > lows[-2]
        return hh and hl
    else:
        # Lower highs AND lower lows
        lh = highs[-1] < highs[-2]
        ll = lows[-1] < lows[-2]
        return lh and ll

def determine_direction(df, df_h4, symbol=""):
    """
    STABLE DIRECTION ENGINE V3.
    DIRECTION = H4 trend. Period. Direction does NOT flip on small moves.
    GRADE handles "is NOW a good time to enter" (pullback, extended, etc.)
    Direction only changes when H4 trend changes.
    """
    if len(df) < 30:
        return "Wait"

    row   = df.iloc[-1]
    close = float(row["close"])
    e20   = float(row.get("ema20",  close))
    e50   = float(row.get("ema50",  close))
    e200  = float(row.get("ema200", close))
    rsi   = float(row.get("rsi14", 50) or 50)
    atr   = float(row.get("atr14", 0.001) or 0.001)
    bb_upper = float(row.get("bb_upper", 0) or 0)
    bb_lower = float(row.get("bb_lower", 0) or 0)

    h4t = _h4_trend(df_h4)
    regime = _detect_regime(df)

    # ════════════════════════════════════════════════════
    # RULE 1: H4 TREND = DIRECTION (stable, doesn't flip easily)
    # H4 bull/bull_weak → Buy. H4 bear/bear_weak → Sell.
    # Whether to ENTER NOW is decided by the Grade, not direction.
    # ════════════════════════════════════════════════════
    if h4t in ("bull", "bull_weak"):
        return "Buy"
    if h4t in ("bear", "bear_weak"):
        return "Sell"

    # ════════════════════════════════════════════════════
    # RULE 2: H4 NEUTRAL → use EMA structure as tiebreaker
    # ════════════════════════════════════════════════════
    if e20 > e50 and e50 > e200 and close > e200:
        return "Buy"    # Strong bullish structure even if H4 neutral
    if e20 < e50 and e50 < e200 and close < e200:
        return "Sell"   # Strong bearish structure

    # ════════════════════════════════════════════════════
    # RULE 3: RANGING MARKET OVERRIDE (ADX < 20)
    # Only at BB extremes + RSI confirmation
    # ════════════════════════════════════════════════════
    if regime == "ranging":
        if bb_lower > 0 and close <= bb_lower and rsi < 30:
            return "Buy"
        if bb_upper > 0 and close >= bb_upper and rsi > 70:
            return "Sell"

    # No clear direction
    return "Wait"


def calculate_smart_entry(df, direction, close, atr, symbol):
    """
    SMART ENTRY V2 — always based on current price, anti-chase aware.
    MARKET = at key level now, enter immediately.
    LIMIT = set pending order at nearby pullback level.
    WAIT = no good level, skip this trade.
    """
    c = cfg(symbol)
    dec = c.get("dec", 5)
    row = df.iloc[-1]
    ema20  = float(row.get("ema20", close))
    ema50  = float(row.get("ema50", close))
    bb_upper = float(row.get("bb_upper", 0) or 0)
    bb_lower = float(row.get("bb_lower", 0) or 0)
    rsi = float(row.get("rsi14", 50) or 50)
    regime = _detect_regime(df)

    # ── Anti-chase check first ──
    extended, move_atr = _is_extended(df, direction, atr)
    ema_dist = abs(close - ema20) / atr if atr > 0 else 0

    # If price is extended, force WAIT regardless
    if extended and ema_dist > 1.5:
        return {
            "entry_price": round(ema20, dec),
            "entry_type": "WAIT",
            "quality": 1,
            "stars": "★☆☆☆☆",
            "reason": f"Price extended {move_atr}× ATR — wait for pullback to EMA20",
        }

    # ── Find key levels ──
    support = close - atr * 3
    resistance = close + atr * 3
    if len(df) >= 15:
        lookback = df.tail(60)
        for i in range(2, len(lookback) - 2):
            r = lookback.iloc[i]
            h, l = float(r["high"]), float(r["low"])
            w = lookback.iloc[i-2:i+3]
            if l <= w["low"].min() and l < close:
                if l > support: support = l
            if h >= w["high"].max() and h > close:
                if h < resistance: resistance = h

    # ── Am I at a key level RIGHT NOW? ──
    at_ema20 = abs(close - ema20) < atr * 0.5
    at_support = direction == "Buy" and abs(close - support) < atr * 0.5
    at_resistance = direction == "Sell" and abs(close - resistance) < atr * 0.5
    at_bb = (direction == "Buy" and bb_lower > 0 and abs(close - bb_lower) < atr * 0.5) or \
            (direction == "Sell" and bb_upper > 0 and abs(close - bb_upper) < atr * 0.5)

    if at_ema20 or at_support or at_resistance or at_bb:
        reason = "At EMA20" if at_ema20 else ("At support" if at_support else ("At resistance" if at_resistance else "At BB band"))
        quality = 3
        if at_ema20: quality += 1
        if (direction == "Buy" and rsi < 45) or (direction == "Sell" and rsi > 55): quality += 1
        quality = min(5, quality)
        return {
            "entry_price": round(close, dec),  # ALWAYS current price for MARKET
            "entry_type": "MARKET",
            "quality": quality,
            "stars": "★" * quality + "☆" * (5 - quality),
            "reason": f"{reason} @ {round(close, dec)}",
        }

    # ── Not at key level — find nearest LIMIT level ──
    candidates = []
    if direction == "Buy":
        if ema20 < close and close - ema20 < atr * 1.5:
            candidates.append(("EMA20 pullback", ema20, close - ema20))
        if support < close and close - support < atr * 2:
            candidates.append(("Support level", support, close - support))
        if bb_lower > 0 and bb_lower < close and close - bb_lower < atr * 2:
            candidates.append(("BB Lower band", bb_lower, close - bb_lower))
    else:
        if ema20 > close and ema20 - close < atr * 1.5:
            candidates.append(("EMA20 pullback", ema20, ema20 - close))
        if resistance > close and resistance - close < atr * 2:
            candidates.append(("Resistance level", resistance, resistance - close))
        if bb_upper > 0 and bb_upper > close and bb_upper - close < atr * 2:
            candidates.append(("BB Upper band", bb_upper, bb_upper - close))

    if candidates:
        candidates.sort(key=lambda x: x[2])
        best_name, best_price, best_dist = candidates[0]
        quality = 2
        if best_dist < atr * 0.5: quality += 1
        if (direction == "Buy" and rsi < 45) or (direction == "Sell" and rsi > 55): quality += 1
        quality = min(5, max(1, quality))
        return {
            "entry_price": round(best_price, dec),
            "entry_type": "LIMIT",
            "quality": quality,
            "stars": "★" * quality + "☆" * (5 - quality),
            "reason": f"{best_name} @ {round(best_price, dec)}",
        }

    # ── No good level at all → WAIT ──
    return {
        "entry_price": round(close, dec),
        "entry_type": "WAIT",
        "quality": 1,
        "stars": "★☆☆☆☆",
        "reason": "No key level nearby — wait for better setup",
    }


def compute_levels(entry, direction, atr, symbol, df=None):
    """
    Smart SL/TP: uses swing highs/lows when available, ATR fallback.
    TP1 targets nearest reachable swing level (min R:R 1.5).
    TP2 uses ATR extension beyond TP1.
    """
    c = cfg(symbol)
    min_rr = c.get("min_rr", 1.5)

    # ── SL: ATR-based (proven reliable) ───────────────────────
    sl_d = atr * c["atr_sl"]
    if direction == "Buy":
        sl = entry - sl_d
    else:
        sl = entry + sl_d

    # ── TP1: ATR-based (proven reliable) ──────────────────────
    tp1_d = atr * c["atr_tp1"]
    if direction == "Buy":
        tp1 = entry + tp1_d
    else:
        tp1 = entry - tp1_d

    # ── TP2: ATR extension beyond TP1 ─────────────────────────
    tp2_extra = atr * c["atr_sl"] * 2
    if direction == "Buy":
        tp2 = tp1 + tp2_extra
    else:
        tp2 = tp1 - tp2_extra

    # ── Safety check: ensure SL/TP on correct side ─────────
    if direction == "Buy":
        if sl >= entry:   # SL must be BELOW entry for Buy
            sl = entry - sl_d
        if tp1 <= entry:  # TP1 must be ABOVE entry for Buy
            tp1 = entry + atr * c["atr_tp1"]
            tp1_d = tp1 - entry
            tp2 = tp1 + tp2_extra
    else:
        if sl <= entry:   # SL must be ABOVE entry for Sell
            sl = entry + sl_d
        if tp1 >= entry:  # TP1 must be BELOW entry for Sell
            tp1 = entry - atr * c["atr_tp1"]
            tp1_d = entry - tp1
            tp2 = tp1 - tp2_extra

    rr = tp1_d / sl_d if sl_d > 0 else 0
    return {"sl":sl,"tp1":tp1,"tp2":tp2,"sl_d":sl_d,"tp1_d":tp1_d,"rr":rr}

def _is_overextended(df, direction, atr, threshold=3.0):
    """Check if price has moved too far too fast (overextended)."""
    if len(df) < 20:
        return False
    close = float(df.iloc[-1]["close"])
    close_20 = float(df.iloc[-20]["close"])
    move = abs(close - close_20)
    if move > atr * threshold:
        return True
    rsi = float(df.iloc[-1].get("rsi14", 50) or 50)
    if direction == "Buy" and rsi > 75 and move > atr * 2:
        return True
    if direction == "Sell" and rsi < 25 and move > atr * 2:
        return True
    return False

# ── Spike Detection System ────────────────────────────────────
def detect_spike(df, atr, symbol, lookback=5):
    """
    Detect sudden price spikes (news/liquidity events).
    Returns dict: {is_spike, direction, magnitude, spike_atr_ratio, alert_level}
    - alert_level: "none" | "warning" | "danger" | "opportunity"
    """
    if len(df) < lookback + 2:
        return {"is_spike": False, "direction": None, "magnitude": 0,
                "spike_atr_ratio": 0, "alert_level": "none", "message": ""}

    c = cfg(symbol)
    asset = c.get("asset_class", "forex")

    # Spike thresholds vary by asset class
    spike_thresholds = {
        "forex":  {"warn": 2.0, "danger": 3.5, "opportunity": 4.5},
        "gold":   {"warn": 2.5, "danger": 4.0, "opportunity": 5.5},
        "oil":    {"warn": 2.5, "danger": 4.0, "opportunity": 5.5},
        "crypto": {"warn": 3.0, "danger": 5.0, "opportunity": 7.0},
    }
    th = spike_thresholds.get(asset, spike_thresholds["forex"])

    # Check last bar's range vs ATR
    last = df.iloc[-1]
    bar_range = abs(float(last["high"]) - float(last["low"]))
    ratio = bar_range / atr if atr > 0 else 0

    # Check momentum: last N bars cumulative move
    recent_close = float(df.iloc[-1]["close"])
    past_close   = float(df.iloc[-(lookback+1)]["close"])
    move = abs(recent_close - past_close)
    move_ratio = move / atr if atr > 0 else 0
    spike_dir = "Bull" if recent_close > past_close else "Bear"

    # Body ratio (large body = conviction, small body = wick spike)
    body = abs(float(last["close"]) - float(last["open"]))
    body_ratio = body / bar_range if bar_range > 0 else 0

    # Determine spike level
    effective_ratio = max(ratio, move_ratio)

    if effective_ratio >= th["opportunity"]:
        # Massive spike — could be opportunity for reversal or continuation
        if body_ratio > 0.6:
            alert = "opportunity"
            msg = f"🚀 SPIKE {spike_dir.upper()} — {effective_ratio:.1f}× ATR | Strong momentum, potential continuation"
        else:
            alert = "danger"
            msg = f"⚠️ SPIKE {spike_dir.upper()} — {effective_ratio:.1f}× ATR | Wick rejection, avoid entry"
    elif effective_ratio >= th["danger"]:
        alert = "danger"
        msg = f"🔴 SPIKE {spike_dir.upper()} — {effective_ratio:.1f}× ATR | High volatility, widen SL or stay out"
    elif effective_ratio >= th["warn"]:
        alert = "warning"
        msg = f"🟡 Elevated volatility — {effective_ratio:.1f}× ATR | Monitor closely"
    else:
        alert = "none"
        msg = ""

    return {
        "is_spike": effective_ratio >= th["warn"],
        "direction": spike_dir,
        "magnitude": round(move, c["dec"]),
        "spike_atr_ratio": round(effective_ratio, 2),
        "body_ratio": round(body_ratio, 2),
        "alert_level": alert,
        "message": msg,
    }

def spike_adjusted_levels(entry, direction, atr, symbol, spike_info, df=None):
    """
    Adjust SL/TP when spike is detected:
    - Danger: widen SL by 50%, keep TP
    - Opportunity: normal SL, extend TP2
    """
    lvl = compute_levels(entry, direction, atr, symbol, df=df)
    if not spike_info.get("is_spike"):
        return lvl

    alert = spike_info["alert_level"]
    if alert == "danger":
        # Widen SL to account for spike volatility
        wider_sl_d = lvl["sl_d"] * 1.5
        if direction == "Buy":
            lvl["sl"] = entry - wider_sl_d
        else:
            lvl["sl"] = entry + wider_sl_d
        lvl["sl_d"] = wider_sl_d
        # Recalculate R:R
        lvl["rr"] = lvl["tp1_d"] / wider_sl_d if wider_sl_d > 0 else 0
    elif alert == "opportunity":
        # Extend TP2 for spike continuation
        c = cfg(symbol)
        extended_tp2 = atr * c["atr_tp2"] * 1.5
        if direction == "Buy":
            lvl["tp2"] = entry + extended_tp2
        else:
            lvl["tp2"] = entry - extended_tp2

    return lvl

# ============================================================
# GOLD ENGINE — Professional XAUUSD Trading System
# ============================================================
def _gold_asian_range(df):
    """
    Calculate Asian session range (00:00-08:00 UTC).
    Returns dict: {high, low, range, valid}
    """
    if "time" not in df.columns or len(df) < 20:
        return {"high": 0, "low": 0, "range": 0, "valid": False}

    try:
        times = pd.to_datetime(df["time"], utc=True)
    except Exception:
        return {"high": 0, "low": 0, "range": 0, "valid": False}

    today = times.iloc[-1].normalize()
    asian_mask = (times >= today) & (times.dt.hour < 8)
    asian_bars = df.loc[asian_mask]

    if len(asian_bars) < 3:
        # Try yesterday's Asian session
        yesterday = today - pd.Timedelta(days=1)
        asian_mask = (times >= yesterday) & (times < today) & (times.dt.hour < 8)
        asian_bars = df.loc[asian_mask]

    if len(asian_bars) < 3:
        return {"high": 0, "low": 0, "range": 0, "valid": False}

    ah = float(asian_bars["high"].max())
    al = float(asian_bars["low"].min())
    return {"high": ah, "low": al, "range": ah - al, "valid": True}

def _gold_breakout_signal(df, asian_range, atr):
    """
    Detect London breakout of Asian range.
    Returns: "bull_breakout" | "bear_breakout" | "inside" | "invalid"
    """
    if not asian_range["valid"] or asian_range["range"] == 0:
        return "invalid"

    close = float(df.iloc[-1]["close"])
    ah = asian_range["high"]
    al = asian_range["low"]

    # Need clear breakout (at least 0.3× ATR beyond range)
    margin = atr * 0.3
    if close > ah + margin:
        return "bull_breakout"
    elif close < al - margin:
        return "bear_breakout"
    return "inside"

def _gold_liquidity_sweep(df, atr, lookback=30):
    """
    Detect liquidity sweep: price spikes beyond recent high/low then reverses.
    This is a classic institutional pattern.
    Returns: {"detected": bool, "direction": "bull"/"bear", "sweep_level": float}
    """
    if len(df) < lookback + 5:
        return {"detected": False, "direction": None, "sweep_level": 0}

    recent = df.iloc[-(lookback+5):-5]
    last5  = df.iloc[-5:]

    recent_high = float(recent["high"].max())
    recent_low  = float(recent["low"].min())
    last_high   = float(last5["high"].max())
    last_low    = float(last5["low"].min())
    close       = float(df.iloc[-1]["close"])

    sweep_margin = atr * 0.5

    # Bearish sweep: price spiked ABOVE recent high then closed back below → sell signal
    if last_high > recent_high + sweep_margin and close < recent_high:
        return {"detected": True, "direction": "bear", "sweep_level": recent_high}

    # Bullish sweep: price spiked BELOW recent low then closed back above → buy signal
    if last_low < recent_low - sweep_margin and close > recent_low:
        return {"detected": True, "direction": "bull", "sweep_level": recent_low}

    return {"detected": False, "direction": None, "sweep_level": 0}

def _gold_supply_demand_zones(df, lookback=80):
    """
    Identify Supply & Demand zones based on strong impulse moves.
    Supply zone = origin of strong bearish move. Demand zone = origin of strong bullish move.
    """
    zones = {"supply": [], "demand": []}
    if len(df) < lookback:
        return zones
    data = df.tail(lookback)
    atr = float(data.iloc[-1].get("atr14", 1.0) or 1.0)
    threshold = atr * 1.5
    for i in range(1, len(data) - 1):
        curr = data.iloc[i]
        body = abs(float(curr["close"]) - float(curr["open"]))
        if body > threshold:
            if float(curr["close"]) < float(curr["open"]):
                zones["supply"].append({
                    "high": float(curr["high"]),
                    "low": float(curr["open"]),
                    "strength": body / atr
                })
            else:
                zones["demand"].append({
                    "high": float(curr["open"]),
                    "low": float(curr["low"]),
                    "strength": body / atr
                })
    zones["supply"] = sorted(zones["supply"], key=lambda z: z["strength"], reverse=True)[:3]
    zones["demand"] = sorted(zones["demand"], key=lambda z: z["strength"], reverse=True)[:3]
    return zones

def _gold_price_in_zone(close, zones, atr):
    """Check if price is in any supply or demand zone."""
    margin = atr * 0.3
    for z in zones.get("supply", []):
        if z["low"] - margin <= close <= z["high"] + margin:
            return "supply"
    for z in zones.get("demand", []):
        if z["low"] - margin <= close <= z["high"] + margin:
            return "demand"
    return None

def _gold_fvg_detection(df, direction, lookback=50):
    """
    Detect Fair Value Gap (FVG) — imbalance between 3 consecutive candles.
    Bullish FVG: candle3.low > candle1.high (gap up). Bearish FVG: candle3.high < candle1.low.
    """
    if len(df) < lookback:
        return {"detected": False, "type": None, "level": 0}
    data = df.tail(lookback)
    fvgs = []
    for i in range(2, len(data)):
        c1 = data.iloc[i-2]
        c3 = data.iloc[i]
        gap_bull = float(c3["low"]) - float(c1["high"])
        gap_bear = float(c1["low"]) - float(c3["high"])
        if gap_bull > 0:
            fvgs.append({"type": "bullish", "top": float(c3["low"]), "bottom": float(c1["high"]), "size": gap_bull})
        elif gap_bear > 0:
            fvgs.append({"type": "bearish", "top": float(c1["low"]), "bottom": float(c3["high"]), "size": gap_bear})
    if not fvgs:
        return {"detected": False, "type": None, "level": 0}
    close = float(data.iloc[-1]["close"])
    atr = float(data.iloc[-1].get("atr14", 1.0) or 1.0)
    for fvg in reversed(fvgs):
        if fvg["type"] == "bullish" and direction == "Buy":
            if fvg["bottom"] - atr <= close <= fvg["top"] + atr:
                return {"detected": True, "type": "bullish_fvg", "level": fvg["bottom"]}
        elif fvg["type"] == "bearish" and direction == "Sell":
            if fvg["bottom"] - atr <= close <= fvg["top"] + atr:
                return {"detected": True, "type": "bearish_fvg", "level": fvg["top"]}
    return {"detected": False, "type": None, "level": 0}

def _gold_choch_detection(df, lookback=40):
    """
    Change of Character (CHoCH) — detect when market structure shifts.
    Bullish CHoCH: price breaks above recent swing high after making lower lows.
    Bearish CHoCH: price breaks below recent swing low after making higher highs.
    """
    if len(df) < lookback:
        return {"detected": False, "direction": None}
    data = df.tail(lookback)
    swing_highs = []
    swing_lows = []
    for i in range(2, len(data) - 2):
        r = data.iloc[i]
        if float(r["high"]) >= max(float(data.iloc[i-1]["high"]), float(data.iloc[i-2]["high"]),
                                    float(data.iloc[i+1]["high"]), float(data.iloc[i+2]["high"])):
            swing_highs.append(float(r["high"]))
        if float(r["low"]) <= min(float(data.iloc[i-1]["low"]), float(data.iloc[i-2]["low"]),
                                   float(data.iloc[i+1]["low"]), float(data.iloc[i+2]["low"])):
            swing_lows.append(float(r["low"]))
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return {"detected": False, "direction": None}
    close = float(data.iloc[-1]["close"])
    if swing_lows[-1] < swing_lows[-2] and close > swing_highs[-1]:
        return {"detected": True, "direction": "bullish"}
    if swing_highs[-1] > swing_highs[-2] and close < swing_lows[-1]:
        return {"detected": True, "direction": "bearish"}
    return {"detected": False, "direction": None}

def _gold_killzone_bonus():
    """
    ICT Killzone timing for gold.
    London Killzone: 07:00-09:00 UTC — highest gold volatility.
    NY Killzone: 12:00-14:00 UTC — second major move.
    Returns bonus points.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    h = now.hour
    if 7 <= h <= 8:
        return 8, "London Killzone"
    elif 12 <= h <= 13:
        return 8, "NY Killzone"
    elif 9 <= h <= 11:
        return 3, "London Session"
    elif 14 <= h <= 16:
        return 3, "NY Session"
    elif 13 <= h <= 14:
        return 6, "London/NY Overlap"
    else:
        return -3, "Off-hours"

def _gold_rsi_divergence(df, direction, lookback=30):
    """
    Detect RSI divergence — price making new high/low but RSI not confirming.
    Bullish div: price lower low + RSI higher low. Bearish div: price higher high + RSI lower high.
    """
    if len(df) < lookback:
        return {"detected": False, "type": None}
    data = df.tail(lookback)
    swing_data = []
    for i in range(2, len(data) - 2):
        r = data.iloc[i]
        rsi = float(r.get("rsi14", 50) or 50)
        is_high = float(r["high"]) >= max(float(data.iloc[i-1]["high"]), float(data.iloc[i+1]["high"]))
        is_low = float(r["low"]) <= min(float(data.iloc[i-1]["low"]), float(data.iloc[i+1]["low"]))
        if is_high:
            swing_data.append({"type": "high", "price": float(r["high"]), "rsi": rsi})
        if is_low:
            swing_data.append({"type": "low", "price": float(r["low"]), "rsi": rsi})
    swing_highs = [s for s in swing_data if s["type"] == "high"]
    swing_lows = [s for s in swing_data if s["type"] == "low"]
    if direction == "Buy" and len(swing_lows) >= 2:
        if (swing_lows[-1]["price"] < swing_lows[-2]["price"] and
            swing_lows[-1]["rsi"] > swing_lows[-2]["rsi"] + 3):
            return {"detected": True, "type": "bullish_divergence"}
    if direction == "Sell" and len(swing_highs) >= 2:
        if (swing_highs[-1]["price"] > swing_highs[-2]["price"] and
            swing_highs[-1]["rsi"] < swing_highs[-2]["rsi"] - 3):
            return {"detected": True, "type": "bearish_divergence"}
    return {"detected": False, "type": None}

def _gold_momentum_filter(df, direction):
    """
    Gold-specific momentum: checks multiple timeframe momentum alignment.
    Returns bonus score (0-15).
    """
    if len(df) < 50:
        return 0

    close = float(df.iloc[-1]["close"])
    # Short-term momentum (5 bars)
    c5 = float(df.iloc[-6]["close"])
    mom5 = close - c5
    # Medium momentum (20 bars)
    c20 = float(df.iloc[-21]["close"])
    mom20 = close - c20

    score = 0
    if direction == "Sell":
        if mom5 < 0:  score += 5   # short-term bearish
        if mom20 < 0: score += 5   # medium bearish
        # Acceleration: momentum increasing
        if mom5 < mom20 * 0.3: score += 5
    else:  # Buy
        if mom5 > 0:  score += 5
        if mom20 > 0: score += 5
        if mom5 > mom20 * 0.3: score += 5

    return score

def _gold_candle_quality(df, direction):
    """
    Gold-specific candle quality check.
    Looks for momentum candles, pin bars, and rejection patterns.
    Returns score 0-10.
    """
    if len(df) < 3:
        return 0
    c = df.iloc[-1]; p = df.iloc[-2]
    body = abs(float(c["close"]) - float(c["open"]))
    rng = float(c["high"]) - float(c["low"])
    if rng == 0:
        return 0
    body_ratio = body / rng

    score = 0
    if direction == "Buy":
        # Bullish momentum candle: large body, close near high
        upper_wick = float(c["high"]) - max(float(c["close"]), float(c["open"]))
        if float(c["close"]) > float(c["open"]) and body_ratio > 0.6:
            score += 5
        # Bullish pin bar: long lower wick, small body at top
        lower_wick = min(float(c["close"]), float(c["open"])) - float(c["low"])
        if lower_wick > body * 2 and upper_wick < body:
            score += 5
        # Close above previous high
        if float(c["close"]) > float(p["high"]):
            score += 3
    else:
        # Bearish momentum candle
        lower_wick = min(float(c["close"]), float(c["open"])) - float(c["low"])
        if float(c["close"]) < float(c["open"]) and body_ratio > 0.6:
            score += 5
        # Bearish pin bar: long upper wick
        upper_wick = float(c["high"]) - max(float(c["close"]), float(c["open"]))
        if upper_wick > body * 2 and lower_wick < body:
            score += 5
        # Close below previous low
        if float(c["close"]) < float(p["low"]):
            score += 3

    return min(10, score)

def gold_engine_score(df, df_h4, df_h1, direction, base_score, base_grade):
    """
    Gold-specific scoring overlay V2 — Multi-Timeframe + Smart Money hybrid.
    H4: trend direction. H1: structure & zones. Entry TF: entry signals.
    Returns: (adjusted_score, gold_info_dict, adjusted_grade, extra_warns)
    """
    row   = df.iloc[-1]
    atr   = float(row.get("atr14", 0.001) or 0.001)
    close = float(row["close"])
    c = cfg("XAUUSD")
    extra_warns = []
    gold_info = {}
    bonus = 0
    confirmations = 0
    contradictions = 0

    # ── MODULE 1: Multi-Timeframe Trend Alignment ────────────
    h4t = _h4_trend(df_h4)
    h1t = _h4_trend(df_h1) if df_h1 is not None and len(df_h1) >= 50 else "neutral"
    # Entry TF trend from EMA9/21
    e9  = float(row.get("ema9", close))
    e21 = float(row.get("ema21", close))
    entry_trend = "bull" if e9 > e21 else ("bear" if e9 < e21 else "neutral")

    gold_info["h4_trend"] = h4t
    gold_info["h1_trend"] = h1t
    gold_info["entry_trend"] = entry_trend

    # All 3 timeframes aligned = strong bonus
    dir_lower = "bull" if direction == "Buy" else "bear"
    h4_ok = dir_lower in h4t
    h1_ok = dir_lower in h1t
    entry_ok = entry_trend == dir_lower

    aligned_count = sum([h4_ok, h1_ok, entry_ok])
    if aligned_count == 3:
        bonus += 15
        confirmations += 1
        gold_info["mtf_alignment"] = "perfect"
    elif aligned_count == 2:
        bonus += 8
        gold_info["mtf_alignment"] = "good"
    elif aligned_count == 1:
        bonus += 0
        gold_info["mtf_alignment"] = "weak"
        extra_warns.append("⚠ Only 1/3 timeframes aligned — weak setup")
    else:
        bonus -= 10
        contradictions += 1
        gold_info["mtf_alignment"] = "opposed"
        extra_warns.append("🚫 All timeframes OPPOSE direction — avoid trade")

    # ── MODULE 2: Supply & Demand Zones ──────────────────────
    # Use H1 data for better zone detection (wider view)
    zone_df = df_h1 if df_h1 is not None and len(df_h1) >= 50 else df
    zones = _gold_supply_demand_zones(zone_df, lookback=80)
    zone_position = _gold_price_in_zone(close, zones, atr)
    gold_info["zones"] = {"supply_count": len(zones["supply"]), "demand_count": len(zones["demand"]), "position": zone_position}

    if zone_position == "demand" and direction == "Buy":
        bonus += 10
        confirmations += 1
        extra_warns.append("🏦 Price in DEMAND zone — supports Buy")
    elif zone_position == "supply" and direction == "Sell":
        bonus += 10
        confirmations += 1
        extra_warns.append("🏦 Price in SUPPLY zone — supports Sell")
    elif zone_position == "demand" and direction == "Sell":
        bonus -= 8
        contradictions += 1
        extra_warns.append("⚠ Price in DEMAND zone — risky Sell")
    elif zone_position == "supply" and direction == "Buy":
        bonus -= 8
        contradictions += 1
        extra_warns.append("⚠ Price in SUPPLY zone — risky Buy")

    # ── MODULE 3: Fair Value Gap (FVG) ───────────────────────
    fvg = _gold_fvg_detection(df, direction, lookback=50)
    gold_info["fvg"] = fvg
    if fvg["detected"]:
        bonus += 8
        confirmations += 1
        extra_warns.append(f"📊 FVG detected ({fvg['type']}) near {fvg['level']:.2f}")

    # ── MODULE 4: Change of Character (CHoCH) ────────────────
    choch = _gold_choch_detection(df, lookback=40)
    gold_info["choch"] = choch
    if choch["detected"]:
        if (choch["direction"] == "bullish" and direction == "Buy") or \
           (choch["direction"] == "bearish" and direction == "Sell"):
            bonus += 10
            confirmations += 1
            extra_warns.append(f"🔄 CHoCH detected — structure shift {choch['direction']}")
        else:
            bonus -= 8
            contradictions += 1
            extra_warns.append(f"⚠ CHoCH OPPOSES direction — {choch['direction']} shift detected")

    # ── MODULE 5: ICT Killzone Timing ────────────────────────
    kz_bonus, kz_name = _gold_killzone_bonus()
    bonus += kz_bonus
    gold_info["killzone"] = kz_name
    if kz_bonus >= 6:
        confirmations += 1
        extra_warns.append(f"⏰ {kz_name} active — prime gold trading time")
    elif kz_bonus < 0:
        extra_warns.append(f"⚠ {kz_name} — low volatility, avoid gold trades")

    # ── MODULE 6: RSI Divergence ─────────────────────────────
    rsi_div = _gold_rsi_divergence(df, direction, lookback=30)
    gold_info["rsi_divergence"] = rsi_div
    if rsi_div["detected"]:
        bonus += 8
        confirmations += 1
        extra_warns.append(f"📈 RSI Divergence: {rsi_div['type']} — reversal signal")

    # ── MODULE 7: Liquidity Sweep ────────────────────────────
    sweep = _gold_liquidity_sweep(df, atr)
    gold_info["sweep"] = sweep
    if sweep["detected"]:
        if (sweep["direction"] == "bear" and direction == "Sell") or \
           (sweep["direction"] == "bull" and direction == "Buy"):
            bonus += 10
            confirmations += 1
            extra_warns.append(f"🏦 Liquidity sweep — institutional {direction.lower()} signal")
        else:
            bonus -= 8
            contradictions += 1
            extra_warns.append(f"⚠ Liquidity sweep OPPOSES {direction}")

    # ── MODULE 8: Asian Range Breakout ───────────────────────
    asian = _gold_asian_range(df)
    gold_info["asian_range"] = asian
    if asian["valid"]:
        breakout = _gold_breakout_signal(df, asian, atr)
        gold_info["breakout"] = breakout
        if (breakout == "bear_breakout" and direction == "Sell") or \
           (breakout == "bull_breakout" and direction == "Buy"):
            bonus += 8
            confirmations += 1
        elif breakout == "inside":
            bonus -= 3
            extra_warns.append("⚠ Gold inside Asian range — wait for breakout")

    # ── MODULE 9: Gold Momentum Filter ───────────────────────
    mom_bonus = _gold_momentum_filter(df, direction)
    gold_info["momentum_bonus"] = mom_bonus
    bonus += mom_bonus
    if mom_bonus >= 10:
        confirmations += 1

    # ── MODULE 10: Overextension Guard ───────────────────────
    if len(df) >= 20:
        c20 = float(df.iloc[-20]["close"])
        move_20 = abs(close - c20)
        if move_20 > atr * 4:
            bonus -= 10
            contradictions += 1
            extra_warns.append(f"⚠ Gold overextended: {move_20:.2f} in 20 bars ({move_20/atr:.1f}× ATR)")

    # ── MODULE 11: Market Structure ──────────────────────────
    structure_ok = _gold_structure_check(df, direction)
    gold_info["structure_ok"] = structure_ok
    if structure_ok:
        bonus += 5
        confirmations += 1
    else:
        bonus -= 5
        extra_warns.append("⚠ Market structure does not support direction")

    # ── FINAL SCORING ────────────────────────────────────────
    gold_info["confirmations"] = confirmations
    gold_info["contradictions"] = contradictions
    gold_info["bonus"] = bonus

    # Safety: if too many contradictions vs confirmations, cap the score
    if contradictions >= 3 and confirmations < contradictions:
        bonus = min(bonus, -15)
        extra_warns.append("🛑 Too many contradicting signals — trade not recommended")

    adjusted_score = min(100, max(0, base_score + bonus))
    gold_info["adjusted_score"] = adjusted_score

    # Re-grade with adjusted score + STRICT safety gates
    # A/A+ requires H4 alignment (h4_pts=25 from base score)
    if   adjusted_score >= c["grade_aplus"] and h4_ok: adjusted_grade = "A+"
    elif adjusted_score >= c["grade_a"]     and h4_ok: adjusted_grade = "A"
    elif adjusted_score >= c["grade_b"]:               adjusted_grade = "B"
    elif adjusted_score >= 45:                          adjusted_grade = "C"
    else:                                               adjusted_grade = "D"

    # ── HARD CAPS: prevent inflated grades ──

    # CAP 1: H4 opposes → max C (not even B)
    if not h4_ok:
        if adjusted_grade in ("A+", "A", "B"):
            adjusted_grade = "C"
            extra_warns.append("🚫 H4 OPPOSES — observe only")

    # CAP 2: 3+ contradictions → max B
    if contradictions >= 3:
        if adjusted_grade in ("A+", "A"):
            adjusted_grade = "B"

    # CAP 3: MTF alignment "opposed" → max C
    if gold_info.get("mtf_alignment") == "opposed":
        if adjusted_grade in ("A+", "A", "B"):
            adjusted_grade = "C"

    # CAP 4: Anti-chase — if price extended, max B
    _ext, _ext_atr = _is_extended(df, direction, atr)
    if _ext:
        if adjusted_grade in ("A+", "A"):
            adjusted_grade = "B"
            extra_warns.append(f"🚫 Price extended {_ext_atr}× ATR — don't chase")

    return adjusted_score, gold_info, adjusted_grade, extra_warns

def compute_lot(balance, risk_pct, sl_pips, symbol):
    pip_val = {"USDJPY":9.1,"GBPJPY":9.1,"EURJPY":9.1,
               "XAUUSD":10.0,"XTIUSD":10.0,
               "BTCUSD":1.0,"ETHUSD":1.0}.get(norm(symbol),10.0)
    pip_sz  = cfg(symbol).get("pip",0.0001)
    if sl_pips <= 0: return 0.01
    risk_amt = balance * risk_pct / 100
    lot = risk_amt / (sl_pips * pip_val)
    return round(max(0.01, min(lot, 100.0)), 2)

@st.cache_data(ttl=300)   # 5 min — K-lines don't need to refresh every 15s
def analyze_symbol(symbol, interval, bars, td_key):
    """
    Full analysis for one symbol.
    Returns dict with df, df_h4, direction, score, grade, levels, session, warns.
    """
    try:
        df   = add_indicators(fetch_bars(symbol, interval, bars, td_key))
        df_h4= add_indicators(fetch_bars(symbol, "4h", 200, td_key))
        df_h1 = None
        if norm(symbol) == "XAUUSD":
            try:
                df_h1 = add_indicators(fetch_bars(symbol, "1h", 200, td_key))
            except Exception:
                df_h1 = None
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

    row      = df.iloc[-1]
    close    = float(row["close"])
    atr      = float(row.get("atr14", 0.001) or 0.001)
    direction= determine_direction(df, df_h4, symbol)

    score, bd, grade, warns = score_signal(df, df_h4, symbol, direction)

    # ── Gold Engine overlay (XAUUSD only) ─────────────────────
    gold_info = {}
    if norm(symbol) == "XAUUSD":
        score, gold_info, grade, gold_warns = gold_engine_score(
            df, df_h4, df_h1, direction, score, grade)
        warns.extend(gold_warns)
        bd["Gold Engine"] = gold_info.get("bonus", 0)

    # ── Spike detection (same engine as backtest) ─────────────
    spike_info = detect_spike(df, atr, symbol, lookback=5)
    if spike_info["is_spike"]:
        levels = spike_adjusted_levels(close, direction, atr, symbol, spike_info, df=df)
    else:
        levels = compute_levels(close, direction, atr, symbol, df=df)
    sess_ok_, sess_name = session_ok(symbol)

    rsi_val = float(row.get("rsi14",50) or 50)
    macd_hist_val = float(row.get("macd_hist",0) or 0)
    macd_val = float(row.get("macd",0) or 0)
    ema20_val = float(row.get("ema20",close))
    ema50_val = float(row.get("ema50",close))
    ema200_val = float(row.get("ema200",close))
    bb_upper = float(row.get("bb_upper",0) or 0)
    bb_lower = float(row.get("bb_lower",0) or 0)

    # ── Smart Entry ────────────────────────────────────────────
    smart_entry = calculate_smart_entry(df, direction, close, atr, symbol)

    # ── GROK PRIMARY ANALYSIS ─────────────────────────────────
    grok_result = None
    xai_key = get_xai_key()
    if xai_key:
        try:
            last_10 = df[["open","high","low","close"]].tail(10).round(cfg(symbol)["dec"]).to_string(index=False)
            grok_result = grok_primary_analysis(
                symbol=symbol, close=close, atr=atr, rsi=rsi_val,
                macd_val=macd_val, macd_hist=macd_hist_val,
                ema20=ema20_val, ema50=ema50_val, ema200=ema200_val,
                h4_trend=_h4_trend(df_h4), session_name=sess_name,
                calc_direction=direction, calc_score=score, calc_grade=grade,
                sl_calc=levels["sl"], tp1_calc=levels["tp1"], tp2_calc=levels["tp2"],
                last_10_bars_str=last_10, xai_key=xai_key,
                bb_upper=bb_upper, bb_lower=bb_lower,
            )
        except Exception:
            grok_result = None

    return {
        "symbol": symbol, "df": df, "df_h4": df_h4, "df_h1": df_h1,
        "close": close, "atr": atr,
        "direction": direction, "score": score, "bd": bd, "grade": grade, "warns": warns,
        "sl": levels["sl"], "tp1": levels["tp1"], "tp2": levels["tp2"],
        "rr": levels["rr"], "sl_d": levels["sl_d"],
        "rsi": rsi_val,
        "macd_hist": macd_hist_val,
        "ema20": ema20_val,
        "ema50": ema50_val,
        "ema200": ema200_val,
        "session": sess_name, "session_ok": sess_ok_,
        "h4_trend": _h4_trend(df_h4),
        "spike": spike_info,
        "gold": gold_info,
        "smart_entry": smart_entry,
        "grok": grok_result,  # Grok-primary AI analysis
        "error": None,
    }

# ============================================================
# TRADE JOURNAL
# ============================================================
def load_journal():
    try:
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE) as f: return json.load(f)
    except: pass
    return []

def save_journal(journal):
    try:
        with open(JOURNAL_FILE,"w") as f: json.dump(journal, f, indent=2)
    except: pass

def log_trade(trade, exit_price, result, notes=""):
    j = load_journal()
    entry  = float(trade["entry"]); sl = float(trade["sl"])
    ex     = float(exit_price)
    risk   = abs(entry - sl)
    dir_   = trade["direction"]
    move   = (ex-entry) if dir_=="Buy" else (entry-ex)
    pnl_r  = round(move/risk,2) if risk > 0 else 0
    j.append({
        "id": trade.get("id","?")[:6],
        "ts": pd.Timestamp.utcnow().isoformat()[:16],
        "symbol": trade.get("symbol","?"),
        "direction": dir_, "entry": entry, "sl": sl,
        "exit": ex, "lot": trade.get("lot",0.01),
        "result": result, "pnl_r": pnl_r,
        "grade": trade.get("locked_grade","?"),
        "score": trade.get("locked_score",0),
        "session": trade.get("session","?"),
        "notes": notes,
    })
    save_journal(j)
    return j

def journal_stats(journal):
    if not journal: return {}
    total = len(journal); wins = sum(1 for t in journal if t.get("result")=="Win")
    losses = sum(1 for t in journal if t.get("result")=="Loss")
    bes    = sum(1 for t in journal if t.get("result")=="BE")
    wr     = wins/total*100 if total else 0
    all_r  = [t.get("pnl_r",0) for t in journal]
    gross_p= sum(r for r in all_r if r>0)
    gross_l= abs(sum(r for r in all_r if r<0))
    pf     = gross_p/gross_l if gross_l>0 else 0
    return {"total":total,"wins":wins,"losses":losses,"bes":bes,
            "wr":wr,"total_r":sum(all_r),"avg_r":sum(all_r)/total if total else 0,
            "pf":pf,"gross_p":gross_p,"gross_l":gross_l}

# ============================================================
# SHARED UI COMPONENTS
# ============================================================
def _prog_bar(pct, color="#00d4aa"):
    f = max(0,min(int(pct),100))
    return (f"<div style='height:4px;background:rgba(255,255,255,0.08);border-radius:2px;margin-top:3px;'>"
            f"<div style='width:{f}%;height:100%;background:{color};border-radius:2px;'></div></div>")

def _tp_pct(tp, entry, live, direction):
    try:
        tf=float(tp); e=float(entry)
        total=abs(tf-e)
        if total==0: return None
        if direction=="Buy"  and tf<=e: return 0
        if direction=="Sell" and tf>=e: return 0
        done=(live-e) if direction=="Buy" else (e-live)
        if done<=0: return 0
        return min(int(done/total*100),100)
    except: return None

def render_grade_badge(grade, score=None):
    gc = grade_color(grade)
    sc = f" <span style='font-size:11px;color:#8b9ab0;'>({score})</span>" if score is not None else ""
    st.markdown(
        f"<div style='display:inline-block;background:rgba(255,255,255,0.05);border:1px solid {gc};"
        f"border-radius:6px;padding:6px 16px;font-family:Space Mono,monospace;font-size:22px;"
        f"font-weight:700;color:{gc};letter-spacing:.05em;'>{grade}{sc}</div>",
        unsafe_allow_html=True)

def render_direction_badge(direction):
    if direction == "Buy":
        color="#10b981"; bg="rgba(16,185,129,.12)"; border="rgba(16,185,129,.3)"
    elif direction == "Sell":
        color="#ef4444"; bg="rgba(239,68,68,.12)"; border="rgba(239,68,68,.3)"
    else:
        color="#f59e0b"; bg="rgba(245,158,11,.12)"; border="rgba(245,158,11,.3)"
    st.markdown(
        f"<div style='display:inline-block;background:{bg};border:1px solid {border};"
        f"border-radius:8px;padding:8px 20px;font-family:Space Mono,monospace;font-size:14px;"
        f"font-weight:700;color:{color};letter-spacing:.08em;'>{'▲ ' if direction=='Buy' else ('▼ ' if direction=='Sell' else '◈ ')}{direction.upper()}</div>",
        unsafe_allow_html=True)

def render_kv(label, value, color="#e8edf2"):
    st.markdown(
        f"<div class='kv'><span class='muted'>{label}</span>"
        f"<span style='color:{color};font-family:Space Mono,monospace;font-size:12px;'>{value}</span></div>",
        unsafe_allow_html=True)

def render_score_breakdown(bd, score, grade):
    gc = grade_color(grade)
    html = (f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.07);"
            f"border-radius:8px;padding:12px 14px;'>"
            f"<div class='mono-title'>SIGNAL SCORE</div>"
            f"<div style='font-family:Space Mono,monospace;font-size:28px;font-weight:700;"
            f"color:{gc};margin-bottom:10px;'>{score} <span style='font-size:14px;'>{grade}</span></div>")
    maxes = {"H4 Trend":25,"Pullback":25,"EMA Stack":15,"RSI":15,"Candle":10,"Session":5,"MACD":5}
    for k, v in bd.items():
        if not isinstance(v, (int, float)): continue  # skip non-numeric entries
        mx  = maxes.get(k, 10)
        pct = int(v/mx*100) if mx else 0
        bar_col = "#00d4aa" if pct>=80 else "#f59e0b" if pct>=40 else "#ef4444"
        html += (f"<div style='display:flex;align-items:center;gap:8px;margin:3px 0;font-size:11px;'>"
                 f"<span style='color:#8b9ab0;width:70px;'>{k}</span>"
                 f"<div style='background:#131a22;border-radius:3px;flex:1;height:5px;'>"
                 f"<div style='width:{pct}%;height:100%;background:{bar_col};border-radius:3px;'></div></div>"
                 f"<span style='color:{bar_col};width:28px;text-align:right;font-family:Space Mono,monospace;'>{v}</span></div>")
    html += f"<div style='height:4px;background:#131a22;border-radius:2px;margin-top:8px;overflow:hidden;'><div style='width:{score}%;height:100%;background:{gc};border-radius:2px;'></div></div></div>"
    st.markdown(html, unsafe_allow_html=True)

def render_price_chart(df, symbol, entry=None, sl=None, tp1=None, tp2=None, title="PRICE CHART"):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.6,0.2,0.2],
                        subplot_titles=["","MACD","RSI"],
                        vertical_spacing=0.04)
    # Candlestick
    fig.add_trace(go.Candlestick(x=df["time"],open=df["open"],high=df["high"],
                                  low=df["low"],close=df["close"],name="Price",
                                  increasing_line_color="#10b981",decreasing_line_color="#ef4444"),row=1,col=1)
    for col_, c_ in [("ema20","#f59e0b"),("ema50","#8b5cf6"),("ema200","#3b82f6")]:
        if col_ in df.columns:
            fig.add_trace(go.Scatter(x=df["time"],y=df[col_],name=col_.upper(),
                                     line=dict(color=c_,width=1),opacity=0.8),row=1,col=1)
    if "bb_upper" in df.columns:
        for bk, bn in [("bb_upper","BB Upper"),("bb_lower","BB Lower")]:
            fig.add_trace(go.Scatter(x=df["time"],y=df[bk],name=bn,
                                     line=dict(color="#94a3b8",width=1,dash="dot"),opacity=0.5),row=1,col=1)
    # Level lines
    if entry: fig.add_hline(y=entry, line_color="#00d4aa", line_dash="dash", line_width=1, row=1, col=1)
    if sl:    fig.add_hline(y=sl,    line_color="#ef4444", line_dash="dash", line_width=1, row=1, col=1)
    if tp1:   fig.add_hline(y=tp1,   line_color="#10b981", line_dash="dash", line_width=1, row=1, col=1)
    if tp2:   fig.add_hline(y=tp2,   line_color="#84cc16", line_dash="dot",  line_width=1, row=1, col=1)
    # MACD
    if "macd_hist" in df.columns:
        colors_ = ["#10b981" if v>=0 else "#ef4444" for v in df["macd_hist"]]
        fig.add_trace(go.Bar(x=df["time"],y=df["macd_hist"],name="MACD Hist",
                             marker_color=colors_,opacity=0.8),row=2,col=1)
        fig.add_trace(go.Scatter(x=df["time"],y=df.get("macd",df["macd_hist"]*0),
                                 line=dict(color="#3b82f6",width=1),name="MACD"),row=2,col=1)
    # RSI
    if "rsi14" in df.columns:
        fig.add_trace(go.Scatter(x=df["time"],y=df["rsi14"],
                                 line=dict(color="#a78bfa",width=1.5),name="RSI"),row=3,col=1)
        fig.add_hline(y=70, line_color="#ef4444", line_dash="dot", line_width=1, row=3, col=1)
        fig.add_hline(y=30, line_color="#10b981", line_dash="dot", line_width=1, row=3, col=1)
    fig.update_layout(
        title=title, paper_bgcolor="#080c10", plot_bgcolor="#080c10",
        font=dict(color="#e8edf2",size=11), height=520,
        xaxis_rangeslider_visible=False, showlegend=True,
        legend=dict(orientation="h",y=1.02,bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0,r=0,t=30,b=0))
    for axis in ["xaxis","yaxis","xaxis2","yaxis2","xaxis3","yaxis3"]:
        fig.update_layout(**{axis:dict(gridcolor="rgba(255,255,255,0.05)",
                                       zerolinecolor="rgba(255,255,255,0.1)")})
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# MULTI-TRADE TRACKER COMPONENT
# ============================================================
def render_trade_tracker(symbol, current_price, a=None, td_key=""):
    """Renders Trade Tracker for a specific symbol. Returns (entry,sl,dir) of first active trade or None."""
    if "active_trades" not in st.session_state:
        st.session_state.active_trades = []

    trades = st.session_state.active_trades
    sym_trades = [t for t in trades if t.get("symbol","") == symbol]

    st.markdown("<div class='panel'><div class='mono-title'>TRADE TRACKER</div>", unsafe_allow_html=True)

    # ── Enter New Trade ──
    with st.expander(f"▶ New Trade — {symbol}", expanded=(len(sym_trades)==0)):
        # Try to use analysis for defaults
        default_dir = a.get("direction","Buy") if a else "Buy"
        default_entry= float(current_price)
        # Recalculate levels using live price to prevent wrong-side SL/TP
        if a and abs(float(current_price) - a.get("close", current_price)) > a.get("atr", 1) * 0.3:
            _tracker_lvl = compute_levels(float(current_price), default_dir, a.get("atr", 0.001), symbol, df=a.get("df"))
            default_sl  = float(_tracker_lvl["sl"])
            default_tp1 = float(_tracker_lvl["tp1"])
            default_tp2 = float(_tracker_lvl["tp2"])
        else:
            default_sl   = float(a.get("sl", current_price)) if a else float(current_price)
            default_tp1  = float(a.get("tp1",current_price)) if a else float(current_price)
            default_tp2  = float(a.get("tp2",current_price)) if a else float(current_price)

        c1,c2 = st.columns(2)
        me  = c1.number_input("Entry",     value=default_entry, format=f"%.{cfg(symbol)['dec']}f", key=f"te_e_{symbol}")
        ms  = c2.number_input("Stop Loss", value=default_sl,    format=f"%.{cfg(symbol)['dec']}f", key=f"te_s_{symbol}")
        md  = c1.selectbox("Direction",["Buy","Sell"],index=0 if default_dir=="Buy" else 1,key=f"te_d_{symbol}")
        ml  = c2.number_input("Lot",value=0.01,format="%.2f",key=f"te_l_{symbol}")
        tc1,tc2 = st.columns(2)
        mt1 = tc1.number_input("TP1",value=default_tp1,format=f"%.{cfg(symbol)['dec']}f",key=f"te_t1_{symbol}")
        mt2 = tc2.number_input("TP2",value=default_tp2,format=f"%.{cfg(symbol)['dec']}f",key=f"te_t2_{symbol}")

        # Validation warnings
        sl_ok  = (ms<me and md=="Buy") or (ms>me and md=="Sell")
        tp1_ok = (mt1>me and md=="Buy") or (mt1<me and md=="Sell")
        if not sl_ok:  st.warning(f"⚠ SL is on wrong side for {md}")
        if not tp1_ok: st.warning(f"⚠ TP1 is on wrong side for {md}")

        if st.button("▶ Enter Trade", key=f"btn_enter_{symbol}"):
            # ── Validate trade before saving ──────────────────
            _valid = True
            if md == "Buy":
                if ms >= me: st.error("SL must be BELOW entry for Buy"); _valid = False
                if mt1 <= me: st.error("TP1 must be ABOVE entry for Buy"); _valid = False
            else:
                if ms <= me: st.error("SL must be ABOVE entry for Sell"); _valid = False
                if mt1 >= me: st.error("TP1 must be BELOW entry for Sell"); _valid = False
            if _valid:
                grade_lock = a.get("grade","?") if a else "?"
                score_lock = a.get("score",0)   if a else 0
                sess_lock  = a.get("session","?") if a else "?"
                st.session_state.active_trades.append({
                    "id": str(uuid.uuid4())[:8], "symbol": symbol,
                    "entry":me,"sl":ms,"direction":md,"lot":ml,"tp1":mt1,"tp2":mt2,
                    "locked_grade":grade_lock,"locked_score":score_lock,"session":sess_lock,
                })
                st.success(f"Trade entered: {symbol} {md}"); st.rerun()

    # ── Active trade cards ──
    if not sym_trades:
        st.markdown("<div style='font-size:12px;color:#4a5568;padding:8px 0;'>No open trades for this symbol.</div>", unsafe_allow_html=True)
    else:
        for t in sym_trades:
            tid   = t.get("id","0")
            t_dir = t["direction"]
            t_e   = float(t["entry"]); t_sl  = float(t["sl"])
            t_risk= abs(t_e-t_sl)
            dc    = "#10b981" if t_dir=="Buy" else "#ef4444"
            gc_   = grade_color(t.get("locked_grade","?"))

            # Live price (always for this trade's symbol)
            tick = fetch_mt5_price(symbol, get_ma_token_price(), get_ma_account_price()) if (get_ma_token_price() and get_ma_account_price()) else None
            live = tick["bid"] if tick else current_price
            plabel = f"MT5 {fmt_price(live,symbol)}" if tick else "TD~"
            pcol   = "#00d4aa" if tick else "#f59e0b"

            # P&L (direction-aware)
            move   = (live-t_e) if t_dir=="Buy" else (t_e-live)
            pnl_r  = move/t_risk if t_risk>0 else 0
            pnl_c  = "#10b981" if pnl_r>=0 else "#ef4444"

            tp1_p  = _tp_pct(t.get("tp1"), t_e, live, t_dir)
            tp2_p  = _tp_pct(t.get("tp2"), t_e, live, t_dir)

            st.markdown(
                f"<div style='border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:8px 10px;margin:5px 0;background:#090e14;'>"
                f"<div style='font-size:10px;color:#8b9ab0;margin-bottom:5px;'>"
                f"<b style='color:{dc};'>{t_dir}</b>  ·  {t.get('lot',0)} lot  "
                f"<span style='color:{gc_};'>{t.get('locked_grade','?')}</span>  "
                f"<span style='float:right;font-size:9px;color:#4a5568;'>#{tid}</span></div>"
                f"<div style='display:flex;gap:10px;flex-wrap:wrap;font-size:12px;margin-bottom:5px;'>"
                f"<div><span class='muted'>Entry</span><br><b style='color:#00d4aa;font-family:Space Mono,monospace;'>{fmt_price(t_e,symbol)}</b></div>"
                f"<div><span class='muted'>SL</span><br><b style='color:#ef4444;font-family:Space Mono,monospace;'>{fmt_price(t_sl,symbol)}</b></div>"
                f"<div><span class='muted'>P&L <span style='font-size:9px;color:{pcol};'>({plabel})</span></span><br>"
                f"<b style='color:{pnl_c};font-family:Space Mono,monospace;'>{pnl_r:+.2f}R</b></div></div>"
                f"<div style='display:flex;gap:10px;font-size:11px;'>"
                f"<div style='flex:1;'><span class='muted'>TP1</span> <b style='color:#10b981;font-family:Space Mono,monospace;'>{fmt_price(t.get('tp1'),symbol)}</b>"
                + (f" <span style='color:#8b9ab0;font-size:9px;'>{tp1_p}%</span>{_prog_bar(tp1_p,'#10b981')}" if tp1_p is not None else "") +
                f"</div><div style='flex:1;'><span class='muted'>TP2</span> <b style='color:#00d4aa;font-family:Space Mono,monospace;'>{fmt_price(t.get('tp2'),symbol)}</b>"
                + (f" <span style='color:#8b9ab0;font-size:9px;'>{tp2_p}%</span>{_prog_bar(tp2_p,'#00d4aa')}" if tp2_p is not None else "") +
                f"</div></div></div>", unsafe_allow_html=True)

            # ── SL Proximity danger warning ──────────────────────
            sl_dist   = abs(live - t_sl)
            sl_total  = abs(t_e  - t_sl)
            sl_pct    = (sl_dist / sl_total * 100) if sl_total > 0 else 100
            sl_pips   = round(sl_dist / cfg(symbol).get("pip", 0.0001), 1)
            if sl_pct <= 30:
                sl_pct_int = int(sl_pct)
                st.markdown(
                    f"<div style='background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.5);"
                    f"border-left:3px solid #ef4444;border-radius:6px;padding:7px 10px;margin:5px 0;"
                    f"animation:alertpulse 1.5s infinite;font-size:11px;color:#fca5a5;font-family:Space Mono,monospace;'>"
                    f"🚨 SL DANGER — Price is {sl_pips:.1f} pips from SL "
                    f"({sl_pct_int}% of SL distance remaining). Consider EXIT or MOVE SL.</div>",
                    unsafe_allow_html=True
                )
                # Browser alert — fire once when entering danger zone
                _dng_key = f"_danger_alerted_{tid}"
                if not st.session_state.get(_dng_key):
                    fire_danger_alert(symbol, sl_pips, sl_pct)
                    st.session_state[_dng_key] = True
            elif sl_pct <= 50:
                st.markdown(
                    f"<div style='background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);"
                    f"border-left:3px solid #f59e0b;border-radius:6px;padding:6px 10px;margin:5px 0;"
                    f"font-size:11px;color:#fcd34d;font-family:Space Mono,monospace;'>"
                    f"⚠ SL ALERT — {sl_pips:.1f} pips from SL ({int(sl_pct)}% remaining). Stay alert.</div>",
                    unsafe_allow_html=True
                )
            else:
                # Price recovered — reset danger alert so it fires again if it returns
                st.session_state.pop(f"_danger_alerted_{tid}", None)

            # ── TP1 hit alert ─────────────────────────────────────
            t_tp1_val = t.get("tp1"); t_tp2_val = t.get("tp2")
            if t_tp1_val:
                try:
                    _tp1f = float(t_tp1_val)
                    _tp1_hit = (t_dir == "Buy" and live >= _tp1f) or \
                               (t_dir == "Sell" and live <= _tp1f)
                    _tp1_alert_key = f"_tp1_hit_{tid}"
                    if _tp1_hit and not st.session_state.get(_tp1_alert_key):
                        fire_tp_alert(symbol, "TP1", fmt_price(_tp1f, symbol),
                                      fmt_price(float(t_tp2_val), symbol) if t_tp2_val else None)
                        st.session_state[_tp1_alert_key] = True
                        st.markdown(
                            f"<div style='background:rgba(16,185,129,0.12);border:1px solid #10b981;"
                            f"border-left:3px solid #10b981;border-radius:6px;padding:8px 12px;margin:6px 0;"
                            f"font-size:12px;color:#6ee7b7;font-family:Space Mono,monospace;animation:alertpulse 1.5s 3;'>"
                            f"🎯 TP1 HIT! Consider taking profit or trailing SL to TP2 @ {fmt_price(float(t_tp2_val), symbol) if t_tp2_val else '—'}"
                            f"</div>", unsafe_allow_html=True)
                except Exception:
                    pass

            # ── AI advisor button & response ──────────────────────
            ai_key   = f"_ai_advice_{tid}"
            btn_col, _ = st.columns([1, 3])
            with btn_col:
                if st.button("🤖 Ask AI", key=f"btn_ai_{tid}", help="Get HOLD / EXIT / MOVE SL recommendation from Grok"):
                    with st.spinner("Asking Grok…"):
                        advice = get_ai_trade_advice(
                            t, live,
                            a if a else {},
                            st.session_state.get("last_news_{}".format(symbol), {})
                        )
                    st.session_state[ai_key] = advice

            if st.session_state.get(ai_key):
                adv_text = st.session_state[ai_key]
                # Choose colour hint based on action word
                adv_upper = adv_text.upper()
                if "EXIT NOW" in adv_upper or "EXIT" in adv_upper[:60]:
                    adv_border = "#ef4444"; adv_bg = "rgba(239,68,68,0.07)"
                elif "MOVE SL" in adv_upper or "BREAKEVEN" in adv_upper:
                    adv_border = "#f59e0b"; adv_bg = "rgba(245,158,11,0.07)"
                elif "PARTIAL" in adv_upper:
                    adv_border = "#a78bfa"; adv_bg = "rgba(167,139,250,0.07)"
                else:
                    adv_border = "#6366f1"; adv_bg = "rgba(99,102,241,0.07)"
                st.markdown(
                    f"<div style='background:{adv_bg};border:1px solid {adv_border}44;"
                    f"border-left:3px solid {adv_border};border-radius:8px;"
                    f"padding:10px 13px;margin:4px 0 8px;font-size:12px;color:#c7d2fe;line-height:1.75;'>"
                    f"<span style='font-size:10px;color:{adv_border};font-family:Space Mono,monospace;"
                    f"letter-spacing:.08em;'>🤖 GROK ADVISOR</span><br><br>"
                    + adv_text.replace("\n","<br>") +
                    f"</div>", unsafe_allow_html=True
                )
                clr_col, _ = st.columns([1, 4])
                with clr_col:
                    if st.button("✕ Clear advice", key=f"btn_ai_clr_{tid}"):
                        st.session_state.pop(ai_key, None); st.rerun()

            ck = f"_closing_{tid}"
            if not st.session_state.get(ck):
                if st.button(f"✕ Close #{tid}", key=f"btn_cl_{tid}"):
                    st.session_state[ck] = True; st.rerun()
            else:
                st.markdown(f"<div style='font-size:11px;color:#f59e0b;font-family:Space Mono,monospace;margin:4px 0;'>LOG TRADE #{tid}</div>", unsafe_allow_html=True)
                ep   = st.number_input("Exit Price", value=float(live), format=f"%.{cfg(symbol)['dec']}f", key=f"j_ep_{tid}")
                res  = st.selectbox("Result",["Win","Loss","BE"],key=f"j_res_{tid}")
                note = st.text_input("Notes",key=f"j_note_{tid}",placeholder="e.g. news spike, early exit...")
                cc1,cc2 = st.columns(2)
                if cc1.button("💾 Save & Close", key=f"btn_sc_{tid}"):
                    log_trade(t, ep, res, note)
                    st.session_state.active_trades = [x for x in st.session_state.active_trades if x.get("id")!=tid]
                    st.session_state.pop(ck,None)
                    st.success("Trade logged!"); st.rerun()
                if cc2.button("Cancel", key=f"btn_cc_{tid}"):
                    st.session_state.pop(ck,None); st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    if sym_trades:
        t0 = sym_trades[0]
        return t0["entry"], t0["sl"], t0["direction"]
    return None

# ============================================================
# AUTO PRE-MARKET / DAILY BIAS (Grok)
# ============================================================
@st.cache_data(ttl=3600)  # 1-hour cache — auto-refreshes each hour
def _auto_premarket_bias(xai_key: str, symbols_csv: str, cal_text: str, hist_text: str):
    """
    Auto-generate per-symbol bias using Grok.
    Returns dict like {"EURUSD": {"bias":"bull","conf":"HIGH","note":"..."}, ...}
    Cached 1 hour so it doesn't spam the API.
    """
    now_utc = pd.Timestamp.utcnow()
    msg = (
        f"QUICK MARKET BIAS — {now_utc.strftime('%Y-%m-%d %H:%M UTC')} ({now_utc.strftime('%A')})\n"
        f"Symbols: {symbols_csv}\n"
    )
    if cal_text:
        msg += f"\nUPCOMING EVENTS:\n{cal_text}\n"
    if hist_text:
        msg += f"\nTRADER PERFORMANCE:\n{hist_text}\n"
    msg += (
        f"\nFor EACH symbol return a JSON object with:\n"
        f'  "SYM": {{"bias":"bull|bear|neutral","conf":"HIGH|MED|LOW","note":"<12 words max>"}}\n'
        f"Return ONLY a single JSON object containing all symbols. No markdown.\n"
        f"Base your bias on: current trends, upcoming events, session timing, and the trader's personal data."
    )
    raw = _grok([
        {"role":"system","content":"You are a forex analyst. Return ONLY valid JSON. "
         f"UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}"},
        {"role":"user","content":msg}
    ], max_tokens=600, temperature=0.1, api_key=xai_key)
    if not raw or raw.startswith("[Grok"):
        return {}
    try:
        return json.loads(re.sub(r"```json|```","",raw).strip())
    except Exception:
        return {}

def _get_premarket_data():
    """Gather calendar + history data and call auto bias. Returns bias dict."""
    xai_key = get_xai_key()
    if not xai_key:
        return {}
    # Economic calendar
    cal_text = ""
    te_key = get_te_key()
    if te_key:
        events = fetch_te_calendar(te_key)
        if events:
            lines = []
            for e in events[:15]:
                imp = "HIGH" if e["importance"]=="HIGH" else e["importance"]
                lines.append(f"  {e['date'].strftime('%a %H:%M')} [{e['country'].title()}] [{imp}] {e['event']}")
            cal_text = "\n".join(lines)
    # Trader history
    hist_text = ""
    if _sb_ok():
        journal = sb_get("journal", "order=closed_at.desc&limit=50")
        if journal:
            df_j = pd.DataFrame(journal)
            df_j["pnl_r"] = pd.to_numeric(df_j["pnl_r"], errors="coerce").fillna(0)
            try:
                by_sym = df_j.groupby("symbol").agg(
                    trades=("pnl_r","count"),
                    wr=("outcome", lambda x: f"{(x=='WIN').sum()}/{len(x)}"),
                    avg_r=("pnl_r","mean")
                ).round(2)
                hist_text = by_sym.to_string()
            except Exception:
                pass
    return _auto_premarket_bias(xai_key, ",".join(ACTIVE_SYMBOLS), cal_text, hist_text)

# ============================================================
# PAGE 1 — MARKET OVERVIEW
# ============================================================
def page_overview():
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;letter-spacing:.12em;padding:4px 0 16px;'>◈ MARKET OVERVIEW</div>", unsafe_allow_html=True)

    td_key = get_td_key()
    if not td_key:
        st.warning("⚠ Add your Twelve Data API key in the sidebar to load analysis.")
        return

    # AI Market Bias removed — Grok Primary Analysis now covers fundamentals
    # in its unified signal output (no more separate bias badges that can conflict)

    interval = st.session_state.get("ov_interval","15min")
    cols = st.columns(3)

    for i, sym in enumerate(ACTIVE_SYMBOLS):
        is_open, mkt = market_is_open(sym)
        with cols[i % 3]:
            with st.spinner(f"Loading {sym}..."):
                a = analyze_symbol(sym, interval, 400, td_key)
            if a.get("error"):
                st.error(f"{sym}: {a['error']}")
                continue
            gc   = grade_color(a["grade"])
            dc   = "#10b981" if a["direction"]=="Buy" else ("#ef4444" if a["direction"]=="Sell" else "#f59e0b")
            mkt_col = "#10b981" if mkt in ("LIVE","24/7") else "#f59e0b"
            sess_col= "#10b981" if a["session_ok"] else "#4a5568"
            # MT5 price if available
            tick = fetch_mt5_price(sym, get_ma_token_price(), get_ma_account_price())
            price = tick["bid"] if tick else a["close"]
            price_src = "MT5" if tick else "TD"

            # Spike alert for this symbol
            sp_info = a.get("spike", {})
            spike_html = ""
            if sp_info.get("is_spike"):
                sp_lvl = sp_info["alert_level"]
                sp_col = "#ef4444" if sp_lvl == "danger" else ("#f59e0b" if sp_lvl == "warning" else "#a78bfa")
                sp_bg  = "rgba(239,68,68,0.1)" if sp_lvl == "danger" else ("rgba(245,158,11,0.1)" if sp_lvl == "warning" else "rgba(167,139,250,0.1)")
                spike_html = (
                    f"<div style='background:{sp_bg};border:1px solid {sp_col}44;border-radius:4px;"
                    f"padding:3px 8px;font-size:10px;color:{sp_col};font-family:Space Mono,monospace;"
                    f"margin-top:4px;'>{sp_info['message']}</div>")

            # ── AI data ───────────────────────────────────────────
            grok = a.get("grok")
            if grok and not grok.get("error"):
                grok_ai_r = grok.get("ai_rating", 0)
                ai_dir = grok.get("direction", a["direction"])
                ai_action = grok.get("action", "WAIT")
                ai_conf = grok.get("confidence", "LOW")
                # News impact
                news_html = ""
                news_imp = grok.get("news_impact","")
                if news_imp:
                    news_html = f"<div style='font-size:10px;color:#a78bfa;margin-top:4px;font-family:Space Mono,monospace;'>📰 {news_imp}</div>"
                # Risk warning
                risk_html = ""
                risk_warn = grok.get("risk_warning","")
                if risk_warn and risk_warn.lower() != "none":
                    risk_html = f"<div style='font-size:10px;color:#f59e0b;margin-top:3px;font-family:Space Mono,monospace;'>⚠ {risk_warn}</div>"
            else:
                # Fallback: no Grok data
                grok_ai_r = 0
                ai_dir = a["direction"]
                ai_action = a["direction"]
                ai_conf = ""
                news_html = ""
                risk_html = ""

            st.markdown(
                f"<div style='background:#0d1117;border:1px solid {'rgba(239,68,68,0.3)' if sp_info.get('alert_level') == 'danger' else 'rgba(255,255,255,0.07)'};border-radius:10px;"
                f"padding:14px 16px;margin-bottom:12px;cursor:pointer;"
                f"{'animation:alertpulse 2s infinite;' if sp_info.get('alert_level') == 'danger' else ''}'>"
                # Header: Symbol + Market status
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
                f"<span style='font-family:Space Mono,monospace;font-size:14px;font-weight:700;color:#e8edf2;'>{sym}</span>"
                f"<span style='font-size:10px;color:{mkt_col};font-family:Space Mono,monospace;'>{mkt}</span></div>"
                # Price
                f"<div style='font-family:Space Mono,monospace;font-size:20px;font-weight:700;color:#e8edf2;margin-bottom:8px;'>{fmt_price(price,sym)}"
                f"<span style='font-size:10px;color:#4a5568;margin-left:4px;'>{price_src}</span></div>"
                # Score + Grade + Direction
                f"<div style='display:flex;gap:8px;align-items:center;margin-bottom:6px;'>"
                f"<span style='font-family:Space Mono,monospace;font-size:22px;font-weight:900;color:{gc};"
                f"background:rgba(255,255,255,0.04);padding:2px 12px;border-radius:6px;border:2px solid {gc};'>"
                f"{a['grade']} ({a['score']})</span>"
                f"<span style='font-family:Space Mono,monospace;font-size:13px;font-weight:700;color:{dc};'>"
                f"{'▲' if a['direction']=='Buy' else ('▼' if a['direction']=='Sell' else '◈')} {a['direction']}</span>"
                f"<span style='font-size:10px;color:{'#10b981' if ai_dir == a['direction'] else '#f59e0b'};font-family:Space Mono,monospace;'>"
                f"{'AI ✅' if ai_dir == a['direction'] else 'AI ⚠'}</span>"
                f"</div>"
                # Technicals row
                f"<div style='display:flex;gap:12px;font-size:11px;'>"
                f"<span style='color:#8b9ab0;'>H4: <span style='color:#e8edf2;'>{a['h4_trend']}</span></span>"
                f"<span style='color:#8b9ab0;'>RSI: <span style='color:#e8edf2;'>{fmt_num(a['rsi'],1)}</span></span>"
                f"<span style='color:{sess_col};'>{a['session']}</span></div>"
                # Levels row
                f"<div style='display:flex;gap:12px;font-size:11px;margin-top:4px;'>"
                f"<span class='muted'>SL <b style='color:#ef4444;'>{fmt_price(a['sl'],sym)}</b></span>"
                f"<span class='muted'>TP1 <b style='color:#10b981;'>{fmt_price(a['tp1'],sym)}</b></span>"
                f"<span class='muted'>R:R <b style='color:#a78bfa;'>{fmt_num(a['rr'],1)}:1</b></span></div>"
                + news_html + risk_html + spike_html +
                f"</div>",
                unsafe_allow_html=True)
            if a["warns"]:
                for w in a["warns"][:2]:
                    st.markdown(f"<div style='font-size:10px;color:#f59e0b;margin:-8px 0 6px;padding-left:2px;'>{w}</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<div style='font-size:11px;color:#4a5568;font-family:Space Mono,monospace;'>Grades use H4-first scoring · AI bias auto-updates hourly · ATR-based SL/TP per asset class</div>", unsafe_allow_html=True)

# ============================================================
# PAGE 2 — SYMBOL PAGE
# ============================================================
def page_symbol(symbol):
    cfg_ = SYMBOL_CONFIG[symbol]
    td_key = get_td_key()
    is_open, mkt = market_is_open(symbol)

    st.markdown(f"<div style='font-family:Space Mono,monospace;font-size:16px;color:#00d4aa;letter-spacing:.1em;padding:4px 0 12px;'>◈ {cfg_['name']} — {symbol}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:11px;color:#8b9ab0;margin-bottom:12px;font-family:Space Mono,monospace;'>{cfg_['note']}</div>", unsafe_allow_html=True)

    # Interval selector — Gold defaults to 5 Min for scalping
    _default_int = 0 if norm(symbol) == "XAUUSD" else 1
    int_col, _, __ = st.columns([1,2,2])
    with int_col:
        int_label = st.selectbox("Interval", list(INTERVAL_OPTIONS.keys()),
                                 index=_default_int, key=f"int_{symbol}")
    interval = INTERVAL_OPTIONS[int_label]
    bars = 400

    if not td_key:
        st.warning("⚠ Add your Twelve Data API key in the sidebar.")
        return

    with st.spinner(f"Loading {symbol} data..."):
        a = analyze_symbol(symbol, interval, bars, td_key)

    if a.get("error"):
        st.error(f"Error loading {symbol}: {a['error']}")
        return

    # MT5 live price
    tick  = fetch_mt5_price(symbol, get_ma_token_price(), get_ma_account_price())
    price = tick["bid"] if tick else a["close"]

    # ── Recalculate SL/TP if live price differs from cached close ──
    # This prevents SL/TP from being on the wrong side when price moves
    _price_drift = abs(price - a["close"])
    if _price_drift > a["atr"] * 0.3:  # Significant price change since cache
        _live_levels = compute_levels(price, a["direction"], a["atr"], symbol, df=a["df"])
        a["sl"]   = _live_levels["sl"]
        a["tp1"]  = _live_levels["tp1"]
        a["tp2"]  = _live_levels["tp2"]
        a["rr"]   = _live_levels["rr"]
        a["sl_d"] = _live_levels["sl_d"]

    # ── Top bar ──────────────────────────────────────────────
    t1, t1b, t2, t3, t4 = st.columns([1.5,1.5,3,1.5,1])
    with t1: render_direction_badge(a["direction"])
    with t1b: render_grade_badge(a["grade"], a["score"])
    with t2:
        pc = "#10b981" if price >= a["close"] else "#ef4444"
        chg = price - a["close"]
        price_src = f"MT5 {fmt_price(tick['bid'],symbol)}/{fmt_price(tick['ask'],symbol)}" if tick else "Twelve Data"
        st.markdown(
            f"<div style='font-family:Space Mono,monospace;font-size:22px;font-weight:700;padding-top:4px;'>"
            f"{fmt_price(price,symbol)}"
            f"<span style='font-size:12px;color:{pc};'> {chg:+.{cfg_['dec']}f}</span>"
            f"<span style='font-size:10px;color:#4a5568;margin-left:8px;'>{price_src}</span></div>",
            unsafe_allow_html=True)
    with t3:
        # AI double-confirm status
        _g = a.get("grok")
        _g_dir = _g.get("direction", a["direction"]) if _g and not _g.get("error") else a["direction"]
        _g_agrees = _g_dir == a["direction"]
        _g_col = "#10b981" if _g_agrees else "#f59e0b"
        _g_txt = "AI ✅" if _g_agrees else "AI ⚠"
        st.markdown(f"<div style='font-family:Space Mono,monospace;font-size:11px;color:{_g_col};padding-top:8px;'>{_g_txt}</div>", unsafe_allow_html=True)
    with t4:
        mkt_c = "#10b981" if mkt=="LIVE" else "#f59e0b"
        st.markdown(f"<span style='font-family:Space Mono,monospace;font-size:11px;color:{mkt_c};'>{mkt}</span>",unsafe_allow_html=True)

    # ── AI ANALYSIS PANEL ────────────────────────────────────
    grok = a.get("grok")
    if grok and not grok.get("error"):
        grok_ai_r = grok.get("ai_rating", 0)
        ai_dir = grok.get("direction", a["direction"])
        ai_action = grok.get("action", "WAIT")
        ai_conf = grok.get("confidence", "LOW")
        ai_col = "#10b981" if grok_ai_r >= 7 else ("#f59e0b" if grok_ai_r >= 5 else "#ef4444")
        ai_dc  = "#10b981" if ai_dir=="Buy" else ("#ef4444" if ai_dir=="Sell" else "#8b9ab0")
        conf_col = "#10b981" if ai_conf=="HIGH" else ("#f59e0b" if ai_conf=="MEDIUM" else "#4a5568")
        border_col = ai_col
        agrees = grok.get("agrees_with_calculator", ai_dir == a["direction"])

        reasoning = grok.get("reasoning", "")
        key_factors = grok.get("key_factors", [])
        news_imp = grok.get("news_impact", "")
        risk_warn = grok.get("risk_warning", "")
        factors_html = "".join(f"<span style='font-size:10px;color:#a78bfa;background:rgba(167,139,250,0.1);"
                               f"padding:2px 8px;border-radius:3px;margin-right:6px;'>{f}</span>" for f in key_factors[:4])

        # AI as secondary reference — no big rating, no direction, just text insight
        _agree_icon = "✅ Agrees" if agrees else "⚠ Disagrees"
        _agree_col = "#10b981" if agrees else "#f59e0b"
        st.markdown(
            f"<div style='background:rgba(13,17,23,0.8);border:1px solid rgba(255,255,255,0.08);"
            f"border-radius:8px;padding:12px 16px;margin:12px 0;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
            f"<span style='font-family:Space Mono,monospace;font-size:10px;color:#8b9ab0;letter-spacing:.1em;'>AI REFERENCE (Grok)</span>"
            f"<span style='font-size:10px;color:{_agree_col};font-family:Space Mono,monospace;'>"
            f"{_agree_icon} with Calculator | Ref: {grok_ai_r}/10</span></div>"
            # Reasoning text only
            f"<div style='font-size:12px;color:#c9d1d9;margin-bottom:8px;line-height:1.5;'>{reasoning}</div>"
            # Key factors
            f"<div style='margin-bottom:6px;'>{factors_html}</div>"
            # News + Risk
            + (f"<div style='font-size:11px;color:#a78bfa;margin-bottom:4px;'>📰 {news_imp}</div>" if news_imp else "")
            + (f"<div style='font-size:11px;color:#f59e0b;'>⚠ {risk_warn}</div>" if risk_warn and risk_warn.lower() != "none" else "")
            + f"</div>",
            unsafe_allow_html=True)

    # ── Warnings ─────────────────────────────────────────────
    if a["warns"]:
        for w in a["warns"]:
            st.markdown(f"<div style='background:rgba(245,158,11,0.08);border-left:3px solid #f59e0b;border-radius:4px;padding:6px 12px;margin:3px 0;font-size:12px;color:#f59e0b;'>{w}</div>", unsafe_allow_html=True)

    # ── Spike Alert ──────────────────────────────────────────
    sp_info = a.get("spike", {})
    if sp_info.get("is_spike"):
        sp_lvl = sp_info["alert_level"]
        sp_col = "#ef4444" if sp_lvl == "danger" else ("#f59e0b" if sp_lvl == "warning" else "#a78bfa")
        sp_bg  = "rgba(239,68,68,0.12)" if sp_lvl == "danger" else ("rgba(245,158,11,0.08)" if sp_lvl == "warning" else "rgba(167,139,250,0.08)")
        sp_border = sp_col
        advice = ""
        if sp_lvl == "danger":
            advice = " | <b>Recommendation: STAY OUT or widen SL</b>"
        elif sp_lvl == "opportunity":
            advice = " | <b>Potential spike continuation trade</b>"
        st.markdown(
            f"<div style='background:{sp_bg};border:1px solid {sp_col}44;border-left:3px solid {sp_col};"
            f"border-radius:6px;padding:10px 14px;margin:6px 0;font-size:12px;color:{sp_col};"
            f"font-family:Space Mono,monospace;'>"
            f"<b>SPIKE DETECTED</b> — {sp_info['message']}{advice}<br>"
            f"<span style='font-size:10px;color:#8b9ab0;'>ATR Ratio: {sp_info['spike_atr_ratio']}x "
            f"| Body: {sp_info.get('body_ratio',0)*100:.0f}% | Dir: {sp_info['direction']}</span></div>",
            unsafe_allow_html=True)

    # ── Gold Engine Panel (XAUUSD only) ────────────────────────
    gi = a.get("gold", {})
    if gi and norm(symbol) == "XAUUSD":
        ar = gi.get("asian_range", {})
        bo = gi.get("breakout", "no_data")
        sw = gi.get("sweep", {})
        bonus = gi.get("bonus", 0)
        confirmations = gi.get("confirmations", 0)
        contradictions = gi.get("contradictions", 0)

        # MTF display
        h4t_g = gi.get("h4_trend", "neutral")
        h1t_g = gi.get("h1_trend", "neutral")
        et_g  = gi.get("entry_trend", "neutral")
        mtf_align = gi.get("mtf_alignment", "unknown")
        def _tf_col(t): return "#10b981" if "bull" in str(t) else ("#ef4444" if "bear" in str(t) else "#f59e0b")
        def _tf_icon(t): return "▲" if "bull" in str(t) else ("▼" if "bear" in str(t) else "◈")
        mtf_col = {"perfect": "#10b981", "good": "#84cc16", "weak": "#f59e0b", "opposed": "#ef4444"}.get(mtf_align, "#8b9ab0")

        # Zone display
        zone_info = gi.get("zones", {})
        zone_pos = zone_info.get("position", None)
        zone_text = {"supply": "🔴 In Supply Zone", "demand": "🟢 In Demand Zone"}.get(zone_pos, "— No zone")
        zone_col = "#ef4444" if zone_pos == "supply" else ("#10b981" if zone_pos == "demand" else "#8b9ab0")

        # FVG, CHoCH, Killzone, RSI Div
        fvg = gi.get("fvg", {})
        choch = gi.get("choch", {})
        kz = gi.get("killzone", "Off-hours")
        rsi_div = gi.get("rsi_divergence", {})

        bo_col = "#10b981" if gi.get("breakout_aligned") else ("#f59e0b" if bo == "inside" else "#8b9ab0")
        bo_text = {"bull_breakout": "▲ BULL", "bear_breakout": "▼ BEAR",
                   "inside": "◈ Inside", "invalid": "—", "no_data": "—"}.get(bo, bo)
        _sw_lvl = f"{sw.get('sweep_level', 0):.2f}"
        sw_text = f"🏦 {sw['direction'].upper()} @ {_sw_lvl}" if sw.get("detected") else "—"
        b_col = "#10b981" if bonus > 0 else ("#ef4444" if bonus < 0 else "#8b9ab0")
        conf_col = "#10b981" if confirmations >= 4 else ("#84cc16" if confirmations >= 2 else "#f59e0b")
        contra_col = "#ef4444" if contradictions >= 2 else ("#f59e0b" if contradictions >= 1 else "#10b981")

        st.markdown(
            f"<div style='background:rgba(255,215,0,0.04);border:1px solid rgba(255,215,0,0.15);"
            f"border-radius:8px;padding:12px 14px;margin:8px 0;'>"
            # Title + Score
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;'>"
            f"<span style='font-size:10px;color:#ffd700;font-family:Space Mono,monospace;"
            f"letter-spacing:.1em;'>🥇 GOLD ENGINE V2</span>"
            f"<span style='font-size:12px;font-weight:700;color:{b_col};font-family:Space Mono,monospace;'>"
            f"{bonus:+d} pts | ✅{confirmations} ❌{contradictions}</span></div>"
            # Row 1: Multi-Timeframe
            f"<div style='background:rgba(255,255,255,0.03);border-radius:6px;padding:8px 10px;margin-bottom:8px;'>"
            f"<div style='font-size:9px;color:#8b9ab0;font-family:Space Mono,monospace;letter-spacing:.08em;margin-bottom:6px;'>MULTI-TIMEFRAME ANALYSIS</div>"
            f"<div style='display:flex;gap:12px;font-size:11px;'>"
            f"<div><span style='color:#8b9ab0;'>H4: </span><span style='color:{_tf_col(h4t_g)};font-weight:700;'>{_tf_icon(h4t_g)} {h4t_g.upper()}</span></div>"
            f"<div><span style='color:#8b9ab0;'>H1: </span><span style='color:{_tf_col(h1t_g)};font-weight:700;'>{_tf_icon(h1t_g)} {h1t_g.upper()}</span></div>"
            f"<div><span style='color:#8b9ab0;'>Entry: </span><span style='color:{_tf_col(et_g)};font-weight:700;'>{_tf_icon(et_g)} {et_g.upper()}</span></div>"
            f"<div><span style='color:#8b9ab0;'>Align: </span><span style='color:{mtf_col};font-weight:700;'>{mtf_align.upper()}</span></div>"
            f"</div></div>"
            # Row 2: Smart Money Modules
            f"<div style='display:flex;gap:10px;font-size:11px;flex-wrap:wrap;margin-bottom:6px;'>"
            f"<div><span style='color:#8b9ab0;'>Zone: </span><span style='color:{zone_col};'>{zone_text}</span></div>"
            f"<div><span style='color:#8b9ab0;'>FVG: </span><span style='color:{'#10b981' if fvg.get('detected') else '#8b9ab0'};'>{'✓ ' + str(fvg.get('type','')) if fvg.get('detected') else '—'}</span></div>"
            f"<div><span style='color:#8b9ab0;'>CHoCH: </span><span style='color:{'#10b981' if choch.get('detected') else '#8b9ab0'};'>{'✓ ' + str(choch.get('direction','')) if choch.get('detected') else '—'}</span></div>"
            f"<div><span style='color:#8b9ab0;'>Divergence: </span><span style='color:{'#10b981' if rsi_div.get('detected') else '#8b9ab0'};'>{'✓ ' + str(rsi_div.get('type','')) if rsi_div.get('detected') else '—'}</span></div>"
            f"</div>"
            # Row 3: Traditional modules
            f"<div style='display:flex;gap:10px;font-size:11px;flex-wrap:wrap;'>"
            f"<div><span style='color:#8b9ab0;'>Killzone: </span><span style='color:#e8edf2;'>{kz}</span></div>"
            f"<div><span style='color:#8b9ab0;'>Asian: </span>"
            f"<span style='color:#e8edf2;'>{(str(round(ar['low'],2)) + '—' + str(round(ar['high'],2))) if ar.get('valid') else 'N/A'}</span>"
            f" <span style='color:{bo_col};font-weight:700;'>{bo_text}</span></div>"
            f"<div><span style='color:#8b9ab0;'>Sweep: </span><span style='color:#e8edf2;'>{sw_text}</span></div>"
            f"</div></div>",
            unsafe_allow_html=True)

    # ── KPI cards — mobile-friendly 2-row grid ────────────────
    def kpi(lbl, val, col="#e8edf2"):
        return (f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.08);border-radius:8px;"
                f"padding:10px 12px;min-width:90px;flex:1;'>"
                f"<div style='font-size:9px;color:#8b9ab0;font-family:Space Mono,monospace;"
                f"letter-spacing:.08em;margin-bottom:4px;white-space:nowrap;overflow:hidden;'>{lbl}</div>"
                f"<div style='font-size:14px;font-weight:700;color:{col};font-family:Space Mono,monospace;"
                f"white-space:nowrap;'>{val}</div></div>")
    h4c = "#10b981" if "bull" in a["h4_trend"] else ("#ef4444" if "bear" in a["h4_trend"] else "#f59e0b")
    rc  = "#ef4444" if a["rsi"]>70 else ("#10b981" if a["rsi"]<30 else "#e8edf2")
    sess_col = "#10b981" if a["session_ok"] else "#6b7280"
    # Row 1: trend context
    st.markdown(
        f"<div style='display:flex;gap:6px;margin:10px 0 6px;'>"
        f"{kpi('H4 TREND', a['h4_trend'].upper(), h4c)}"
        f"{kpi('RSI14', fmt_num(a['rsi'],1), rc)}"
        f"{kpi('ATR', fmt_num(a['atr'],cfg_['dec']), '#8b9ab0')}"
        f"{kpi('SESSION', a['session'][:10], sess_col)}"
        f"</div>", unsafe_allow_html=True)
    # Row 2: Smart Entry + Trade levels
    se = a.get("smart_entry", {})
    se_price = se.get("entry_price", a["close"])
    se_type = se.get("entry_type", "MARKET")
    se_quality = se.get("quality", 2)
    se_stars = se.get("stars", "★★☆☆☆")
    se_reason = se.get("reason", "")
    # Safety: compare entry price against LIVE MT5 price (not cached close)
    _live_price = float(price)  # MT5 live price from line 2994-2995
    _entry_drift = abs(se_price - _live_price)
    _atr_val = float(a.get("atr", 1))
    if se_type == "MARKET":
        se_price = _live_price  # MARKET always = current live price
    elif se_type == "LIMIT" and _entry_drift > _atr_val * 3:
        se_type = "WAIT"  # LIMIT too far from live price → downgrade to WAIT
        se_reason = f"Price moved too far from entry level"
    elif se_type == "WAIT" and _entry_drift < _atr_val * 0.3:
        se_type = "MARKET"  # Price reached the WAIT level → upgrade to MARKET
        se_price = _live_price
    se_icon = "🟢" if se_type == "MARKET" else ("🟡" if se_type == "LIMIT" else "🔴")
    se_col = "#10b981" if se_type == "MARKET" else ("#f59e0b" if se_type == "LIMIT" else "#ef4444")
    st.markdown(
        f"<div style='display:flex;gap:6px;margin:0 0 4px;'>"
        f"{kpi(f'{se_icon} ENTRY ({se_type})', fmt_price(se_price,symbol), se_col)}"
        f"{kpi('SL', fmt_price(a['sl'],symbol), '#ef4444')}"
        f"{kpi('TP1', fmt_price(a['tp1'],symbol), '#10b981')}"
        f"{kpi('TP2', fmt_price(a['tp2'],symbol), '#84cc16')}"
        f"{kpi('R:R', fmt_num(a['rr'],1)+':1', '#a78bfa')}"
        f"</div>", unsafe_allow_html=True)
    # Entry quality bar
    _eq_col = "#10b981" if se_quality >= 4 else ("#f59e0b" if se_quality >= 3 else "#ef4444")
    st.markdown(
        f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.08);border-radius:6px;"
        f"padding:6px 12px;margin:0 0 6px;display:flex;justify-content:space-between;align-items:center;'>"
        f"<span style='font-size:10px;color:#8b9ab0;font-family:Space Mono,monospace;'>{se_reason}</span>"
        f"<span style='font-size:12px;color:{_eq_col};'>{se_stars}</span>"
        f"</div>", unsafe_allow_html=True)

    # Row 3: Risk/Reward in actual currency
    bal = st.session_state.get("balance", 1000.0)
    rpct = st.session_state.get("risk_pct", 1.0)
    risk_amt = bal * rpct / 100
    reward_tp1 = risk_amt * a["rr"] if a["rr"] > 0 else 0
    reward_tp2 = risk_amt * (a.get("tp2",0) - a["close"]) / a["sl_d"] if a["sl_d"] > 0 and a["direction"]=="Buy" else (risk_amt * (a["close"] - a.get("tp2",0)) / a["sl_d"] if a["sl_d"] > 0 else 0)
    rr2 = abs(reward_tp2 / risk_amt) if risk_amt > 0 else 0
    ccy = st.session_state.get("currency_label", "USD")
    st.markdown(
        f"<div style='display:flex;gap:6px;margin:0 0 10px;'>"
        f"{kpi('💰 RISK', f'{ccy} {risk_amt:,.0f}', '#ef4444')}"
        f"{kpi('🎯 TP1 REWARD', f'{ccy} {reward_tp1:,.0f}', '#10b981')}"
        f"{kpi('🎯 TP2 REWARD', f'{ccy} {abs(reward_tp2):,.0f}', '#84cc16')}"
        f"{kpi('📊 R:R (TP2)', f'{rr2:.1f}:1', '#a78bfa')}"
        f"</div>", unsafe_allow_html=True)

    # ── Chart — full width for mobile ─────────────────────────
    positions = fetch_mt5_positions(get_ma_token(), get_ma_account()) if (_is_owner() or get_ma_token()) else []
    sym_pos = [p for p in positions if norm(p.get("symbol","")).replace(".R","") == symbol]
    if sym_pos and _is_owner():
        st.markdown("<div style='font-size:11px;color:#00d4aa;font-family:Space Mono,monospace;margin-bottom:4px;'>📡 MT5 POSITIONS</div>", unsafe_allow_html=True)
        rows = []
        for p in sym_pos:
            rows.append({"Type": p.get("type","?").replace("POSITION_TYPE_",""),
                          "Vol": p.get("volume",0),
                          "Open": fmt_price(p.get("openPrice",0),symbol),
                          "Current": fmt_price(p.get("currentPrice",0),symbol),
                          "SL": fmt_price(p.get("stopLoss",0),symbol),
                          "TP": fmt_price(p.get("takeProfit",0),symbol),
                          "P&L": f"${p.get('profit',0):+.2f}"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    df_plot = a["df"].tail(150)
    trade_active = next((t for t in st.session_state.get("active_trades",[]) if t.get("symbol")==symbol), None)
    render_price_chart(
        df_plot, symbol,
        entry=trade_active["entry"] if trade_active else None,
        sl=trade_active["sl"] if trade_active else None,
        tp1=trade_active.get("tp1") if trade_active else a["tp1"],
        tp2=trade_active.get("tp2") if trade_active else a["tp2"],
        title=f"{symbol} {int_label}")

    # ── Below chart: 2-column layout (better on mobile) ───────
    col_l, col_r = st.columns([1, 1])

    with col_l:
        # Score breakdown (calculator backup)
        with st.expander("📊 Calculator Breakdown (Backup)", expanded=False):
            render_score_breakdown(a["bd"], a["score"], a["grade"])

        # ── Signal alert: Unified score Grade A/A+ ──────────────
        grok_rating = grok.get("ai_rating", 0) if grok and not grok.get("error") else 0
        _uni_s = a["score"]  # Use calculator score directly, AI is reference only
        _uni_s = max(0, min(100, _uni_s))
        _c_alert = cfg(symbol)
        _uni_triggered = _uni_s >= _c_alert.get("grade_a", 76)
        calc_triggered = a["grade"] in ("A+", "A")
        grok_triggered = _uni_triggered  # Use unified instead of raw AI rating
        alert_key    = f"_alerted_{symbol}_{a['grade']}_{a['direction']}_{a['score']}_{grok_rating}"
        ai_vfy_key   = f"_ai_vfy_{symbol}_{a['grade']}_{a['direction']}_{a['score']}"
        if (grok_triggered or calc_triggered) and not st.session_state.get(alert_key):
            # Run AI verification once per unique signal
            if ai_vfy_key not in st.session_state:
                with st.spinner("🤖 AI verifying signal…"):
                    st.session_state[ai_vfy_key] = verify_signal_with_ai(
                        symbol, a["grade"], a["direction"], a["score"], a)
            if st.session_state.get(ai_vfy_key):
                fire_signal_alert(symbol, a["grade"], a["direction"], a["score"])
                st.session_state[alert_key] = True
                # Log to signals DB
                log_signal_to_db(symbol, a["direction"], a["grade"], a["score"],
                                 True, a.get("session","?"), a.get("rsi",50), a.get("h4_trend","?"))
                _grok_label = f" | AI Rating: {grok_rating}/10" if grok_rating else ""
                st.markdown(
                    f"<div style='background:rgba(0,212,170,0.1);border:1px solid #00d4aa;"
                    f"border-left:3px solid #00d4aa;border-radius:6px;padding:8px 12px;margin:6px 0;"
                    f"font-size:12px;color:#00d4aa;font-family:Space Mono,monospace;animation:alertpulse 1.5s 3;'>"
                    f"🔔 SIGNAL — AI CONFIRMED ✅ — {a['direction']} {symbol} (Calc: {a['grade']} {a['score']}/100{_grok_label})"
                    f"</div>", unsafe_allow_html=True)
            else:
                st.session_state[alert_key] = True  # mark as handled, no alert
                # Log rejected signal to DB
                log_signal_to_db(symbol, a["direction"], a["grade"], a["score"],
                                 False, a.get("session","?"), a.get("rsi",50), a.get("h4_trend","?"))
                st.markdown(
                    f"<div style='background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);"
                    f"border-left:3px solid #f59e0b;border-radius:6px;padding:8px 12px;margin:6px 0;"
                    f"font-size:12px;color:#fcd34d;font-family:Space Mono,monospace;'>"
                    f"⚠ {a['grade']} SIGNAL — AI NOT CONFIRMED — {a['direction']} {symbol} ({a['score']}/100). Skip or verify manually."
                    f"</div>", unsafe_allow_html=True)

        # News — Trading Economics first, Grok fallback
        news_key = f"news_{symbol}"
        te_key   = get_te_key()
        nb1, nb2 = st.columns([2,1])
        if te_key:
            if nb1.button(f"📅 Load News (TE)", key=f"news_btn_{symbol}"):
                with st.spinner("Fetching economic calendar…"):
                    st.session_state[news_key] = get_te_news_for_symbol(symbol, te_key)
        else:
            if nb1.button(f"🗞 Load News (Grok)", key=f"news_btn_{symbol}"):
                with st.spinner("Getting Grok news…"):
                    st.session_state[news_key] = get_news_sentiment(symbol, get_xai_key())
        # Manual Grok fallback button if TE key exists
        if te_key:
            if nb2.button("🤖 Grok", key=f"grok_news_btn_{symbol}", help="Use Grok AI news instead"):
                with st.spinner("Asking Grok…"):
                    st.session_state[news_key] = get_news_sentiment(symbol, get_xai_key())

        news = st.session_state.get(news_key)
        if news:
            rc_    = {"HIGH":"#ef4444","MEDIUM":"#f59e0b","LOW":"#10b981"}.get(news["risk"],"#8b9ab0")
            adj_   = f"+{news['adj']}" if news["adj"]>0 else str(news["adj"])
            source = news.get("source","Grok")
            title  = "📅 TE CALENDAR" if source=="TE" else "🤖 GROK NEWS"
            st.markdown(
                f"<div class='panel'>"
                f"<div class='mono-title'>{title}</div>"
                f"<div style='display:flex;gap:12px;margin-bottom:6px;font-size:12px;'>"
                f"<span>Risk: <b style='color:{rc_};'>{news['risk']}</b></span>"
                f"<span>Adj: <b style='color:{rc_};'>{adj_}</b></span>"
                f"<span>Bias: <b>{news['bias'].upper()}</b></span></div>"
                f"<div style='font-size:12px;color:#e8edf2;margin-bottom:6px;'>{news['summary']}</div>"
                + "".join(f"<div style='font-size:11px;color:#8b9ab0;margin-bottom:2px;'>▸ {e}</div>" for e in news.get("events",[]))
                + "</div>", unsafe_allow_html=True)
            # Store for AI trade advisor context
            st.session_state[f"last_news_{symbol}"] = news

        # AI analysis button
        ai_key = f"ai_{symbol}_{interval}"
        if st.button(f"🤖 AI Analysis", key=f"ai_btn_{symbol}"):
            with st.spinner("Asking Grok..."):
                news_d = st.session_state.get(f"news_{symbol}")
                st.session_state[ai_key] = get_ai_analysis(
                    symbol, a["direction"], a["score"], a["grade"],
                    price, a["sl"], a["tp1"], a["tp2"],
                    a["atr"], a["rsi"], a["macd_hist"], a["session"],
                    news_d, a["df"].tail(10))
        if ai_key in st.session_state:
            st.markdown(f"<div class='ai-bubble'><div class='ai-header'>◈ GROK ANALYSIS</div>{st.session_state[ai_key]}</div>", unsafe_allow_html=True)

    with col_r:
        render_trade_tracker(symbol, price, a, td_key)

# ============================================================
# PAGE 3 — TRADE OVERVIEW & JOURNAL
# ============================================================
def page_trades():
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;letter-spacing:.12em;padding:4px 0 16px;'>◈ TRADE OVERVIEW & JOURNAL</div>", unsafe_allow_html=True)

    # ── Open trades ──────────────────────────────────────────
    trades = st.session_state.get("active_trades",[])
    st.markdown("<div class='mono-title' style='font-size:12px;'>OPEN TRADES</div>", unsafe_allow_html=True)
    if not trades:
        st.markdown("<div style='color:#4a5568;font-size:13px;padding:8px 0;'>No open trades. Enter trades from the symbol pages.</div>", unsafe_allow_html=True)
    else:
        rows = []
        for t in trades:
            sym = t.get("symbol","?")
            tick = fetch_mt5_price(sym, get_ma_token_price(), get_ma_account_price())
            live = tick["bid"] if tick else float(t["entry"])
            risk = abs(float(t["entry"])-float(t["sl"]))
            move = (live-float(t["entry"])) if t["direction"]=="Buy" else (float(t["entry"])-live)
            pnl_r = round(move/risk,2) if risk>0 else 0
            rows.append({
                "Symbol": sym, "Dir": t["direction"], "Entry": fmt_price(t["entry"],sym),
                "SL": fmt_price(t["sl"],sym), "TP1": fmt_price(t.get("tp1"),sym),
                "Lot": t.get("lot",0.01), "Grade": t.get("locked_grade","?"),
                "Live P&L (R)": f"{pnl_r:+.2f}",
                "Price": fmt_price(live,sym)+" (MT5)" if tick else fmt_price(live,sym)+" (TD)",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── MT5 live positions (owner only) ────────────────────────────────────
    st.markdown("---")
    positions = fetch_mt5_positions(get_ma_token(), get_ma_account()) if (_is_owner() or get_ma_token()) else []
    if positions and _is_owner():
        st.markdown("<div class='mono-title' style='font-size:12px;'>📡 MT5 LIVE POSITIONS</div>", unsafe_allow_html=True)
        pos_rows = []
        total_pnl = 0
        for p in positions:
            sym_p = p.get("symbol","?")
            profit = p.get("profit",0); total_pnl += profit
            pos_rows.append({
                "Symbol": sym_p, "Type": p.get("type","?").replace("POSITION_TYPE_",""),
                "Volume": p.get("volume",0), "Open": p.get("openPrice",0),
                "Current": p.get("currentPrice",0),
                "SL": p.get("stopLoss",0), "TP": p.get("takeProfit",0),
                "P&L ($)": f"${profit:+.2f}"})
        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
        pnl_c = "#10b981" if total_pnl>=0 else "#ef4444"
        st.markdown(f"<div style='font-family:Space Mono,monospace;font-size:14px;color:{pnl_c};padding:6px 0;'>Total P&L: ${total_pnl:+.2f}</div>", unsafe_allow_html=True)

    # ── Journal ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='mono-title' style='font-size:12px;'>TRADE JOURNAL</div>", unsafe_allow_html=True)
    journal = load_journal()
    stats   = journal_stats(journal)

    if stats:
        s1,s2,s3,s4,s5 = st.columns(5)
        s1.metric("Trades",   stats["total"])
        s2.metric("Win Rate",  f"{stats['wr']:.0f}%")
        s3.metric("Total R",   f"{stats['total_r']:+.2f}")
        s4.metric("Avg R",     f"{stats['avg_r']:+.2f}")
        s5.metric("Prof Factor",f"{stats['pf']:.2f}")

        # Equity curve
        if len(journal)>=2:
            cum_r = pd.Series([t.get("pnl_r",0) for t in journal]).cumsum()
            fig_eq = go.Figure(go.Scatter(y=cum_r.tolist(),mode="lines+markers",
                                          line=dict(color="#00d4aa",width=2),
                                          fill="tozeroy",fillcolor="rgba(0,212,170,0.06)"))
            fig_eq.update_layout(title="Equity Curve (R)",paper_bgcolor="#080c10",plot_bgcolor="#080c10",
                                  font=dict(color="#e8edf2"),height=200,margin=dict(l=0,r=0,t=30,b=0),
                                  xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                  yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig_eq, use_container_width=True)

        # By grade performance
        tab1, tab2, tab3 = st.tabs(["By Grade", "By Symbol", "By Session"])
        with tab1:
            grade_data = {}
            for t in journal:
                g = t.get("grade","?")
                grade_data.setdefault(g,[]).append(t.get("pnl_r",0))
            if grade_data:
                gd = pd.DataFrame([{"Grade":g,"Trades":len(v),"Win%":sum(1 for x in v if x>0)/len(v)*100,
                                     "Avg R":sum(v)/len(v)} for g,v in grade_data.items()])
                st.dataframe(gd, use_container_width=True, hide_index=True)
        with tab2:
            sym_data = {}
            for t in journal:
                s = t.get("symbol","?")
                sym_data.setdefault(s,[]).append(t.get("pnl_r",0))
            if sym_data:
                sd = pd.DataFrame([{"Symbol":s,"Trades":len(v),"Win%":sum(1 for x in v if x>0)/len(v)*100,
                                     "Total R":sum(v)} for s,v in sym_data.items()])
                st.dataframe(sd, use_container_width=True, hide_index=True)
        with tab3:
            sess_data = {}
            for t in journal:
                se = t.get("session","?")
                sess_data.setdefault(se,[]).append(t.get("pnl_r",0))
            if sess_data:
                sd2 = pd.DataFrame([{"Session":se,"Trades":len(v),"Avg R":sum(v)/len(v)} for se,v in sess_data.items()])
                st.dataframe(sd2, use_container_width=True, hide_index=True)

    # Full log table
    if journal:
        st.markdown("<div class='mono-title' style='font-size:11px;margin-top:12px;'>FULL LOG</div>", unsafe_allow_html=True)
        show_cols = ["id","ts","symbol","direction","entry","sl","exit","result","pnl_r","grade","session","notes"]
        df_j = pd.DataFrame(journal)[[c for c in show_cols if c in pd.DataFrame(journal).columns]]
        st.dataframe(df_j, use_container_width=True, hide_index=True)

        cc1, cc2 = st.columns([1,4])
        with cc1:
            csv = df_j.to_csv(index=False)
            st.download_button("⬇ Export CSV", csv, "journal.csv", "text/csv")
        with cc2:
            if st.button("🗑 Clear Journal"):
                if st.session_state.get("_confirm_clear"):
                    save_journal([]); st.session_state.pop("_confirm_clear",None)
                    st.success("Journal cleared!"); st.rerun()
                else:
                    st.session_state["_confirm_clear"] = True
                    st.warning("Click again to confirm clearing all journal data.")
    else:
        st.markdown("<div style='color:#4a5568;font-size:13px;'>No trades in journal yet.</div>", unsafe_allow_html=True)

# ============================================================
# PAGE 4 — BACKTEST
# ============================================================
def page_backtest():
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;letter-spacing:.12em;padding:4px 0 16px;'>◈ BACKTEST ENGINE</div>", unsafe_allow_html=True)

    td_key = get_td_key()
    if not td_key:
        st.warning("⚠ Add your Twelve Data API key in the sidebar.")
        return

    # ── Settings ─────────────────────────────────────────────
    st.markdown("<div class='mono-title'>BACKTEST SETTINGS</div>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    bt_sym  = b1.selectbox("Symbol",  ACTIVE_SYMBOLS, key="bt_sym")
    bt_int  = b2.selectbox("Interval", list(INTERVAL_OPTIONS.keys()), index=1, key="bt_int")
    # Calculate approximate bars needed for days
    _mins_map = {"5 Min":5,"15 Min":15,"30 Min":30,"1 Hour":60,"4 Hours":240}
    _bars_per_day = int(24*60 / _mins_map.get(bt_int, 15) * 5/7)  # trading days
    bt_days = b3.slider("Days", 7, 90, 30, key="bt_days")
    bt_bars = max(400, bt_days * _bars_per_day + 250)  # +250 for indicator warmup
    st.markdown(f"<div style='font-size:10px;color:#4a5568;font-family:Space Mono,monospace;margin:-8px 0 8px;'>"
                f"≈ {bt_bars} bars for {bt_days} days on {bt_int}</div>", unsafe_allow_html=True)

    b4, b5, b6 = st.columns(3)
    bt_balance  = b4.number_input("Balance", value=st.session_state.get("balance", 1000.0), min_value=100.0, key="bt_bal")
    bt_risk_pct = b5.number_input("Risk %", value=st.session_state.get("risk_pct", 1.0), min_value=0.1, max_value=10.0, step=0.1, key="bt_risk")
    bt_lot_mode = b6.selectbox("Lot Size", ["Auto (risk-based)", "Custom", "Fixed 0.01", "Fixed 0.1", "Fixed 1.0"], key="bt_lot_mode")

    bt_custom_lot = 0.01
    if bt_lot_mode == "Custom":
        bt_custom_lot = st.number_input("Custom Lot Size", value=0.05, min_value=0.01, max_value=100.0, step=0.01, format="%.2f", key="bt_custom_lot")

    b7, b8 = st.columns(2)
    bt_min_grade = b7.selectbox("Min Grade", ["A+ only", "A and above", "B and above"], index=1, key="bt_min_grade")
    run_bt = b8.button("▶ Run Backtest", key="btn_bt", type="primary")

    if not run_bt:
        return

    interval = INTERVAL_OPTIONS[bt_int]
    c_ = cfg(bt_sym)
    ccy = st.session_state.get("currency_label", "USD")

    with st.spinner("Running backtest..."):
        try:
            df_raw = add_indicators(fetch_bars(bt_sym, interval, bt_bars, td_key))
            df_h4  = add_indicators(fetch_bars(bt_sym, "4h", 300, td_key))
        except Exception as e:
            st.error(f"Error: {e}"); return

    # Grade filter
    if bt_min_grade == "A+ only":
        allowed_grades = {"A+"}
    elif bt_min_grade == "A and above":
        allowed_grades = {"A+", "A"}
    else:
        allowed_grades = {"A+", "A", "B"}

    trades_bt = []
    spike_trades = 0
    consecutive_losses = 0
    last_trade_bar = 0
    is_gold = norm(bt_sym) == "XAUUSD"
    COOLDOWN_BARS = 15 if is_gold else 8  # Gold needs more cooldown
    OVEREXT_THRESH = 2.0 if is_gold else 3.0  # Stricter for gold

    # ── Precompute H4 time index to prevent lookahead bias ────
    h4_times = None
    raw_times = None
    try:
        h4_times = pd.to_datetime(df_h4["time"], utc=True)
        raw_times = pd.to_datetime(df_raw["time"], utc=True)
    except Exception:
        pass  # Fallback: use full df_h4 (no time column)

    i = 200

    while i < len(df_raw)-1:
        row   = df_raw.iloc[i]
        df_sl = df_raw.iloc[:i+1]
        close = float(row["close"])
        atr   = float(row.get("atr14",0.001) or 0.001)

        # ── Cooldown: skip if too soon after last trade ───────
        if i - last_trade_bar < COOLDOWN_BARS and last_trade_bar > 0:
            i += 1; continue

        # ── Loss streak protection: pause after 3 consecutive losses ──
        if consecutive_losses >= 3:
            consecutive_losses = 0
            i += COOLDOWN_BARS; continue  # Skip more bars after loss streak

        # ── Slice H4 to prevent lookahead bias ────────────────
        df_h4_sync = df_h4
        if h4_times is not None and raw_times is not None:
            current_time = raw_times.iloc[i]
            h4_mask = h4_times <= current_time
            h4_cutoff = h4_mask.sum()
            if h4_cutoff >= 50:
                df_h4_sync = df_h4.iloc[:h4_cutoff]

        direction = determine_direction(df_sl, df_h4_sync, bt_sym)
        if direction == "Wait":
            i += 1; continue

        # ── Overextended filter ───────────────────────────────
        if _is_overextended(df_sl, direction, atr, threshold=OVEREXT_THRESH):
            i += 1; continue

        score, bd, grade, warns = score_signal(df_sl, df_h4_sync, bt_sym, direction)

        # ── Gold Engine overlay for XAUUSD ────────────────────
        if norm(bt_sym) == "XAUUSD":
            score, _gi, grade, _gw = gold_engine_score(
                df_sl, df_h4_sync, None, direction, score, grade)
            warns.extend(_gw)

        if grade not in allowed_grades:
            i += 1; continue
        if any("OPPOSES" in w for w in warns):
            i += 1; continue

        # ── Spike detection ───────────────────────────────────
        spike_info = detect_spike(df_sl, atr, bt_sym, lookback=5)
        # Skip trade if danger-level spike AGAINST our direction
        if spike_info["is_spike"] and spike_info["alert_level"] == "danger":
            spike_dir = spike_info["direction"]
            if (direction == "Buy" and spike_dir == "Bear") or \
               (direction == "Sell" and spike_dir == "Bull"):
                i += 1; continue

        # ── Levels: spike-adjusted if spike, swing-based otherwise ──
        if spike_info["is_spike"]:
            lvl = spike_adjusted_levels(close, direction, atr, bt_sym, spike_info, df=df_sl)
            spike_trades += 1
        else:
            lvl = compute_levels(close, direction, atr, bt_sym, df=df_sl)
        sl  = lvl["sl"]; tp1 = lvl["tp1"]; tp2 = lvl["tp2"]

        # Lot size calculation
        sl_pips = abs(close - sl) / c_.get("pip", 0.0001)
        if bt_lot_mode == "Auto (risk-based)":
            lot = compute_lot(bt_balance, bt_risk_pct, sl_pips, bt_sym)
        elif bt_lot_mode == "Custom":
            lot = bt_custom_lot
        elif bt_lot_mode == "Fixed 0.01":
            lot = 0.01
        elif bt_lot_mode == "Fixed 0.1":
            lot = 0.1
        else:
            lot = 1.0

        # Simulate forward (smarter trailing stop system)
        max_bars_forward = 80 if is_gold else 150  # Gold: faster timeout
        result = "timeout"; exit_price = close; exit_i = i
        trailing_sl = sl
        be_trigger_pct = 0.5  # Move to BE at 50% of TP1 (was 60%)
        trail_trigger_pct = 0.75  # Start trailing at 75% of TP1
        risk_dist = abs(close - sl)
        tp1_dist = abs(tp1 - close)

        be_level = close + tp1_dist * be_trigger_pct if direction == "Buy" else close - tp1_dist * be_trigger_pct
        trail_level = close + tp1_dist * trail_trigger_pct if direction == "Buy" else close - tp1_dist * trail_trigger_pct
        moved_to_be = False
        trailing_active = False
        best_price = close  # Track best price for trailing

        for j in range(i+1, min(i+max_bars_forward, len(df_raw))):
            future = df_raw.iloc[j]
            fh = float(future["high"]); fl = float(future["low"])

            # Track best price reached
            if direction == "Buy":
                best_price = max(best_price, fh)
            else:
                best_price = min(best_price, fl)

            # Stage 1: Move to breakeven at 50% of TP1
            if not moved_to_be:
                if (direction == "Buy" and fh >= be_level) or (direction == "Sell" and fl <= be_level):
                    trailing_sl = close + (atr * 0.1 if direction == "Buy" else -atr * 0.1)
                    moved_to_be = True

            # Stage 2: Active trailing at 75% of TP1 — trail by 0.7× ATR (wider to let trades run)
            if not trailing_active and moved_to_be:
                if (direction == "Buy" and fh >= trail_level) or (direction == "Sell" and fl <= trail_level):
                    trailing_active = True

            if trailing_active:
                if direction == "Buy":
                    new_trail = best_price - atr * 0.7
                    trailing_sl = max(trailing_sl, new_trail)
                else:
                    new_trail = best_price + atr * 0.7
                    trailing_sl = min(trailing_sl, new_trail)

            # Check SL hit — profitable trailing exits count as Win
            if direction == "Buy":
                if fl <= trailing_sl:
                    if not moved_to_be:
                        result = "Loss"
                    elif trailing_sl > close + atr * 0.05:
                        result = "Win"  # Profitable trailing stop = Win
                    else:
                        result = "BE"
                    exit_price = trailing_sl; exit_i = j; break
                if fh >= tp1:
                    result = "Win"; exit_price = tp1; exit_i = j; break
            else:
                if fh >= trailing_sl:
                    if not moved_to_be:
                        result = "Loss"
                    elif trailing_sl < close - atr * 0.05:
                        result = "Win"  # Profitable trailing stop = Win
                    else:
                        result = "BE"
                    exit_price = trailing_sl; exit_i = j; break
                if fl <= tp1:
                    result = "Win"; exit_price = tp1; exit_i = j; break

        if result == "timeout":
            exit_price = float(df_raw.iloc[min(i+max_bars_forward-1, len(df_raw)-1)]["close"])
            exit_i = min(i+max_bars_forward-1, len(df_raw)-1)

        risk = abs(close-sl)
        move = (exit_price-close) if direction=="Buy" else (close-exit_price)
        pnl_r = move/risk if risk>0 else 0
        pnl_usd = pnl_r * (bt_balance * bt_risk_pct / 100)
        bars_held = exit_i - i

        if result == "Loss":
            consecutive_losses += 1
        elif result == "Win":
            consecutive_losses = 0

        last_trade_bar = exit_i
        trade_date = str(df_raw.iloc[i]["time"])[:16]
        is_spike_trade = spike_info["is_spike"]

        trades_bt.append({
            "Date": trade_date, "Dir": direction, "Grade": grade, "Score": score,
            "Entry": round(close, c_["dec"]), "SL": round(sl, c_["dec"]),
            "TP1": round(tp1, c_["dec"]), "Lot": lot,
            "Result": result, "PnL_R": round(pnl_r, 2),
            "PnL_$": round(pnl_usd, 2), "Bars": bars_held,
            "RSI": round(float(row.get("rsi14", 50) or 50), 1),
            "H4": _h4_trend(df_h4),
            "Spike": "⚡" if is_spike_trade else "",
        })
        i = exit_i + 1

    if not trades_bt:
        st.info("No qualifying trades found in this period."); return

    df_bt  = pd.DataFrame(trades_bt)
    wins   = len(df_bt[df_bt["Result"]=="Win"])
    losses = len(df_bt[df_bt["Result"]=="Loss"])
    bes    = len(df_bt[df_bt["Result"]=="BE"])
    timeouts = len(df_bt[df_bt["Result"]=="timeout"])
    total  = len(df_bt)
    decided = wins + losses  # exclude BE and timeout for true win rate
    wr     = wins/decided*100 if decided else 0
    total_r= df_bt["PnL_R"].sum()
    total_usd = df_bt["PnL_$"].sum()
    avg_r  = df_bt["PnL_R"].mean()
    gp     = df_bt[df_bt["PnL_R"]>0]["PnL_R"].sum()
    gl     = abs(df_bt[df_bt["PnL_R"]<0]["PnL_R"].sum())
    pf     = gp/gl if gl>0 else 0
    cum_r  = df_bt["PnL_R"].cumsum()
    max_dd = (cum_r.cummax() - cum_r).max()
    # Win/loss streaks
    streak_w = 0; streak_l = 0; max_w = 0; max_l = 0
    for r in df_bt["Result"]:
        if r == "Win":
            streak_w += 1; streak_l = 0; max_w = max(max_w, streak_w)
        elif r == "Loss":
            streak_l += 1; streak_w = 0; max_l = max(max_l, streak_l)
        else:
            streak_w = 0; streak_l = 0

    # ── Stats Dashboard ──────────────────────────────────────
    st.markdown("<div class='mono-title' style='margin-top:16px;'>BACKTEST RESULTS</div>", unsafe_allow_html=True)

    def bt_stat(lbl, val, col="#e8edf2"):
        return (f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.08);"
                f"border-radius:8px;padding:10px;flex:1;min-width:80px;text-align:center;'>"
                f"<div style='font-size:9px;color:#8b9ab0;font-family:Space Mono,monospace;"
                f"letter-spacing:.06em;margin-bottom:4px;'>{lbl}</div>"
                f"<div style='font-size:16px;font-weight:700;color:{col};font-family:Space Mono,monospace;'>{val}</div></div>")

    st.markdown(
        f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;'>"
        f"{bt_stat('TRADES', total)}"
        f"{bt_stat('WIN RATE', f'{wr:.0f}%', '#10b981' if wr>=50 else '#ef4444')}"
        f"{bt_stat('TOTAL R', f'{total_r:+.1f}R', '#10b981' if total_r>0 else '#ef4444')}"
        f"{bt_stat(f'P&L ({ccy})', f'{total_usd:+,.0f}', '#10b981' if total_usd>0 else '#ef4444')}"
        f"{bt_stat('PROFIT F', f'{pf:.2f}', '#10b981' if pf>1 else '#ef4444')}"
        f"{bt_stat('MAX DD', f'{max_dd:.1f}R', '#ef4444')}"
        f"</div>", unsafe_allow_html=True)
    avg_bars_val = f"{df_bt['Bars'].mean():.0f}"
    st.markdown(
        f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;'>"
        f"{bt_stat('AVG R', f'{avg_r:+.2f}', '#10b981' if avg_r>0 else '#ef4444')}"
        f"{bt_stat('WINS', wins, '#10b981')}"
        f"{bt_stat('LOSSES', losses, '#ef4444')}"
        f"{bt_stat('BE', bes, '#f59e0b')}"
        f"{bt_stat('WIN STREAK', max_w, '#10b981')}"
        f"{bt_stat('LOSS STREAK', max_l, '#ef4444')}"
        f"{bt_stat('AVG BARS', avg_bars_val)}"
        f"</div>", unsafe_allow_html=True)

    # ── Equity Curve ─────────────────────────────────────────
    cum_usd = df_bt["PnL_$"].cumsum()
    fig_eq = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.7, 0.3], vertical_spacing=0.05,
                            subplot_titles=["Equity Curve", "Drawdown"])
    fig_eq.add_trace(go.Scatter(x=df_bt["Date"], y=cum_r, mode="lines+markers",
                                 line=dict(color="#00d4aa", width=2),
                                 fill="tozeroy", fillcolor="rgba(0,212,170,0.06)",
                                 name="Cumulative R"), row=1, col=1)
    # Drawdown
    dd_series = cum_r - cum_r.cummax()
    fig_eq.add_trace(go.Scatter(x=df_bt["Date"], y=dd_series, mode="lines",
                                 fill="tozeroy", fillcolor="rgba(239,68,68,0.15)",
                                 line=dict(color="#ef4444", width=1.5),
                                 name="Drawdown"), row=2, col=1)
    fig_eq.update_layout(paper_bgcolor="#080c10", plot_bgcolor="#080c10",
                          font=dict(color="#e8edf2"), height=400,
                          margin=dict(l=0,r=0,t=30,b=0), showlegend=True,
                          legend=dict(orientation="h", y=1.02, bgcolor="rgba(0,0,0,0)"))
    for ax in ["xaxis","yaxis","xaxis2","yaxis2"]:
        fig_eq.update_layout(**{ax: dict(gridcolor="rgba(255,255,255,0.05)")})
    st.plotly_chart(fig_eq, use_container_width=True)

    # ── Trade Table ──────────────────────────────────────────
    st.markdown("<div class='mono-title'>TRADE LOG</div>", unsafe_allow_html=True)
    show_cols = ["Date","Dir","Grade","Score","Entry","SL","TP1","Lot","Result","PnL_R","PnL_$","Bars","RSI","H4","Spike"]
    st.dataframe(df_bt[show_cols], use_container_width=True, hide_index=True)

    # ── Breakdowns ───────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["By Grade", "By Direction", "By Session (RSI)"])
    with tab1:
        gd2 = df_bt.groupby("Grade").agg(
            Trades=("PnL_R","count"),
            Win_Rate=("Result", lambda x:(x=="Win").mean()*100),
            Avg_R=("PnL_R","mean"),
            Total_R=("PnL_R","sum"),
            Total_USD=("PnL_$","sum")
        ).round(2).reset_index()
        st.dataframe(gd2, use_container_width=True, hide_index=True)
    with tab2:
        dd2 = df_bt.groupby("Dir").agg(
            Trades=("PnL_R","count"),
            Win_Rate=("Result", lambda x:(x=="Win").mean()*100),
            Avg_R=("PnL_R","mean"),
            Total_R=("PnL_R","sum")
        ).round(2).reset_index()
        st.dataframe(dd2, use_container_width=True, hide_index=True)
    with tab3:
        # RSI distribution analysis
        df_bt["RSI_Zone"] = pd.cut(df_bt["RSI"], bins=[0,30,40,60,70,100],
                                    labels=["<30 OS","30-40","40-60","60-70",">70 OB"])
        rsi2 = df_bt.groupby("RSI_Zone", observed=True).agg(
            Trades=("PnL_R","count"),
            Win_Rate=("Result", lambda x:(x=="Win").mean()*100),
            Avg_R=("PnL_R","mean")
        ).round(2).reset_index()
        st.dataframe(rsi2, use_container_width=True, hide_index=True)

    # ── Grok AI Backtest Analysis ────────────────────────────
    st.markdown("---")
    if st.button("🤖 AI Backtest Analysis (Grok)", key="btn_bt_ai"):
        key = get_xai_key()
        if not key:
            st.error("No xAI key.")
        else:
            bt_summary = (
                f"BACKTEST RESULTS — {bt_sym} {bt_int} ({bt_bars} bars)\n"
                f"Total trades: {total} | Win rate: {wr:.1f}% | Avg R: {avg_r:+.2f} | Total R: {total_r:+.2f}\n"
                f"Profit Factor: {pf:.2f} | Max Drawdown: {max_dd:.1f}R\n"
                f"Max Win Streak: {max_w} | Max Loss Streak: {max_l}\n"
                f"Asset class: {c_.get('asset_class','forex')}\n\n"
                f"BY GRADE:\n{gd2.to_string(index=False)}\n\n"
                f"BY DIRECTION:\n{dd2.to_string(index=False)}\n\n"
                f"Analyze this backtest:\n"
                f"1. Is this strategy profitable? Is the edge statistically significant?\n"
                f"2. What's the biggest weakness?\n"
                f"3. Should I trade this symbol/timeframe with real money?\n"
                f"4. Specific parameter adjustments to improve results?\n"
                f"5. Compare to my live trading performance if data is available.\n"
                f"Be brutally honest."
            )
            with st.spinner("Grok analyzing backtest…"):
                bt_ai = _grok([
                    {"role":"system","content":"You are a quantitative trading analyst reviewing backtest results. Be data-driven and honest."},
                    {"role":"user","content":bt_summary}
                ], max_tokens=600, temperature=0.3, api_key=key) or "No response."
            st.session_state["bt_ai_analysis"] = bt_ai

    if st.session_state.get("bt_ai_analysis"):
        st.markdown(
            f"<div class='ai-bubble'>"
            f"<div style='font-size:10px;color:#6366f1;font-family:Space Mono,monospace;"
            f"letter-spacing:.08em;margin-bottom:8px;'>🤖 GROK BACKTEST ANALYSIS</div>"
            + st.session_state["bt_ai_analysis"].replace("\n","<br>") +
            f"</div>", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================
# ============================================================
# PAGE — PERFORMANCE & AI HABIT ANALYSIS
# ============================================================
def page_performance():
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;"
                "letter-spacing:.12em;padding:4px 0 16px;'>◈ PERFORMANCE & AI ANALYSIS</div>",
                unsafe_allow_html=True)

    if not _sb_ok():
        st.warning("Supabase not connected. Add SUPABASE_URL and SUPABASE_KEY to your secrets.")
        return

    # ── Import MT5 History via MetaApi (owner only) ────────────
    if _is_owner() or get_ma_token():
      with st.expander("📥 Import MT5 History (one-time setup)"):
        st.markdown("<div style='font-size:12px;color:#8b9ab0;margin-bottom:8px;'>"
                    "Click the button below to import your complete MT5 trade history "
                    "directly from MetaApi. This only needs to be done once.</div>",
                    unsafe_allow_html=True)
        days_back = st.number_input("Import how many days back?", min_value=7, max_value=365, value=30, key="imp_days")
        if st.button("📥 Import from MetaApi", key="btn_import_ma"):
            ma_tok = get_ma_token(); ma_acc = get_ma_account()
            if not ma_tok or not ma_acc:
                st.error("MetaApi not connected. Add token and account ID first.")
            else:
                with st.spinner(f"Fetching {days_back} days of MT5 history…"):
                    deals = fetch_mt5_history_deals(ma_tok, ma_acc, since_hours=days_back*24)
                if not deals:
                    st.warning("No deals found. Check MetaApi connection.")
                else:
                    # Group deals by positionId to match IN/OUT pairs
                    positions = {}
                    for d in deals:
                        pid = str(d.get("positionId",""))
                        if not pid: continue
                        entry_type = d.get("entryType","")
                        if pid not in positions: positions[pid] = {}
                        if "IN" in entry_type: positions[pid]["in"] = d
                        elif "OUT" in entry_type: positions[pid]["out"] = d

                    # Check existing tickets to avoid duplicates
                    existing = sb_get("journal")
                    existing_tickets = {j.get("mt5_ticket","") for j in existing}

                    imported = 0; skipped = 0
                    for pid, pair in positions.items():
                        if "in" not in pair or "out" not in pair:
                            skipped += 1; continue
                        if f"hist_{pid}" in existing_tickets:
                            skipped += 1; continue  # already imported
                        din  = pair["in"]; dout = pair["out"]
                        sym  = norm(din.get("symbol","")).replace(".R","").replace(".r","")
                        dir_ = "Buy" if "BUY" in din.get("type","").upper() else "Sell"
                        entry_p = float(din.get("price",0))
                        exit_p  = float(dout.get("price",0))
                        profit  = float(dout.get("profit",0))
                        lot     = float(din.get("volume",0.01))
                        sl_val  = float(din.get("stopLoss",0) or 0)
                        tp_val  = float(din.get("takeProfit",0) or 0)
                        # Calculate R
                        risk = abs(entry_p - sl_val) if sl_val else 1
                        move = (exit_p - entry_p) if dir_=="Buy" else (entry_p - exit_p)
                        pnl_r = round(move/risk, 2) if risk > 0 else 0
                        outcome = "WIN" if profit > 0 else ("LOSS" if profit < 0 else "BREAKEVEN")
                        sb_insert("journal", {
                            "mt5_ticket": f"hist_{pid}",
                            "symbol": sym, "direction": dir_,
                            "entry": entry_p, "exit_price": exit_p,
                            "sl": sl_val, "tp1": tp_val, "lot": lot,
                            "pnl_r": pnl_r, "pnl_usd": profit,
                            "outcome": outcome, "grade": "HISTORY",
                            "score": 0,
                            "opened_at": din.get("time",""),
                            "notes": f"MetaApi import"
                        })
                        imported += 1
                    st.success(f"✅ Imported {imported} trades. Skipped {skipped}.")
                    if imported > 0: st.rerun()

    journal = sb_get("journal", "order=closed_at.desc")
    signals = sb_get("signals", "order=recorded_at.desc&limit=200")

    # ── Stats cards ──────────────────────────────────────────
    if not journal:
        st.info("No closed trades yet. Once MT5 positions close, they'll appear here automatically.")
    else:
        df = pd.DataFrame(journal)
        df["pnl_r"] = pd.to_numeric(df["pnl_r"], errors="coerce").fillna(0)
        total  = len(df)
        wins   = len(df[df["outcome"]=="WIN"])
        losses = len(df[df["outcome"]=="LOSS"])
        wr     = round(wins/total*100, 1) if total else 0
        avg_r  = round(df["pnl_r"].mean(), 2)
        total_r= round(df["pnl_r"].sum(), 2)
        best   = df.loc[df["pnl_r"].idxmax()] if total else None
        worst  = df.loc[df["pnl_r"].idxmin()] if total else None

        def stat(lbl, val, col):
            return (f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.08);"
                    f"border-radius:8px;padding:14px;flex:1;min-width:100px;text-align:center;'>"
                    f"<div style='font-size:9px;color:#8b9ab0;font-family:Space Mono,monospace;"
                    f"letter-spacing:.08em;margin-bottom:6px;'>{lbl}</div>"
                    f"<div style='font-size:22px;font-weight:700;color:{col};font-family:Space Mono,monospace;'>{val}</div></div>")

        st.markdown(
            f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;'>"
            f"{stat('TOTAL TRADES', total, '#e8edf2')}"
            f"{stat('WIN RATE', f'{wr}%', '#10b981' if wr>=50 else '#ef4444')}"
            f"{stat('AVG R', f'{avg_r:+.2f}R', '#10b981' if avg_r>0 else '#ef4444')}"
            f"{stat('TOTAL R', f'{total_r:+.2f}R', '#10b981' if total_r>0 else '#ef4444')}"
            f"{stat('WINS', wins, '#10b981')}"
            f"{stat('LOSSES', losses, '#ef4444')}"
            f"</div>", unsafe_allow_html=True)

        # By symbol breakdown
        st.markdown("<div class='mono-title'>BY SYMBOL</div>", unsafe_allow_html=True)
        sym_stats = df.groupby("symbol").agg(
            Trades=("pnl_r","count"),
            WinRate=("outcome", lambda x: round((x=="WIN").sum()/len(x)*100,1)),
            AvgR=("pnl_r","mean"),
            TotalR=("pnl_r","sum")
        ).round(2).reset_index()
        st.dataframe(sym_stats, use_container_width=True, hide_index=True)

        # Recent trades table
        st.markdown("<div class='mono-title' style='margin-top:12px;'>RECENT TRADES</div>", unsafe_allow_html=True)
        cols = ["symbol","direction","entry","exit_price","pnl_r","pnl_usd","outcome","grade","closed_at"]
        show_cols = [c for c in cols if c in df.columns]
        st.dataframe(df[show_cols].head(20), use_container_width=True, hide_index=True)

        # ── AI Habit Analysis ─────────────────────────────────
        st.markdown("---")
        st.markdown("<div class='mono-title'>🤖 AI HABIT ANALYSIS</div>", unsafe_allow_html=True)

        if st.button("🤖 Analyze My Trading Habits (Grok)", key="btn_habit"):
            key = get_xai_key()
            if not key:
                st.error("No xAI key configured.")
            else:
                # Build summary for Grok
                by_sym  = sym_stats.to_string(index=False)
                by_dir  = df.groupby("direction")["pnl_r"].agg(["count","mean","sum"]).round(2).to_string()
                by_out  = df["outcome"].value_counts().to_string()
                top3_w  = df[df["outcome"]=="WIN"].nlargest(3,"pnl_r")[["symbol","direction","pnl_r","grade"]].to_string(index=False)
                top3_l  = df[df["outcome"]=="LOSS"].nsmallest(3,"pnl_r")[["symbol","direction","pnl_r","grade"]].to_string(index=False)
                msg = (
                    f"FOREX TRADER PERFORMANCE REVIEW\n"
                    f"Total trades: {total} | Win rate: {wr}% | Avg R: {avg_r} | Total R: {total_r}\n\n"
                    f"BY SYMBOL:\n{by_sym}\n\n"
                    f"BY DIRECTION:\n{by_dir}\n\n"
                    f"OUTCOMES:\n{by_out}\n\n"
                    f"TOP 3 WINS:\n{top3_w}\n\n"
                    f"TOP 3 LOSSES:\n{top3_l}\n\n"
                    f"Please analyze this trader's habits and provide:\n"
                    f"1. STRENGTHS: What they're doing well\n"
                    f"2. WEAKNESSES: Patterns in their losses\n"
                    f"3. BEST SETUP: Which symbol/direction/session works best for them\n"
                    f"4. ADVICE: 3 specific actionable improvements\n"
                    f"Be direct and specific. Use the data to back up every point."
                )
                with st.spinner("Grok is analyzing your trading habits…"):
                    analysis = _grok([
                        {"role":"system","content":"You are an elite forex trading coach analyzing a student's real trade history. UTC: "+pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M")},
                        {"role":"user","content":msg}
                    ], max_tokens=600, temperature=0.3, api_key=key) or "No response."
                st.session_state["habit_analysis"] = analysis

        if st.session_state.get("habit_analysis"):
            st.markdown(
                f"<div class='ai-bubble'>"
                f"<div style='font-size:10px;color:#6366f1;font-family:Space Mono,monospace;"
                f"letter-spacing:.08em;margin-bottom:8px;'>🤖 GROK HABIT ANALYSIS</div>"
                + st.session_state["habit_analysis"].replace("\n","<br>") +
                f"</div>", unsafe_allow_html=True)

    # ── Signal history ────────────────────────────────────────
    if signals:
        st.markdown("---")
        st.markdown("<div class='mono-title'>SIGNAL HISTORY</div>", unsafe_allow_html=True)
        df_s = pd.DataFrame(signals)
        if "ai_confirmed" in df_s.columns:
            confirmed = df_s["ai_confirmed"].sum()
            total_s   = len(df_s)
            st.markdown(
                f"<div style='font-size:12px;color:#8b9ab0;margin-bottom:8px;'>"
                f"Last {total_s} signals · AI confirmed: <b style='color:#10b981;'>{confirmed}</b> · "
                f"Rejected: <b style='color:#ef4444;'>{total_s-confirmed}</b></div>",
                unsafe_allow_html=True)
        show_s = [c for c in ["symbol","direction","grade","score","ai_confirmed","session","rsi","recorded_at"] if c in df_s.columns]
        st.dataframe(df_s[show_s].head(50), use_container_width=True, hide_index=True)

# ============================================================
# PAGE — WEEKEND PRE-MARKET ANALYSIS
# ============================================================
def page_weekend():
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;"
                "letter-spacing:.12em;padding:4px 0 16px;'>◈ WEEKEND PRE-MARKET ANALYSIS</div>",
                unsafe_allow_html=True)

    st.markdown("<div style='font-size:12px;color:#8b9ab0;margin-bottom:16px;'>"
                "Analyze upcoming economic events and weekend news to prepare for Monday's open.</div>",
                unsafe_allow_html=True)

    # Fetch economic calendar for all symbols
    te_key = get_te_key()

    if st.button("🔮 Generate Pre-Market Analysis (Grok)", key="btn_premarket"):
        key = get_xai_key()
        if not key:
            st.error("No xAI key configured.")
            return

        # Gather economic calendar data if available
        cal_text = ""
        if te_key:
            events = fetch_te_calendar(te_key)
            if events:
                ev_lines = []
                for e in events[:20]:
                    imp_icon = "HIGH" if e["importance"]=="HIGH" else e["importance"]
                    ev_lines.append(f"  {e['date'].strftime('%a %d %H:%M UTC')} [{e['country'].title()}] "
                                    f"[{imp_icon}] {e['event']}")
                cal_text = "\n".join(ev_lines)

        # Build prompt for Grok
        now_utc = pd.Timestamp.utcnow()
        symbols_list = ", ".join(ACTIVE_SYMBOLS)

        msg = (
            f"WEEKEND PRE-MARKET ANALYSIS — Prepare for Monday's open\n"
            f"Current time: {now_utc.strftime('%Y-%m-%d %H:%M UTC')} ({now_utc.strftime('%A')})\n"
            f"Symbols I trade: {symbols_list}\n\n"
        )
        if cal_text:
            msg += f"UPCOMING ECONOMIC CALENDAR (next 3 days):\n{cal_text}\n\n"

        # Add historical context if available
        hist_summary = ""
        if _sb_ok():
            journal = sb_get("journal", "order=closed_at.desc&limit=50")
            if journal:
                df_j = pd.DataFrame(journal)
                df_j["pnl_r"] = pd.to_numeric(df_j["pnl_r"], errors="coerce").fillna(0)
                by_sym = df_j.groupby("symbol").agg(
                    trades=("pnl_r","count"),
                    wr=("outcome", lambda x: f"{(x=='WIN').sum()}/{len(x)}"),
                    avg_r=("pnl_r","mean")
                ).round(2)
                hist_summary = f"\nMY RECENT PERFORMANCE (last 50 trades):\n{by_sym.to_string()}\n"

        msg += hist_summary
        msg += (
            f"\nPlease provide:\n"
            f"1. MARKET OUTLOOK: Key themes driving markets this week (USD strength/weakness, "
            f"risk sentiment, central bank expectations)\n"
            f"2. HIGH-IMPACT EVENTS: Which economic events to watch and their expected impact "
            f"on my symbols (with exact event times)\n"
            f"3. SYMBOL-BY-SYMBOL BIAS: For each of my symbols, give a BULLISH/BEARISH/NEUTRAL "
            f"bias with 1-sentence reasoning\n"
            f"4. TRADE PLAN: Top 3 symbols + directions to watch for. Explain the setup "
            f"and catalyst — do NOT include specific price levels (our system calculates "
            f"Entry/SL/TP automatically from live data)\n"
            f"5. RISK WARNINGS: Any major risks or events that could cause unexpected moves\n"
            f"6. PERSONAL ADVICE: Based on my recent performance data, which symbols and "
            f"directions should I focus on or avoid?\n\n"
            f"IMPORTANT: Do NOT provide specific price numbers for entry, SL, TP, or support/resistance. "
            f"You do not have access to live prices and your price data is outdated. "
            f"Focus on DIRECTION, EVENTS, TIMING, and RISK only. Our system handles price levels."
        )

        with st.spinner("🔮 Grok is analyzing weekend news and upcoming events…"):
            analysis = _grok([
                {"role":"system","content":
                 "You are an elite forex market analyst preparing a weekly pre-market brief. "
                 "Use the trader's personal performance data to give personalised recommendations. "
                 "CRITICAL: Never output specific price levels (entry, SL, TP, support, resistance) — "
                 "you do not have live price access and your data is outdated. "
                 "Focus on direction, events, timing, catalysts, and risk. "
                 f"UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}"},
                {"role":"user","content":msg}
            ], max_tokens=1200, temperature=0.3, api_key=key) or "No response."
        st.session_state["premarket_analysis"] = analysis

    if st.session_state.get("premarket_analysis"):
        st.markdown(
            f"<div class='ai-bubble'>"
            f"<div style='font-size:10px;color:#6366f1;font-family:Space Mono,monospace;"
            f"letter-spacing:.08em;margin-bottom:8px;'>🔮 GROK PRE-MARKET BRIEF</div>"
            + st.session_state["premarket_analysis"].replace("\n","<br>") +
            f"</div>", unsafe_allow_html=True)

    # Economic calendar display
    if te_key:
        st.markdown("---")
        st.markdown("<div class='mono-title'>📅 UPCOMING ECONOMIC CALENDAR</div>", unsafe_allow_html=True)
        events = fetch_te_calendar(te_key)
        if events:
            ev_rows = []
            for e in events[:30]:
                imp_icon = "🔴" if e["importance"]=="HIGH" else ("🟡" if e["importance"]=="MEDIUM" else "⚪")
                ev_rows.append({
                    "Time": e["date"].strftime("%a %d %H:%M"),
                    "Impact": imp_icon + " " + e["importance"],
                    "Country": e["country"].title(),
                    "Event": e["event"],
                    "Forecast": str(e.get("forecast","")) if e.get("forecast") else "—",
                    "Previous": str(e.get("previous","")) if e.get("previous") else "—",
                })
            st.dataframe(pd.DataFrame(ev_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming events found.")
    else:
        st.info("Add Trading Economics API key in sidebar to see economic calendar.")

def render_sidebar():
    with st.sidebar:
        st.markdown("<div style='font-family:Space Mono,monospace;font-size:12px;color:#00d4aa;letter-spacing:.1em;padding:8px 0;'>ALPHA EDGE AI<br><span style='color:#4a5568;'>V14.0 — Multi-User</span></div>", unsafe_allow_html=True)

        # ── User Profile (if authenticated) ──
        if _AUTH_AVAILABLE and is_logged_in():
            _email = get_current_email()
            _short = _email.split("@")[0] if _email else "User"
            st.markdown(f"<div style='font-size:11px;color:#8b9ab0;font-family:Space Mono,monospace;padding:4px 0;'>👤 {_short}</div>", unsafe_allow_html=True)
            if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
                tok = st.session_state.get("auth_access_token", "")
                if tok:
                    sign_out(tok)
                clear_session()
                st.rerun()
            st.markdown("---")

        # ── Navigation ──
        page_options = ["🏠  Overview","🔮  Pre-Market"] + [f"💱  {s}" for s in ACTIVE_SYMBOLS] + ["📊  Trades & Journal","📈  Performance","🔬  Backtest"]
        page = st.radio("", page_options, key="page_sel", label_visibility="collapsed")

        st.markdown("---")

        # ── Auto-refresh ──
        if st_autorefresh:
            ref_int = st.selectbox("Auto-refresh (s)", [0,15,30,60,120],
                                   format_func=lambda x:"Off" if x==0 else f"{x}s",
                                   index=0, key="ref_int")
            if ref_int > 0:
                st_autorefresh(interval=ref_int*1000, key="autoref")
            st.markdown(f"<div style='font-size:10px;color:#4a5568;font-family:Space Mono,monospace;'>"
                        f"Price: live · Analysis: 5min cache</div>", unsafe_allow_html=True)

        # ── Overview interval ──
        ov_int_label = st.selectbox("Overview Interval", list(INTERVAL_OPTIONS.keys()), index=1, key="ov_int_sel")
        st.session_state["ov_interval"] = INTERVAL_OPTIONS[ov_int_label]

        st.markdown("---")
        # API Keys — OWNER ONLY (other users use platform keys from env)
        if _is_owner():
            st.markdown("<div style='font-size:11px;color:#8b9ab0;font-family:Space Mono,monospace;margin-bottom:4px;'>API KEYS</div>", unsafe_allow_html=True)

            # Twelve Data
            _td = st.text_input("Twelve Data", value=st.session_state.get("td_key",_ENV_TD),
                                type="password", key="td_inp", placeholder="paste key…")
            if _td: st.session_state["td_key"] = _td

            # xAI Grok
            _xai = st.text_input("xAI Grok", value=st.session_state.get("xai_key",_ENV_XAI),
                                 type="password", key="xai_inp", placeholder="paste key…")
            if _xai: st.session_state["xai_key"] = _xai

            _gm = st.selectbox("Grok Model", _GROK_MODELS, index=0, key="grok_model_sel")

            # Trading Economics
            _te = st.text_input("Trading Economics", value=st.session_state.get("te_key",_ENV_TE),
                                type="password", key="te_inp", placeholder="paste TE key…")
            if _te: st.session_state["te_key"] = _te

            td_ok  = "✅" if get_td_key()  else "❌"
            xai_ok = "✅" if get_xai_key() else "❌"
            te_ok  = "✅" if get_te_key()  else "❌"
            st.markdown(f"<div style='font-size:11px;color:#4a5568;font-family:Space Mono,monospace;'>{td_ok} TD &nbsp; {xai_ok} xAI ({_gm[:14]}) &nbsp; {te_ok} TE</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<div style='font-size:11px;color:#00d4aa;font-family:Space Mono,monospace;margin-bottom:4px;'>MT5 LIVE (MetaApi)</div>", unsafe_allow_html=True)

        # MT5 live prices powered by platform — show status to all users
        _price_connected = bool(get_ma_token_price() and get_ma_account_price())
        st.markdown(f"<div style='font-size:11px;color:#4a5568;font-family:Space Mono,monospace;'>{'✅' if _price_connected else '❌'} Live MT5 Prices</div>", unsafe_allow_html=True)

        # MT5 credentials management — OWNER ONLY
        if _is_owner():
            _ma_tok = st.text_input("MetaApi Token", value=st.session_state.get("ma_token",""),
                                    type="password", key="ma_tok_inp")
            _ma_acc = st.text_input("Account ID", value=st.session_state.get("ma_account",""), key="ma_acc_inp")
            _ma_sfx = st.text_input("Symbol suffix", value=st.session_state.get("ma_sym_suffix",""),
                                    key="ma_sfx_inp", placeholder=".r for FP Markets Raw")
            if _ma_tok: st.session_state["ma_token"]     = _ma_tok
            if _ma_acc: st.session_state["ma_account"]   = _ma_acc
            st.session_state["ma_sym_suffix"] = _ma_sfx

            mab1, mab2 = st.columns(2)
            if mab1.button("🔌 Test MT5"):
                with st.spinner("Testing..."):
                    ok, msg = test_mt5_connection(get_ma_token(), get_ma_account())
                st.session_state["ma_test_result"] = (ok, msg)
            if mab2.button("▶ Deploy"):
                with st.spinner("Deploying..."):
                    ok, msg = deploy_mt5_account(get_ma_token(), get_ma_account())
                st.session_state["ma_test_result"] = (ok, msg)

            # Persist test/deploy result so it doesn't disappear on rerun
            if "ma_test_result" in st.session_state:
                ok, msg = st.session_state["ma_test_result"]
                (st.success if ok else st.error)(msg)

            ma_ok = "✅" if (get_ma_token() and get_ma_account()) else "❌"
            st.markdown(f"<div style='font-size:11px;color:#4a5568;font-family:Space Mono,monospace;'>{ma_ok} MetaApi MT5 (Owner)</div>", unsafe_allow_html=True)

            # Save MT5 settings per-user
            if st.button("💾 Save MT5 Settings", key="save_mt5_btn", use_container_width=True):
                uid = get_current_user_id()
                _access_tok = st.session_state.get("auth_access_token", "")
                ok = save_user_settings(uid, {
                    "ma_token": st.session_state.get("ma_token", ""),
                    "ma_account": st.session_state.get("ma_account", ""),
                    "ma_sym_suffix": st.session_state.get("ma_sym_suffix", ""),
                }, access_token=_access_tok)
                if ok:
                    st.success("MT5 settings saved!")
                else:
                    st.error("Failed to save. Check Supabase user_settings table.")

        st.markdown("---")
        st.markdown("<div style='font-size:11px;color:#8b9ab0;font-family:Space Mono,monospace;margin-bottom:4px;'>RISK SETTINGS</div>", unsafe_allow_html=True)
        bal = st.number_input("Balance (USD)", value=st.session_state.get("balance",1000.0), min_value=100.0, key="bal_inp")
        risk_pct = st.number_input("Risk %", value=st.session_state.get("risk_pct",1.0), min_value=0.1, max_value=10.0, step=0.1, key="rsk_inp")
        st.session_state["balance"]  = bal
        st.session_state["risk_pct"] = risk_pct
        ccy_label = st.selectbox("Currency", ["USD","MYR","SGD","EUR","GBP","AUD","JPY"],
                                  index=0, key="ccy_sel")
        st.session_state["currency_label"] = ccy_label

    return page

# ============================================================
# MAIN
# ============================================================
def main():
    page = render_sidebar()

    # ── Auto-sync MT5 positions to DB on every page load ──────
    if _sb_ok() and get_ma_token() and get_ma_account():
        if not st.session_state.get("_mt5_synced_this_run"):
            with st.spinner("🔄 Syncing MT5 positions…"):
                db_trades = sync_mt5_to_db()
            # Merge DB trades into session state for UI compatibility
            st.session_state["active_trades"] = db_trades
            st.session_state["_mt5_synced_this_run"] = True

    if page == "🏠  Overview":
        page_overview()
    elif page == "🔮  Pre-Market":
        page_weekend()
    elif page == "📊  Trades & Journal":
        page_trades()
    elif page == "📈  Performance":
        page_performance()
    elif page == "🔬  Backtest":
        page_backtest()
    else:
        # Extract symbol from page name like "💱  EURUSD"
        sym = page.replace("💱  ","").strip()
        if sym in SYMBOL_CONFIG:
            page_symbol(sym)
        else:
            st.error(f"Unknown page: {page}")

main()
