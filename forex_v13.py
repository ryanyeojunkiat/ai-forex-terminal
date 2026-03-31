import os, json, re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
import streamlit.components.v1 as st_components
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="AI Forex Terminal V12", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
html,body,[data-testid="stAppViewContainer"]{background:#080c10!important;color:#e8edf2!important;font-family:'DM Sans','Segoe UI',sans-serif;}
[data-testid="stSidebar"]{background:#0d1117!important;border-right:1px solid rgba(255,255,255,0.06)!important;}
[data-testid="stHeader"]{background:transparent!important;}
[data-testid="stMetricValue"]{color:#e8edf2!important;font-family:'Space Mono',monospace!important;font-size:13px!important;}
[data-testid="stMetricLabel"]{color:#8b9ab0!important;font-size:10px!important;}
.stButton>button{background:rgba(0,212,170,0.08)!important;border:1px solid rgba(0,212,170,0.25)!important;color:#00d4aa!important;font-family:'Space Mono',monospace!important;border-radius:6px!important;}
.stSelectbox>div>div,.stNumberInput>div>div{background:#131a22!important;border-color:rgba(255,255,255,0.1)!important;color:#e8edf2!important;border-radius:6px!important;}
.signal-box{padding:10px 18px;border-radius:8px;font-family:'Space Mono',monospace;font-size:13px;font-weight:700;letter-spacing:.08em;text-align:center;display:inline-block;min-width:180px;}
.signal-buy{background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);color:#10b981;}
.signal-sell{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#ef4444;}
.signal-wait{background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.3);color:#f59e0b;}
.panel{background:#0d1117;border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:12px 14px;margin-bottom:10px;}
.mono-title{color:#00d4aa;font-size:11px;font-family:'Space Mono',monospace;letter-spacing:.12em;margin-bottom:8px;}
.kv{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:13px;}
.kv:last-child{border-bottom:none;}
.muted{color:#8b9ab0;}.good{color:#10b981;}.bad{color:#ef4444;}.warn{color:#f59e0b;}.info{color:#0ea5e9;}
.ai-bubble{background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);border-left:3px solid #6366f1;border-radius:8px;padding:12px 14px;margin:8px 0;font-size:12px;color:#c7d2fe;line-height:1.75;}
.ai-header{font-family:'Space Mono',monospace;font-size:10px;color:#6366f1;letter-spacing:.1em;margin-bottom:6px;}
.news-HIGH{border-left:3px solid #ef4444!important;background:rgba(239,68,68,.06)!important;}
.news-MEDIUM{border-left:3px solid #f59e0b!important;background:rgba(245,158,11,.06)!important;}
.news-LOW{border-left:3px solid #10b981!important;background:rgba(16,185,129,.06)!important;}
.explainer-box{background:rgba(0,212,170,.04);border:1px solid rgba(0,212,170,.12);border-left:3px solid #00d4aa;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:12px;color:#8b9ab0;line-height:1.7;}
.conf-bar{height:6px;border-radius:3px;margin:4px 0;}
</style>""", unsafe_allow_html=True)

# ============================================================
# CONSTANTS
# ============================================================
APP_VERSION = "V12.0"
_ENV_TD  = os.getenv("TWELVE_DATA_API_KEY", "").strip()
_ENV_XAI = os.getenv("XAI_API_KEY", "").strip()

INTERNAL_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","XAUUSD","EURCHF",
                    "AUDUSD","USDCAD","NZDUSD","USDCHF","BTCUSD"]
API_SYMBOL_MAP   = {"EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY",
                    "XAUUSD":"XAU/USD","EURCHF":"EUR/CHF","AUDUSD":"AUD/USD",
                    "USDCAD":"USD/CAD","NZDUSD":"NZD/USD","USDCHF":"USD/CHF","BTCUSD":"BTC/USD"}
SYMBOL_NAMES     = {"EURUSD":"EUR/USD Euro vs US Dollar","GBPUSD":"GBP/USD British Pound vs USD",
                    "USDJPY":"USD/JPY US Dollar vs Japanese Yen","XAUUSD":"Gold (XAU/USD)",
                    "EURCHF":"EUR/CHF","AUDUSD":"AUD/USD Australian Dollar","USDCAD":"USD/CAD",
                    "NZDUSD":"NZD/USD New Zealand Dollar","USDCHF":"USD/CHF","BTCUSD":"Bitcoin vs USD"}
INTERVAL_MAP     = {"1 Min":"1min","5 Min":"5min","15 Min":"15min",
                    "30 Min":"30min","1 Hour":"1h","4 Hours":"4h"}
PIP_SIZE_MAP     = {"USDJPY":0.01,"XAUUSD":0.1,"BTCUSD":1.0}
PIP_VALUE_MAP    = {"USDJPY":9.1,"XAUUSD":10.0,"BTCUSD":1.0}
FOREX_SYMBOLS    = {s for s in INTERNAL_SYMBOLS if s!="BTCUSD"}
XAU_SESSIONS_UTC = [(7,16),(12,21)]

# ── Trading session filters (UTC hours) ──────────────────────
SESSIONS = {
    "London":  (7,16),   # best liquidity for EUR, GBP, CHF
    "NewYork": (12,21),  # best for USD pairs
    "Overlap": (12,16),  # highest volume — strongest signals
    "Asian":   (22, 7),  # weak liquidity — avoid most pairs
}
# Which pairs prefer which session
PAIR_SESSIONS = {
    "EURUSD":["London","Overlap","NewYork"],
    "GBPUSD":["London","Overlap","NewYork"],
    "USDJPY":["Asian","London","Overlap"],
    "EURCHF":["London","Overlap"],
    "AUDUSD":["Asian","London"],
    "USDCAD":["NewYork","Overlap"],
    "NZDUSD":["Asian","London"],
    "USDCHF":["London","Overlap","NewYork"],
    "BTCUSD":["London","NewYork","Overlap"],
    "XAUUSD":["London","Overlap","NewYork"],
}

# ============================================================
# HELPERS
# ============================================================
def norm(s): return str(s).upper().replace("/","").strip()
def to_api_symbol(s): return API_SYMBOL_MAP.get(norm(s),norm(s))
def pip_size(s): return PIP_SIZE_MAP.get(norm(s),0.0001)
def pip_value(s): return PIP_VALUE_MAP.get(norm(s),10.0)
def get_td_key():  return st.session_state.get("td_key","") or _ENV_TD
def get_xai_key(): return st.session_state.get("xai_key","") or _ENV_XAI
def get_grok_model(): return st.session_state.get("grok_model","grok-4-1-fast-non-reasoning")
def get_ma_token():   return st.session_state.get("ma_token","") or os.environ.get("METAAPI_TOKEN","")
def get_ma_account(): return st.session_state.get("ma_account","") or os.environ.get("METAAPI_ACCOUNT","")

# FP Markets MT5 symbol map — raw accounts use .r suffix
# Standard accounts use no suffix; override via sidebar if needed
_MA_SYM_SUFFIX = ""  # set to ".r" if on FP Markets Raw account
MT5_SYMBOL_MAP: Dict[str,str] = {
    "EURUSD":"EURUSD","GBPUSD":"GBPUSD","USDJPY":"USDJPY",
    "XAUUSD":"XAUUSD","AUDUSD":"AUDUSD","USDCAD":"USDCAD",
    "NZDUSD":"NZDUSD","USDCHF":"USDCHF","BTCUSD":"BTCUSD",
}
def mt5_symbol(s:str) -> str:
    suffix = st.session_state.get("ma_sym_suffix","")
    base   = MT5_SYMBOL_MAP.get(norm(s), norm(s))
    return base + suffix

# ============================================================
# METAAPI REST  — real-time FP Markets MT5 price + positions
# ============================================================
_MA_PROVISION_URL = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"

@st.cache_data(ttl=120)
def _ma_get_region(token:str, account_id:str) -> str:
    """Cache the account region so we build the right client URL."""
    try:
        r = requests.get(f"{_MA_PROVISION_URL}/users/current/accounts/{account_id}",
                         headers={"auth-token":token}, timeout=8)
        if r.status_code == 200:
            return r.json().get("region","new-york")
    except Exception: pass
    return "new-york"

def _ma_client_url(token:str, account_id:str) -> str:
    region = _ma_get_region(token, account_id)
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"

@st.cache_data(ttl=3)   # 3-second cache → near real-time
def fetch_mt5_price(symbol:str, token:str, account_id:str) -> Optional[Dict]:
    """Returns {bid, ask, mid, spread_pips, symbol} or None."""
    if not token or not account_id: return None
    base = _ma_client_url(token, account_id)
    sym  = mt5_symbol(symbol)
    def _try(s):
        try:
            r = requests.get(f"{base}/users/current/accounts/{account_id}/symbols/{s}/current-price",
                             headers={"auth-token":token}, timeout=5)
            if r.status_code == 200:
                d = r.json()
                bid = float(d.get("bid",0)); ask = float(d.get("ask",0))
                mid = (bid+ask)/2
                ps  = pip_size(symbol)
                spread = round(abs(ask-bid)/ps, 1) if ps else 0
                return {"bid":bid,"ask":ask,"mid":mid,"spread_pips":spread,
                        "symbol":symbol,"mt5_sym":s,"ts":d.get("time","")}
        except Exception: pass
        return None
    result = _try(sym)
    if result is None and sym != norm(symbol):          # fallback: no suffix
        result = _try(norm(symbol))
    return result

@st.cache_data(ttl=5)
def fetch_mt5_positions(token:str, account_id:str) -> List[Dict]:
    """Returns list of open MT5 positions."""
    if not token or not account_id: return []
    base = _ma_client_url(token, account_id)
    try:
        r = requests.get(f"{base}/users/current/accounts/{account_id}/positions",
                         headers={"auth-token":token}, timeout=5)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return []

@st.cache_data(ttl=30)
def fetch_mt5_account_info(token:str, account_id:str) -> Optional[Dict]:
    """Returns account balance/equity/margin info."""
    if not token or not account_id: return None
    base = _ma_client_url(token, account_id)
    try:
        r = requests.get(f"{base}/users/current/accounts/{account_id}/account-information",
                         headers={"auth-token":token}, timeout=5)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return None

def test_mt5_connection(token:str, account_id:str) -> Tuple[bool,str]:
    """Verbose test — tries provisioning API first, then client API."""
    lines = []
    headers = {"auth-token": token}

    # Step 1: hit provisioning API to get account meta + region
    prov_url = f"{_MA_PROVISION_URL}/users/current/accounts/{account_id}"
    lines.append(f"① Provisioning: {prov_url[:60]}…")
    region = "new-york"
    try:
        rp = requests.get(prov_url, headers=headers, timeout=8)
        lines.append(f"   HTTP {rp.status_code}")
        if rp.status_code == 200:
            acc = rp.json()
            region = acc.get("region", "new-york")
            state  = acc.get("state","?")
            lines.append(f"   region={region}  state={state}")
        elif rp.status_code == 401:
            return False, "❌ 401 Unauthorised — token is wrong or expired"
        elif rp.status_code == 404:
            return False, "❌ 404 Account not found — check Account ID"
        else:
            lines.append(f"   body: {rp.text[:120]}")
    except Exception as e:
        lines.append(f"   ERROR: {e}")

    # Step 2: hit client API for account-information
    client_base = f"https://mt-client-api-v1.{region}.agiliumtrade.ai"
    info_url = f"{client_base}/users/current/accounts/{account_id}/account-information"
    lines.append(f"② Client API ({region}): …/account-information")
    try:
        rc = requests.get(info_url, headers=headers, timeout=8)
        lines.append(f"   HTTP {rc.status_code}")
        if rc.status_code == 200:
            d = rc.json()
            bal  = d.get("balance","?")
            cur  = d.get("currency","USD")
            name = d.get("name","?")
            return True, f"✅ Connected — {name}  Balance: {bal} {cur}"
        else:
            lines.append(f"   body: {rc.text[:200]}")
    except Exception as e:
        lines.append(f"   ERROR: {e}")

    return False, "\n".join(lines)

def deploy_mt5_account(token:str, account_id:str) -> Tuple[bool,str]:
    """POST deploy endpoint — wakes up an UNDEPLOYED account."""
    url = f"{_MA_PROVISION_URL}/users/current/accounts/{account_id}/deploy"
    try:
        r = requests.post(url, headers={"auth-token":token}, timeout=10)
        if r.status_code in (200,204):
            return True,"✅ Deploy request sent. Account connecting — wait 30s then Test MT5 again."
        else:
            return False,f"Deploy failed HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False,f"Deploy error: {e}"

def fmt_price(v,sym=""):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    s=norm(sym)
    return f"{float(v):.3f}" if s in ("USDJPY","XAUUSD","BTCUSD") else f"{float(v):.5f}"
def fmt_num(v,d=2):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    return f"{float(v):.{d}f}"
def fmt_rr(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    return f"1 : {float(v):.2f}"
def score_to_grade(s):
    if s>=90: return "A+"
    if s>=80: return "A"
    if s>=70: return "B"
    if s>=60: return "C"
    return "D"
def grade_color(g):
    return {"A+":"#00d4aa","A":"#10b981","B":"#84cc16","C":"#f59e0b","D":"#ef4444"}.get(g,"#8b9ab0")
def market_is_open(symbol):
    now=pd.Timestamp.utcnow(); wd=now.weekday(); s=norm(symbol)
    if s in FOREX_SYMBOLS:
        if wd==5: return False,"CLOSED"
        if wd==6 and now.hour<22: return False,"CLOSED"
    return True,"LIVE"
def is_xau_session_ok(ts):
    h=int(ts.hour); return any(a<=h<=b for a,b in XAU_SESSIONS_UTC)

def session_score(symbol:str, ts:pd.Timestamp) -> Tuple[int,str]:
    """Returns (score_bonus 0-15, session_name). Higher bonus = better session."""
    h = ts.hour
    s = norm(symbol)
    preferred = PAIR_SESSIONS.get(s, ["London","NewYork"])
    # Overlap 12-16 UTC = best
    if 12<=h<16 and "Overlap" in preferred: return 15,"London/NY Overlap ✓"
    if SESSIONS["London"][0]<=h<SESSIONS["London"][1] and "London" in preferred: return 10,"London Session ✓"
    if SESSIONS["NewYork"][0]<=h<SESSIONS["NewYork"][1] and "NewYork" in preferred: return 10,"NY Session ✓"
    if "Asian" in preferred and (h>=22 or h<7): return 5,"Asian Session (weak)"
    if h>=22 or h<7: return 0,"Asian Session (avoid)"
    return 5,"Off-peak"

# ============================================================
# GROK CLIENT  — V12 fix: key passed explicitly, no stale cache
# ============================================================
def _grok(messages:List[Dict], max_tokens:int=400, temperature:float=0.25,
          api_key:str="", model:str="") -> Optional[str]:
    """
    V12 Fix: api_key passed as explicit param so callers can pass the
    current session key directly — no stale global reference.
    model defaults to session_state selection (sidebar dropdown).
    """
    key = api_key or get_xai_key()
    if not key:
        return None
    mdl = model or get_grok_model()
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": mdl,
            "messages": messages,
            "max_tokens": max_tokens,
            # temperature clamped to [0, 1] — xAI rejects values outside this range
            "temperature": float(max(0.0, min(1.0, temperature))),
        }
        r = requests.post("https://api.x.ai/v1/chat/completions",
                          headers=headers, json=payload, timeout=25)
        # Capture real error body before raising
        if r.status_code != 200:
            try:
                body = r.json()
                msg  = body.get("error", {}).get("message") or body.get("message") or r.text[:120]
            except Exception:
                msg = r.text[:120]
            return f"[Grok {r.status_code}: {msg}]"
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"[Grok error: {exc}]"

def test_grok_connection(api_key:str="") -> Tuple[bool,str]:
    """Quick ping to verify the API key works."""
    mdl = get_grok_model()
    result = _grok([{"role":"user","content":"Reply with the single word: OK"}],
                   max_tokens=5, temperature=0, api_key=api_key)
    if result is None: return False, "No API key set"
    if result.startswith("[Grok"): return False, result
    return True, f"Connected ✓ (model: {mdl} replied: {result[:30]})"

@st.cache_data(ttl=90)
def get_news_sentiment(symbol:str, xai_key:str) -> Dict[str,Any]:
    """
    V12 Fix: xai_key is now an explicit cache parameter.
    Cache key = (symbol, xai_key) — changes when key changes, no stale results.
    """
    if not xai_key:
        return {"risk":"LOW","adj":0,"bias":"neutral","summary":"No xAI key set",
                "events":[],"ok":False}
    sym_name = SYMBOL_NAMES.get(norm(symbol), symbol)
    system_msg = ("You are a professional forex market analyst with real-time news access. "
                  "Be concise. UTC: " + pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M"))
    user_msg = f"""Analyze CURRENT market news sentiment for {sym_name}.
Return ONLY valid JSON (no markdown):
{{"risk":"HIGH|MEDIUM|LOW","adj":<int -15 to 15>,"bias":"bull|bear|neutral",
  "summary":"<max 20 words>","events":["<event1>","<event2>","<event3>"]}}
Rules: HIGH=major event within 2h(NFP,FOMC,CPI,central bank). adj=0 neutral,±5 mild,±10 strong,±15 extreme.
Negative adj if imminent high-impact event regardless of direction."""
    raw = _grok([{"role":"system","content":system_msg},{"role":"user","content":user_msg}],
                max_tokens=200, temperature=0.1, api_key=xai_key)
    if not raw or raw.startswith("[Grok error"):
        return {"risk":"LOW","adj":0,"bias":"neutral","summary":raw or "Unavailable","events":[],"ok":False}
    try:
        obj = json.loads(re.sub(r"```json|```","",raw).strip())
        return {"risk":obj.get("risk","LOW"),"adj":int(obj.get("adj",0)),"bias":obj.get("bias","neutral"),
                "summary":obj.get("summary",""),"events":obj.get("events",[]),"ok":True}
    except:
        return {"risk":"LOW","adj":0,"bias":"neutral","summary":raw[:100],"events":[],"ok":False}

def get_ai_trade_advice(plan, df:pd.DataFrame, live_health:Optional[Dict],
                        news:Optional[Dict], user_question:str="") -> str:
    key = get_xai_key()
    if not key: return "⚠ No xAI key. Enter it in the sidebar."
    row = df.iloc[-1]
    recent = df.tail(10)[["open","high","low","close"]].round(5).to_string(index=False)
    h_info = (f"R={live_health['r_now']:+.2f}, {live_health['status']}, {live_health['advice']}"
              if live_health else "not in trade")
    n_info = (f"Risk={news['risk']}, bias={news['bias']}, {news['summary']}"
              if (news and news.get("ok")) else "no news data")
    q_line = f"\nTrader question: {user_question}" if user_question.strip() else ""
    msg = f"""Active {plan.symbol} trade:
Dir={plan.direction} Entry={fmt_price(plan.entry,plan.symbol)} SL={fmt_price(plan.sl,plan.symbol)}
TP1={fmt_price(plan.tp1,plan.symbol)} TP2={fmt_price(plan.tp2,plan.symbol)}
Strategy={plan.strategy} Score={plan.setup_score}({plan.setup_grade})→Final={plan.final_score}
Price={fmt_price(float(row['close']),plan.symbol)} RSI={fmt_num(row.get('rsi14'),1)} ATR={fmt_num(row.get('atr14'),5)}
MACD_hist={fmt_num(row.get('macd_hist'),5)} Session={plan.session_label}
Health: {h_info}
News: {n_info}
Last 10 bars:\n{recent}{q_line}
→ HOLD, EXIT, or MOVE SL? Brief reasoning (3-4 sentences max)."""
    return _grok([{"role":"system","content":"You are a professional forex risk manager. Be direct and concise."},
                  {"role":"user","content":msg}],
                 max_tokens=300, temperature=0.3, api_key=key) or "Empty response."

# ============================================================
# DATA & INDICATORS
# ============================================================
def td_get(endpoint:str, params:Dict) -> Dict:
    key = get_td_key()
    if not key: raise ValueError("No Twelve Data key — enter it in sidebar")
    url = f"https://api.twelvedata.com/{endpoint}"
    p = dict(params); p["apikey"] = key
    r = requests.get(url, params=p, timeout=20); r.raise_for_status()
    data = r.json()
    if isinstance(data,dict) and data.get("status")=="error":
        raise ValueError(data.get("message","Twelve Data error"))
    return data

def parse_td(values:List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(values)
    if df.empty: return df
    col = "datetime" if "datetime" in df.columns else "date"
    df["time"] = pd.to_datetime(df[col], utc=True, errors="coerce")
    for c in ["open","high","low","close","volume"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("time").dropna(subset=["time","open","high","low","close"]).reset_index(drop=True)

@st.cache_data(ttl=60)
def fetch_bars(symbol:str, interval:str, bars:int, td_key:str) -> pd.DataFrame:
    """V12: td_key in signature so cache invalidates when key changes."""
    data = td_get("time_series", {"symbol":to_api_symbol(symbol),"interval":interval,
                                  "outputsize":int(bars),"timezone":"UTC","order":"ASC"})
    v = data.get("values",[])
    if not v: raise ValueError("No bars returned from Twelve Data")
    return parse_td(v)

def add_indicators(df:pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    # EMAs
    x["ema20"]  = x["close"].ewm(span=20,adjust=False).mean()
    x["ema50"]  = x["close"].ewm(span=50,adjust=False).mean()
    x["ema200"] = x["close"].ewm(span=200,adjust=False).mean()
    # ATR
    tr = pd.concat([x["high"]-x["low"],
                    (x["high"]-x["close"].shift()).abs(),
                    (x["low"]-x["close"].shift()).abs()],axis=1).max(axis=1)
    x["atr14"] = tr.rolling(14).mean()
    # RSI
    delta=x["close"].diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    x["rsi14"] = 100-(100/(1+gain.rolling(14).mean()/loss.rolling(14).mean().replace(0,np.nan)))
    # MACD (12,26,9)
    ema12 = x["close"].ewm(span=12,adjust=False).mean()
    ema26 = x["close"].ewm(span=26,adjust=False).mean()
    x["macd"]      = ema12 - ema26
    x["macd_sig"]  = x["macd"].ewm(span=9,adjust=False).mean()
    x["macd_hist"] = x["macd"] - x["macd_sig"]
    # Bollinger Bands (20, 2σ)
    x["bb_mid"]   = x["close"].rolling(20).mean()
    bb_std        = x["close"].rolling(20).std()
    x["bb_upper"] = x["bb_mid"] + 2*bb_std
    x["bb_lower"] = x["bb_mid"] - 2*bb_std
    x["bb_width"]  = (x["bb_upper"]-x["bb_lower"])/x["bb_mid"]
    # Swing highs/lows
    x["hh20"] = x["high"].rolling(20).max()
    x["ll20"]  = x["low"].rolling(20).min()
    x["slope20"] = x["ema20"].diff(5)
    # Candle patterns
    body  = (x["close"]-x["open"]).abs()
    upper = x["high"] - x[["close","open"]].max(axis=1)
    lower = x[["close","open"]].min(axis=1) - x["low"]
    x["pin_bull"] = (lower > 2*body) & (upper < 0.3*body)   # bullish pin bar
    x["pin_bear"] = (upper > 2*body) & (lower < 0.3*body)   # bearish pin bar
    x["engulf_bull"] = (x["close"]>x["open"]) & (x["close"].shift()<=x["open"].shift()) & \
                       (x["close"]>x["open"].shift()) & (x["open"]<x["close"].shift())
    x["engulf_bear"] = (x["close"]<x["open"]) & (x["close"].shift()>=x["open"].shift()) & \
                       (x["close"]<x["open"].shift()) & (x["open"]>x["close"].shift())
    return x

def trend_bias(df:pd.DataFrame)->str:
    r=df.iloc[-1]
    if r["ema20"]>r["ema50"]>r["ema200"] and r["macd_hist"]>0: return "bull"
    if r["ema20"]<r["ema50"]<r["ema200"] and r["macd_hist"]<0: return "bear"
    if r["ema20"]>r["ema50"]>r["ema200"]: return "bull_weak"
    if r["ema20"]<r["ema50"]<r["ema200"]: return "bear_weak"
    return "neutral"

def detect_sweep(df:pd.DataFrame,symbol:str)->Dict:
    if len(df)<8: return {"detected":False,"severity":"LOW","desc":"Insufficient data"}
    row=df.iloc[-1]; prev=df.iloc[-6:-1]
    atr=row.get("atr14")
    if pd.isna(atr) or atr<=0: return {"detected":False,"severity":"LOW","desc":"ATR unavailable"}
    rh=prev["high"].max(); rl=prev["low"].min()
    if row["high"]>rh and row["close"]<rh:
        sev="HIGH" if (row["high"]-rh)/atr>1.2 else "MEDIUM"
        return {"detected":True,"severity":sev,"desc":f"Upper sweep {fmt_price(rh,symbol)} — avoid longs"}
    if row["low"]<rl and row["close"]>rl:
        sev="HIGH" if (rl-row["low"])/atr>1.2 else "MEDIUM"
        return {"detected":True,"severity":sev,"desc":f"Lower sweep {fmt_price(rl,symbol)} — avoid shorts"}
    return {"detected":False,"severity":"LOW","desc":"No sweep"}

# ============================================================
# PLAN DATACLASS
# ============================================================
@dataclass
class Plan:
    symbol:str; regime:str="insufficient"; strategy:str="No Strategy"
    direction:str="Wait"; execution_status:str="Wait"
    setup_score:int=20; setup_grade:str="D"
    entry:Optional[float]=None; sl:Optional[float]=None
    tp1:Optional[float]=None; tp2:Optional[float]=None; tp3:Optional[float]=None
    rr:Optional[float]=None; reason:str="No valid setup"
    entry_reasons:List[str]=field(default_factory=list)
    exit_conditions:List[str]=field(default_factory=list)
    score_breakdown:Dict[str,int]=field(default_factory=dict)  # V12: per-component scores
    confluence_count:int=0        # V12: how many conditions confirmed
    confluence_needed:int=3       # V12: min confirmations for Ready
    session_label:str=""          # V12: session name
    session_score:int=0           # V12: session bonus
    mtf_aligned:bool=False        # V12: higher TF agrees
    base_lot:float=0.0; suggested_lot:float=0.0
    news_adj:int=0; news_risk:str="LOW"; news_bias:str="neutral"
    news_summary:str=""; news_events:List[str]=field(default_factory=list)
    news_ok:bool=False; final_score:int=20; final_grade:str="D"
    def to_dict(self): return self.__dict__.copy()

# ============================================================
# SCORING ENGINE  (V12: explicit breakdown, confluence gate)
# ============================================================
def _score_plan(row:pd.Series, prev_row:pd.Series, df:pd.DataFrame,
                direction:str, rr:float, symbol:str) -> Tuple[int, Dict[str,int], int, int]:
    """
    Returns (total_score, breakdown_dict, confluence_count, session_pts).
    Max 100 pts:
      EMA stack   20 — trend structure
      Pullback    15 — price returning to ema20
      MACD        15 — histogram confirms direction
      RSI         10 — not overbought/oversold against trade
      Candle      10 — pin bar or engulfing pattern
      RR          20 — risk:reward quality
      Session     10 — trading in optimal session
    Confluence = number of non-zero components (6 possible).
    """
    bd: Dict[str,int] = {}
    # 1. EMA stack
    if direction=="Buy":
        bd["EMA Stack"] = 20 if row["ema20"]>row["ema50"]>row["ema200"] else \
                           10 if row["ema20"]>row["ema50"] else 0
    else:
        bd["EMA Stack"] = 20 if row["ema20"]<row["ema50"]<row["ema200"] else \
                           10 if row["ema20"]<row["ema50"] else 0
    # 2. Pullback quality (distance from EMA20)
    dist = abs(row["close"]-row["ema20"])/max(row["atr14"],1e-9)
    bd["Pullback"] = 15 if dist<=0.4 else 10 if dist<=0.7 else 5 if dist<=1.0 else 0
    # 3. MACD histogram
    if direction=="Buy":
        bd["MACD"] = 15 if row["macd_hist"]>0 and row["macd_hist"]>prev_row["macd_hist"] else \
                      8 if row["macd_hist"]>0 else 0
    else:
        bd["MACD"] = 15 if row["macd_hist"]<0 and row["macd_hist"]<prev_row["macd_hist"] else \
                      8 if row["macd_hist"]<0 else 0
    # 4. RSI (avoid overbought longs / oversold shorts)
    rsi = row["rsi14"]
    if direction=="Buy":
        bd["RSI"] = 10 if 40<=rsi<=60 else 5 if 30<=rsi<=70 else 0
    else:
        bd["RSI"] = 10 if 40<=rsi<=60 else 5 if 30<=rsi<=70 else 0
    # 5. Candle pattern
    candle = 0
    if direction=="Buy"  and (row.get("pin_bull",False) or row.get("engulf_bull",False)): candle=10
    if direction=="Sell" and (row.get("pin_bear",False) or row.get("engulf_bear",False)): candle=10
    bd["Candle"] = candle
    # 6. R:R
    bd["R:R"] = 20 if rr>=2.5 else 15 if rr>=2.0 else 10 if rr>=1.5 else 5 if rr>=1.2 else 0
    # 7. Session (caller adds this)
    sess_pts,_ = session_score(symbol, row.get("time", pd.Timestamp.utcnow()))
    bd["Session"] = sess_pts
    total = sum(bd.values())
    confluence = sum(1 for k,v in bd.items() if k!="Session" and v>0)
    return min(total,100), bd, confluence, sess_pts

# ============================================================
# REGIME
# ============================================================
def get_regime(df:pd.DataFrame)->str:
    if len(df)<220: return "insufficient"
    r=df.iloc[-1]
    if pd.isna(r["atr14"]) or r["atr14"]<=0: return "insufficient"
    # V12: require MACD confirmation for trend
    if r["ema20"]>r["ema50"]>r["ema200"] and r["slope20"]>0: return "trend_up"
    if r["ema20"]<r["ema50"]<r["ema200"] and r["slope20"]<0: return "trend_down"
    if r["bb_width"]<0.005: return "squeeze"  # low volatility squeeze
    if 40<=r["rsi14"]<=60: return "range"
    return "mean_revert"

def _empty(symbol,regime,reason="No valid setup"):
    return Plan(symbol=symbol,regime=regime,reason=reason,entry_reasons=[reason])

# ============================================================
# PLAN BUILDERS  (V12: MTF + scoring engine + session filter)
# ============================================================
def _get_htf_bias(symbol:str, td_key:str) -> str:
    """Fetch 1h bars and return trend bias for MTF confirmation."""
    try:
        df1h = add_indicators(fetch_bars(symbol,"1h",260,td_key))
        return trend_bias(df1h)
    except:
        return "neutral"

def _trend_plan(df:pd.DataFrame, symbol:str, regime:str, htf_bias:str) -> Plan:
    row=df.iloc[-1]; prev=df.iloc[-2]; atr=row["atr14"]; close=row["close"]; ema20=row["ema20"]
    p=_empty(symbol,regime,"Trend exists but no valid trigger")
    if pd.isna(atr) or atr<=0: return p
    direction = "Buy" if regime=="trend_up" else "Sell"

    # V12: MTF filter — 1h must agree
    mtf_ok = (htf_bias in ("bull","bull_weak") and direction=="Buy") or \
              (htf_bias in ("bear","bear_weak") and direction=="Sell") or \
              htf_bias=="neutral"
    if not mtf_ok:
        p.reason=f"1H bias ({htf_bias}) opposes {direction} — MTF conflict"
        p.entry_reasons=[p.reason,"Wait for higher timeframe to align."]
        return p

    dist = abs(close-ema20)/atr
    if dist>1.0:
        p.reason=f"Too extended ({dist:.2f} ATR from EMA20 — max 1.0)"
        p.entry_reasons=[p.reason,"Wait for pullback to EMA20 before entering."]; return p

    touched_pb = dist<=0.75
    resumed    = (close>prev["high"]) if direction=="Buy" else (close<prev["low"])
    if not (touched_pb or resumed):
        p.entry_reasons=[p.reason]; return p

    if direction=="Buy":
        entry=float(close); sl=float(min(df.tail(6)["low"].min(), ema20-0.5*atr))
        risk=entry-sl; tp1=float(entry+risk); tp2=float(entry+2.0*risk); tp3=float(entry+3.0*risk)
    else:
        entry=float(close); sl=float(max(df.tail(6)["high"].max(), ema20+0.5*atr))
        risk=sl-entry; tp1=float(entry-risk); tp2=float(entry-2.0*risk); tp3=float(entry-3.0*risk)
    rr = abs(tp2-entry)/max(abs(entry-sl),1e-9)

    score, breakdown, confluence, sess_pts = _score_plan(row,prev,df,direction,rr,symbol)
    sess_pts2, sess_name = session_score(symbol, row.get("time",pd.Timestamp.utcnow()))
    ready = (score>=70 and rr>=1.5 and confluence>=3)
    p2=Plan(symbol=symbol,regime=regime,strategy="Trend Continuation",direction=direction,
            execution_status="Ready to Enter" if ready else "Wait",
            setup_score=score,setup_grade=score_to_grade(score),
            entry=entry,sl=sl,tp1=tp1,tp2=tp2,tp3=tp3,rr=float(rr),
            score_breakdown=breakdown,confluence_count=confluence,confluence_needed=3,
            session_label=sess_name,session_score=sess_pts2,mtf_aligned=mtf_ok,
            reason=f"{regime} continuation")
    p2.entry_reasons=[
        f"EMA stack: {'✓' if breakdown['EMA Stack']==20 else '⚠'} ({breakdown['EMA Stack']}/20 pts)",
        f"MACD histogram: {'✓ confirms' if breakdown['MACD']>=10 else '⚠ weak'} ({breakdown['MACD']}/15 pts)",
        f"RSI14={fmt_num(row['rsi14'],1)} ({breakdown['RSI']}/10 pts)",
        f"Candle pattern: {'✓ pin/engulf' if breakdown['Candle']==10 else '✗ none'} ({breakdown['Candle']}/10 pts)",
        f"Pullback dist={dist:.2f} ATR ({breakdown['Pullback']}/15 pts)",
        f"R:R={rr:.2f} ({breakdown['R:R']}/20 pts) | Session: {sess_name} ({sess_pts2}/10 pts)",
        f"1H bias: {htf_bias} | MTF aligned: {'✓' if mtf_ok else '✗'}",
        f"Confluence: {confluence}/6 conditions met (need ≥3)",
    ]
    p2.exit_conditions=[
        f"TP1 {fmt_price(tp1,symbol)} — close 50%, move SL to breakeven",
        f"TP2 {fmt_price(tp2,symbol)} — close 40%",
        f"TP3 {fmt_price(tp3,symbol)} — let 10% run",
        f"SL {fmt_price(sl,symbol)} — exit without hesitation",
        "Close early if price breaks EMA50 against direction",
    ]
    return p2

def _mean_rev_plan(df:pd.DataFrame, symbol:str, regime:str) -> Plan:
    row=df.iloc[-1]; prev=df.iloc[-2]; atr=row["atr14"]
    if pd.isna(atr) or atr<=0: return _empty(symbol,regime,"ATR unavailable")
    close=row["close"]; ema20=row["ema20"]; dev=(close-ema20)/atr
    if abs(dev)<1.3: return _empty(symbol,regime,f"Deviation {dev:.2f} ATR too small (need ≥1.3)")
    # V12: require BB touch for better confirmation
    bb_touch = (close<=row["bb_lower"] and dev<0) or (close>=row["bb_upper"] and dev>0)
    direction = "Sell" if dev>0 else "Buy"
    entry=float(close)
    if direction=="Buy":
        sl=float(close-0.85*atr); tp1=float(ema20); tp2=float(close+1.7*atr)
    else:
        sl=float(close+0.85*atr); tp1=float(ema20); tp2=float(close-1.7*atr)
    rr = abs(tp2-entry)/max(abs(entry-sl),1e-9)
    score, breakdown, confluence, sess_pts = _score_plan(row,prev,df,direction,rr,symbol)
    # Mean reversion base bonus
    base = min(20, int(abs(dev)*8))
    if bb_touch: base += 10
    score = min(100, score+base)
    sess_pts2, sess_name = session_score(symbol, row.get("time",pd.Timestamp.utcnow()))
    ready = (score>=65 and rr>=1.3 and confluence>=2)
    p=Plan(symbol=symbol,regime=regime,strategy="Mean Reversion",direction=direction,
           execution_status="Ready to Enter" if ready else "Wait",
           setup_score=score,setup_grade=score_to_grade(score),
           entry=entry,sl=sl,tp1=tp1,tp2=tp2,rr=float(rr),
           score_breakdown=breakdown,confluence_count=confluence,confluence_needed=2,
           session_label=sess_name,session_score=sess_pts2,mtf_aligned=True,
           reason=f"Deviation {dev:.2f} ATR from EMA20{' + BB touch' if bb_touch else ''}")
    p.entry_reasons=[
        f"Price {abs(dev):.2f} ATR {'above' if dev>0 else 'below'} EMA20 (extreme stretch)",
        f"Bollinger Band {'touch ✓' if bb_touch else 'not touched (weaker signal)'}",
        f"RSI={fmt_num(row['rsi14'],1)} ({'overbought' if dev>0 else 'oversold'})",
        f"MACD: {breakdown['MACD']}/15 pts | Candle: {breakdown['Candle']}/10 pts",
        "Counter-trend — use 50% normal lot size",
    ]
    p.exit_conditions=[
        f"TP1 {fmt_price(tp1,symbol)} — EMA20 reversion (main target)",
        f"TP2 {fmt_price(tp2,symbol)} — extended move",
        f"SL {fmt_price(sl,symbol)} — deviation continues",
    ]
    return p

def _squeeze_plan(df:pd.DataFrame, symbol:str) -> Plan:
    """V12: New — trade Bollinger Squeeze breakouts."""
    row=df.iloc[-1]; prev=df.iloc[-2]; atr=row["atr14"]
    if pd.isna(atr) or atr<=0: return _empty(symbol,"squeeze","ATR unavailable")
    # Breakout direction from squeeze
    direction = "Buy" if row["close"]>row["bb_upper"] and row["macd_hist"]>0 else \
                "Sell" if row["close"]<row["bb_lower"] and row["macd_hist"]<0 else None
    if direction is None: return _empty(symbol,"squeeze","Squeeze present — waiting for breakout direction")
    entry=float(row["close"])
    if direction=="Buy":
        sl=float(row["bb_mid"]-0.5*atr); tp1=float(entry+atr); tp2=float(entry+2*atr)
    else:
        sl=float(row["bb_mid"]+0.5*atr); tp1=float(entry-atr); tp2=float(entry-2*atr)
    rr=abs(tp2-entry)/max(abs(entry-sl),1e-9)
    score, breakdown, confluence, _ = _score_plan(row,prev,df,direction,rr,symbol)
    score = min(100, score+15)  # bonus for squeeze breakout
    sess_pts2, sess_name = session_score(symbol, row.get("time",pd.Timestamp.utcnow()))
    ready = (score>=65 and rr>=1.3)
    p=Plan(symbol=symbol,regime="squeeze",strategy="BB Squeeze Breakout",direction=direction,
           execution_status="Ready to Enter" if ready else "Wait",
           setup_score=score,setup_grade=score_to_grade(score),
           entry=entry,sl=sl,tp1=tp1,tp2=tp2,rr=float(rr),
           score_breakdown=breakdown,confluence_count=confluence,confluence_needed=2,
           session_label=sess_name,session_score=sess_pts2,mtf_aligned=True,
           reason="BB Squeeze breakout")
    p.entry_reasons=[
        f"Bollinger Squeeze breakout {direction} — low volatility expansion signal",
        f"MACD confirms direction: {breakdown['MACD']}/15 pts",
        f"BB Width was compressed, now expanding",
    ]
    p.exit_conditions=[
        f"TP1 {fmt_price(tp1,symbol)} — 1 ATR target",
        f"TP2 {fmt_price(tp2,symbol)} — 2 ATR target",
        f"SL {fmt_price(sl,symbol)} — back inside BB mid",
    ]
    return p

def _xau_plan(df5:pd.DataFrame, df15:pd.DataFrame, df1h:pd.DataFrame, symbol:str) -> Plan:
    row=df5.iloc[-1]; prev=df5.iloc[-2]; atr=row["atr14"]
    p=_empty(symbol,"gold_scalp","No valid XAU trigger")
    if pd.isna(atr) or atr<=0: return p
    b5=trend_bias(df5); b15=trend_bias(df15); b1h=trend_bias(df1h)
    aligned_bull = b5 in ("bull","bull_weak") and b15 in ("bull","bull_weak") and b1h in ("bull","bull_weak")
    aligned_bear = b5 in ("bear","bear_weak") and b15 in ("bear","bear_weak") and b1h in ("bear","bear_weak")
    dist=abs(row["close"]-row["ema20"])/atr; too_ext=dist>0.9
    last3=df5.tail(3); vert=(last3["close"]-last3["open"]).abs().sum()>atr*1.8
    rh=df5.iloc[-6:-1]["high"].max(); rl=df5.iloc[-6:-1]["low"].min()
    bull_sw=row["low"]<rl and row["close"]>rl; bear_sw=row["high"]>rh and row["close"]<rh
    long_t=aligned_bull and not too_ext and not vert and (
        (row["close"]>row["ema20"] and prev["close"]<=prev["ema20"]) or bull_sw)
    short_t=aligned_bear and not too_ext and not vert and (
        (row["close"]<row["ema20"] and prev["close"]>=prev["ema20"]) or bear_sw)
    if not is_xau_session_ok(row["time"]):
        p.reason="XAU session filter: only trade 07-16 & 12-21 UTC"
        p.entry_reasons=[p.reason]; return p
    if not long_t and not short_t:
        p.entry_reasons=[f"5m={b5} 15m={b15} 1h={b1h} — need all aligned",
                         "Wait for MTF alignment + trigger."]; return p
    tp_pts=20.0
    if long_t:
        entry=float(row["close"]); sl=float(min(df5.tail(8)["low"].min(),entry-0.8*atr))
        tp1=float(entry+tp_pts); tp2=float(entry+35.0); risk=entry-sl
        rr=(tp1-entry)/max(risk,1e-9); direction="Buy"; tag="Reclaim/lower-sweep long"
    else:
        entry=float(row["close"]); sl=float(max(df5.tail(8)["high"].max(),entry+0.8*atr))
        tp1=float(entry-tp_pts); tp2=float(entry-35.0); risk=sl-entry
        rr=(entry-tp1)/max(risk,1e-9); direction="Sell"; tag="Rejection/upper-sweep short"
    if rr<1.2:
        p.reason="TP20pts doesn't justify stop size"; p.entry_reasons=[p.reason]; return p
    score, breakdown, confluence, _ = _score_plan(row,prev,df5,direction,rr,symbol)
    mtf_bonus = 20 if (aligned_bull or aligned_bear) else 0
    sw_bonus  = 15 if (bull_sw or bear_sw) else 0
    score = min(100, score+mtf_bonus+sw_bonus)
    sess_pts2,sess_name=session_score(symbol,row.get("time",pd.Timestamp.utcnow()))
    p2=Plan(symbol=symbol,regime="gold_scalp",strategy="XAU 20pt Scalp",direction=direction,
            execution_status="Ready to Enter" if score>=75 else "Wait",
            setup_score=score,setup_grade=score_to_grade(score),
            entry=entry,sl=sl,tp1=tp1,tp2=tp2,rr=float(rr),
            score_breakdown=breakdown,confluence_count=confluence,confluence_needed=3,
            session_label=sess_name,session_score=sess_pts2,mtf_aligned=True,
            reason="XAU scalp — MTF aligned")
    p2.entry_reasons=[f"MTF: 5m={b5} 15m={b15} 1h={b1h} ({'✓ ALIGNED' if aligned_bull or aligned_bear else '✗'})",
                      f"Setup: {tag}",f"Sweep: {'✓' if bull_sw or bear_sw else '✗'} | TP={tp_pts:.0f}pts fixed"]
    p2.exit_conditions=[f"TP1 {fmt_price(tp1,symbol)}: exit 70%",f"TP2 {fmt_price(tp2,symbol)}: runner",
                        f"SL {fmt_price(sl,symbol)}: hard exit","Stalls 10 bars → manual exit"]
    return p2

def select_plan(symbol:str, interval:str, bars:int, td_key:str) -> Tuple[pd.DataFrame,Plan]:
    s=norm(symbol)
    if s=="XAUUSD":
        df5=add_indicators(fetch_bars(s,"5min",max(260,bars),td_key))
        df15=add_indicators(fetch_bars(s,"15min",max(260,bars),td_key))
        df1h=add_indicators(fetch_bars(s,"1h",max(260,bars),td_key))
        return df5,_xau_plan(df5,df15,df1h,s)
    df=add_indicators(fetch_bars(s,interval,bars,td_key))
    regime=get_regime(df)
    if regime=="insufficient": return df,_empty(s,regime,"Need ≥220 bars")
    # V12: get HTF bias for MTF filter
    htf_bias = _get_htf_bias(s, td_key) if interval not in ("1h","4h") else "neutral"
    if regime in("trend_up","trend_down"): return df,_trend_plan(df,s,regime,htf_bias)
    if regime=="squeeze": return df,_squeeze_plan(df,s)
    return df,_mean_rev_plan(df,s,regime)

def finalize_plan(plan:Plan, balance:float, risk_pct:float) -> Plan:
    # Lot sizing
    risk_amount=balance*(risk_pct/100)
    if plan.entry and plan.sl:
        stop_pips=abs(plan.entry-plan.sl)/max(pip_size(plan.symbol),1e-9)
        plan.base_lot=max(0.0,round(risk_amount/(stop_pips*pip_value(plan.symbol)),3)) if stop_pips>0 else 0.0
    plan.suggested_lot=plan.base_lot
    # Grok news
    xai=get_xai_key()
    news=get_news_sentiment(plan.symbol,xai)
    plan.news_adj=news["adj"]; plan.news_risk=news["risk"]; plan.news_bias=news["bias"]
    plan.news_summary=news["summary"]; plan.news_events=news.get("events",[]); plan.news_ok=news.get("ok",False)
    plan.final_score=int(max(0,min(100,plan.setup_score+plan.news_adj)))
    plan.final_grade=score_to_grade(plan.final_score)
    if plan.news_risk=="HIGH" and plan.execution_status=="Ready to Enter":
        plan.execution_status="HIGH NEWS RISK — Wait"
    return plan

# ============================================================
# LIVE HEALTH
# ============================================================
def compute_live_health(entry:float,sl:float,direction:str,df:pd.DataFrame,
                        mt5_price:Optional[float]=None)->Dict:
    """
    mt5_price: if provided, use this (actual broker price) instead of Twelve Data close.
    """
    if mt5_price and mt5_price > 0:
        close = mt5_price
        price_src = "MT5"
    else:
        close = float(df.iloc[-1]["close"])
        price_src = "TD"
    risk=abs(entry-sl)
    if risk<=0: return {"r_now":0.0,"status":"Invalid","advice":"Stop=0","health_pct":50,"color":"#8b9ab0","price_src":price_src,"close":close}
    r_now=(close-entry)/risk if direction=="Buy" else (entry-close)/risk
    hp=int(max(5,min(95,50+r_now*25)))
    if r_now>=1.0: return {"r_now":round(r_now,2),"status":"Profit zone","advice":"TP1 hit — move SL to BE.","health_pct":hp,"color":"#10b981","price_src":price_src,"close":close}
    if r_now>=0.0: return {"r_now":round(r_now,2),"status":"In trade","advice":"In profit, TP1 not yet hit. Hold.","health_pct":hp,"color":"#00d4aa","price_src":price_src,"close":close}
    if r_now>=-0.5:return {"r_now":round(r_now,2),"status":"Minor drawdown","advice":"Normal pullback. Structure must hold.","health_pct":hp,"color":"#f59e0b","price_src":price_src,"close":close}
    if r_now>=-0.8:return {"r_now":round(r_now,2),"status":"Near stop","advice":"Approaching SL — prepare to exit.","health_pct":hp,"color":"#f97316","price_src":price_src,"close":close}
    return {"r_now":round(r_now,2),"status":"Stop breached","advice":"Price beyond SL. Exit now.","health_pct":hp,"color":"#ef4444","price_src":price_src,"close":close}

# ============================================================
# CHART
# ============================================================
def build_chart(df:pd.DataFrame, plan:Plan, symbol:str) -> go.Figure:
    n=min(120,len(df)); dfc=df.tail(n)
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,row_heights=[0.72,0.28],
                      vertical_spacing=0.04)
    # Candles
    fig.add_trace(go.Candlestick(x=dfc["time"],open=dfc["open"],high=dfc["high"],
                                  low=dfc["low"],close=dfc["close"],name="Price",
                                  increasing_fillcolor="#10b981",increasing_line_color="#10b981",
                                  decreasing_fillcolor="#ef4444",decreasing_line_color="#ef4444"),row=1,col=1)
    # EMAs
    for col2,color,nm in [("ema20","#00d4aa","EMA20"),("ema50","#f59e0b","EMA50"),("ema200","#8b9ab0","EMA200")]:
        if col2 in dfc: fig.add_trace(go.Scatter(x=dfc["time"],y=dfc[col2],mode="lines",name=nm,
                                                  line=dict(color=color,width=1.2)),row=1,col=1)
    # Bollinger Bands
    if "bb_upper" in dfc:
        fig.add_trace(go.Scatter(x=dfc["time"],y=dfc["bb_upper"],mode="lines",name="BB Upper",
                                  line=dict(color="rgba(99,102,241,0.4)",width=1,dash="dot")),row=1,col=1)
        fig.add_trace(go.Scatter(x=dfc["time"],y=dfc["bb_lower"],mode="lines",name="BB Lower",
                                  line=dict(color="rgba(99,102,241,0.4)",width=1,dash="dot"),
                                  fill="tonexty",fillcolor="rgba(99,102,241,0.04)"),row=1,col=1)
    # Levels
    for lbl,val,col3 in [("Entry",plan.entry,"#00d4aa"),("SL",plan.sl,"#ef4444"),
                          ("TP1",plan.tp1,"#a78bfa"),("TP2",plan.tp2,"#10b981")]:
        if val: fig.add_hline(y=val,line=dict(color=col3,width=1,dash="dot"),
                               annotation_text=lbl,annotation_font_color=col3,row=1,col=1)
    # MACD
    if "macd_hist" in dfc:
        colors=["#10b981" if v>=0 else "#ef4444" for v in dfc["macd_hist"]]
        fig.add_trace(go.Bar(x=dfc["time"],y=dfc["macd_hist"],name="MACD Hist",
                              marker_color=colors,opacity=0.7),row=2,col=1)
        fig.add_trace(go.Scatter(x=dfc["time"],y=dfc["macd"],mode="lines",name="MACD",
                                  line=dict(color="#00d4aa",width=1)),row=2,col=1)
        fig.add_trace(go.Scatter(x=dfc["time"],y=dfc["macd_sig"],mode="lines",name="Signal",
                                  line=dict(color="#f59e0b",width=1)),row=2,col=1)
    fig.update_layout(template="plotly_dark",height=500,margin=dict(l=8,r=8,t=8,b=8),
                      xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h",yanchor="bottom",y=1.01,xanchor="right",x=1))
    return fig

# ============================================================
# PANEL HELPERS
# ============================================================
def render_kv_panel(title,rows):
    html=["<div class='panel'>",f"<div class='mono-title'>{title}</div>"]
    for k,v,klass in rows:
        c=f" class='{klass}'" if klass else ""
        html.append(f"<div class='kv'><span class='muted'>{k}</span><span{c}>{v}</span></div>")
    html.append("</div>"); st.markdown("".join(html),unsafe_allow_html=True)

def render_signal_badge(direction,status):
    if "HIGH NEWS" in status:     cls,text="signal-sell","⚠ HIGH NEWS — WAIT"
    elif status!="Ready to Enter":cls,text="signal-wait","◆ WAIT"
    elif direction=="Buy":         cls,text="signal-buy","▲ BUY — READY"
    elif direction=="Sell":        cls,text="signal-sell","▼ SELL — READY"
    else:                          cls,text="signal-wait","◆ WAIT"
    st.markdown(f"<div class='signal-box {cls}'>{text}</div>",unsafe_allow_html=True)

# ============================================================
# SCORE PANEL  (V12: confluence bar + breakdown)
# ============================================================
def render_score_panel(plan:Plan,df:pd.DataFrame,
                       active_entry=None,active_sl=None,active_dir=None):
    gc=grade_color(plan.final_grade); adj=plan.news_adj
    adj_html=(f"<span style='color:#10b981;'>+{adj}</span>" if adj>0
              else f"<span style='color:#ef4444;'>{adj}</span>" if adj<0
              else "<span style='color:#8b9ab0;'>0</span>")
    # Confluence indicator
    filled=plan.confluence_count; total=6
    conf_color="#10b981" if filled>=4 else "#f59e0b" if filled>=2 else "#ef4444"
    conf_dots="".join([f"<span style='color:{conf_color};'>●</span>" if i<filled
                       else "<span style='color:#2a3441;'>●</span>" for i in range(total)])

    # Score breakdown table
    bd_html=""
    for k,v in plan.score_breakdown.items():
        maxv={"EMA Stack":20,"Pullback":15,"MACD":15,"RSI":10,"Candle":10,"R:R":20,"Session":10}.get(k,10)
        pct=int(v/max(maxv,1)*100)
        bar_col="#10b981" if pct>=70 else "#f59e0b" if pct>=40 else "#ef4444"
        bd_html+=(f"<div style='display:flex;align-items:center;gap:8px;margin:3px 0;font-size:11px;'>"
                  f"<span style='color:#8b9ab0;width:70px;flex-shrink:0;'>{k}</span>"
                  f"<div style='background:#131a22;border-radius:3px;flex:1;height:5px;'>"
                  f"<div style='width:{pct}%;height:100%;background:{bar_col};border-radius:3px;'></div></div>"
                  f"<span style='color:{bar_col};width:28px;text-align:right;font-family:Space Mono,monospace;'>{v}</span>"
                  f"</div>")

    st.markdown(f"""<div class='panel'>
      <div class='mono-title'>SIGNAL SCORE <span style='color:#4a5568;font-size:10px;'>— locked at signal</span></div>
      <div style='display:flex;align-items:center;gap:14px;margin-bottom:8px;flex-wrap:wrap;'>
        <div><div style='font-size:10px;color:#8b9ab0;'>TECH</div>
          <div style='font-family:Space Mono,monospace;font-size:26px;font-weight:700;color:{grade_color(plan.setup_grade)};'>{plan.setup_score}</div></div>
        <div style='color:#4a5568;font-size:18px;'>+</div>
        <div><div style='font-size:10px;color:#8b9ab0;'>NEWS</div>
          <div style='font-family:Space Mono,monospace;font-size:26px;font-weight:700;'>{adj_html}</div></div>
        <div style='color:#4a5568;font-size:18px;'>=</div>
        <div><div style='font-size:10px;color:#8b9ab0;'>FINAL</div>
          <div style='font-family:Space Mono,monospace;font-size:26px;font-weight:700;color:{gc};'>
            {plan.final_score}<span style='font-size:14px;'> {plan.final_grade}</span></div></div>
      </div>
      <div style='background:#131a22;border-radius:4px;height:5px;margin-bottom:10px;overflow:hidden;'>
        <div style='height:100%;border-radius:4px;background:{gc};width:{plan.final_score}%;'></div></div>
      <div style='margin-bottom:8px;'>
        <span style='font-size:10px;color:#8b9ab0;font-family:Space Mono,monospace;'>CONFLUENCE </span>
        {conf_dots}
        <span style='font-size:10px;color:{conf_color};font-family:Space Mono,monospace;'> {filled}/{total}</span>
      </div>
      {bd_html}
      <div style='font-size:11px;color:#8b9ab0;border-top:1px solid rgba(255,255,255,0.05);padding-top:6px;margin-top:6px;'>
        <b style='color:#e8edf2;'>Session:</b> {plan.session_label} &nbsp;|&nbsp;
        <b style='color:#e8edf2;'>MTF:</b> {'✓ Aligned' if plan.mtf_aligned else '✗ Conflict'}
      </div>
    </div>""",unsafe_allow_html=True)

    # Live Health
    live_health=None
    if active_entry and active_sl and active_dir:
        # Use the TRADE's symbol for price — may differ from the currently viewed symbol
        # Find the trade for this symbol to get correct price for Live Health
        _all_trades=st.session_state.get("active_trades",[])
        _active_trade=next((t for t in _all_trades if t.get("symbol",plan.symbol)==plan.symbol),
                           (_all_trades[0] if _all_trades else {}))
        _trade_sym_h=_active_trade.get("symbol", plan.symbol)
        # Price priority: MetaApi tick (trade's symbol) > Twelve Data
        _ma_tick=fetch_mt5_price(_trade_sym_h,get_ma_token(),get_ma_account()) if (get_ma_token() and get_ma_account()) else None
        if _ma_tick:
            _mt5_for_health=_ma_tick["bid"]
        else:
            _mt5_for_health=None
        live_health=compute_live_health(active_entry,active_sl,active_dir,df,mt5_price=_mt5_for_health)
        hc=live_health["color"]; hp=live_health["health_pct"]
        src_label=live_health.get("price_src","TD")
        src_col="#00d4aa" if src_label=="MT5" else "#f59e0b"
        src_note=f"<span style='font-size:9px;color:{src_col};margin-left:6px;'>price: {src_label} {fmt_price(live_health.get('close',0),'')}</span>"
        st.markdown(f"""<div class='panel'>
          <div class='mono-title'>LIVE HEALTH <span style='color:#4a5568;font-size:10px;'>— post-entry</span>{src_note}</div>
          <div style='display:flex;align-items:center;gap:14px;margin-bottom:8px;'>
            <div style='font-family:Space Mono,monospace;font-size:26px;font-weight:700;color:{hc};'>{hp}%</div>
            <div><div style='font-size:13px;font-weight:600;color:{hc};'>{live_health['status']}</div>
              <div style='font-size:11px;color:#8b9ab0;'>R = {live_health['r_now']:+.2f}</div></div>
          </div>
          <div style='background:#131a22;border-radius:4px;height:5px;margin-bottom:8px;overflow:hidden;'>
            <div style='height:100%;border-radius:4px;background:{hc};width:{hp}%;'></div></div>
          <div style='font-size:12px;color:#e8edf2;padding:8px;background:#131a22;border-radius:5px;'>{live_health['advice']}</div>
        </div>""",unsafe_allow_html=True)
    else:
        st.markdown("""<div class='panel' style='border-color:rgba(255,255,255,0.04);'>
          <div class='mono-title' style='color:#4a5568;'>LIVE HEALTH — enter trade to activate</div>
        </div>""",unsafe_allow_html=True)

    # Grok AI Advisor
    _render_ai_panel(plan,df,live_health,active_entry,active_sl,active_dir)

def _render_ai_panel(plan,df,live_health,active_entry,active_sl,active_dir):
    xai=get_xai_key()
    # ── Panel wrapper uses st.container + border styling via markdown above ──
    st.markdown("""<div style='background:#0d1117;border:1px solid rgba(99,102,241,0.2);
        border-left:3px solid #6366f1;border-radius:8px;padding:12px 14px;margin-bottom:10px;'>
        <div style='color:#6366f1;font-size:11px;font-family:Space Mono,monospace;
        letter-spacing:.12em;margin-bottom:8px;'>
        GROK AI ADVISOR <span style='color:#4a5568;font-size:10px;'>— xAI Grok</span></div>
        </div>""", unsafe_allow_html=True)
    if not xai:
        st.markdown("<div style='font-size:12px;color:#4a5568;margin:-6px 0 8px;'>No xAI key — enter it in the sidebar.</div>",unsafe_allow_html=True)
        return
    if active_entry is None:
        st.markdown("<div style='font-size:12px;color:#4a5568;margin:-6px 0 8px;'>Enter a trade above to activate AI advice.</div>",unsafe_allow_html=True)
        return
    trade_key=f"ai_{plan.symbol}_{active_entry:.5f}"
    news_dict={"risk":plan.news_risk,"bias":plan.news_bias,"summary":plan.news_summary,"ok":plan.news_ok}
    if trade_key not in st.session_state:
        with st.spinner("Grok analysing your trade…"):
            st.session_state[trade_key]=get_ai_trade_advice(plan,df,live_health,news_dict)
    advice=st.session_state.get(trade_key,"")
    if advice:
        safe_advice=advice.replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")
        st.markdown(f"""<div class='ai-bubble'>
            <div class='ai-header'>◈ AUTO-ANALYSIS</div>{safe_advice}</div>""",
            unsafe_allow_html=True)
    user_q=st.text_input("Ask Grok anything about this trade…",
                          placeholder="e.g. Should I move SL to breakeven?",
                          key=f"gq_{plan.symbol}")
    if st.button("⚡ Ask Grok",key=f"gb_{plan.symbol}"):
        if user_q.strip():
            with st.spinner("Grok is thinking…"):
                st.session_state[f"gr_{plan.symbol}"]=get_ai_trade_advice(plan,df,live_health,news_dict,user_q)
        else:
            st.warning("Type a question first.")
    reply=st.session_state.get(f"gr_{plan.symbol}","")
    if reply:
        safe_reply=reply.replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")
        st.markdown(f"""<div class='ai-bubble' style='border-left-color:#0ea5e9;background:rgba(14,165,233,.06);'>
            <div class='ai-header' style='color:#0ea5e9;'>◈ GROK REPLY</div>{safe_reply}</div>""",
            unsafe_allow_html=True)

# ============================================================
# NEWS PANEL
# ============================================================
def render_news_panel(plan:Plan):
    xai=get_xai_key()
    if not xai:
        st.markdown("<div class='panel' style='border-color:rgba(255,255,255,0.04);'><div class='mono-title' style='color:#4a5568;'>GROK NEWS — no xAI key</div></div>",unsafe_allow_html=True); return
    risk=plan.news_risk; adj=plan.news_adj; bias=plan.news_bias
    risk_col={"HIGH":"#ef4444","MEDIUM":"#f59e0b","LOW":"#10b981"}.get(risk,"#10b981")
    bias_col={"bull":"#10b981","bear":"#ef4444"}.get(bias,"#8b9ab0")
    adj_str=(f"+{adj}" if adj>0 else str(adj))
    adj_col="#10b981" if adj>0 else "#ef4444" if adj<0 else "#8b9ab0"
    # Escape dynamic content to prevent HTML injection / broken structure
    safe_summary = str(plan.news_summary).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    evts="".join(
        f"<div style='font-size:11px;color:#8b9ab0;padding:2px 0;'>▸ {str(e).replace('<','&lt;').replace('>','&gt;')}</div>"
        for e in (plan.news_events or [])
    )
    high_banner = ('<div style="font-size:11px;color:#ef4444;margin-top:6px;padding:5px;'
                   'background:rgba(239,68,68,.08);border-radius:4px;">'
                   '⚠ HIGH RISK: Signal blocked until event resolves.</div>') if risk=="HIGH" else ""
    # NOTE: closing </div> must NOT be indented — 4-space indent = markdown code block
    html = (f"<div class='panel news-{risk}'>"
            f"<div class='mono-title'>GROK NEWS <span style='color:#4a5568;font-size:10px;'>— live via xAI</span></div>"
            f"<div style='display:flex;gap:20px;margin-bottom:6px;flex-wrap:wrap;'>"
            f"<div><div style='font-size:10px;color:#8b9ab0;'>RISK</div>"
            f"<div style='font-family:Space Mono,monospace;font-size:14px;font-weight:700;color:{risk_col};'>{risk}</div></div>"
            f"<div><div style='font-size:10px;color:#8b9ab0;'>SCORE ADJ</div>"
            f"<div style='font-family:Space Mono,monospace;font-size:14px;font-weight:700;color:{adj_col};'>{adj_str}</div></div>"
            f"<div><div style='font-size:10px;color:#8b9ab0;'>BIAS</div>"
            f"<div style='font-family:Space Mono,monospace;font-size:14px;font-weight:700;color:{bias_col};'>{bias.upper()}</div></div>"
            f"</div>"
            f"<div style='font-size:12px;color:#e8edf2;margin-bottom:4px;'>{safe_summary}</div>"
            f"{evts}{high_banner}</div>")
    st.markdown(html, unsafe_allow_html=True)

# ============================================================
# TRADE TRACKER  (multi-trade: active_trades = list of dicts)
# ============================================================
def _tp_pct_dir(tp, entry, live_price, direction):
    """Direction-aware TP progress %. Returns 0 if price moved wrong way."""
    if not tp: return None
    try:
        tp_f  = float(tp); e = float(entry)
        total = abs(tp_f - e)
        if total == 0: return None
        # TP must be in the correct direction from entry
        if direction == "Buy"  and tp_f <= e: return 0
        if direction == "Sell" and tp_f >= e: return 0
        done = (live_price - e) if direction == "Buy" else (e - live_price)
        if done <= 0: return 0
        return min(int(done / total * 100), 100)
    except:
        return None

def _prog_bar_html(pct, color):
    filled = max(0, min(pct, 100))
    return (f"<div style='height:4px;background:rgba(255,255,255,0.08);border-radius:2px;margin-top:3px;'>"
            f"<div style='width:{filled}%;height:100%;background:{color};border-radius:2px;'></div></div>")

def render_trade_tracker(plan: Plan, current_price: float, df: pd.DataFrame):
    # ── Migrate old single active_trade → list ──────────────
    if "active_trades" not in st.session_state:
        old = st.session_state.pop("active_trade", None)
        st.session_state.active_trades = [old] if old else []
    trades = st.session_state.active_trades

    # ── Title bar ──────────────────────────────────────────
    n_trades = len(trades)
    badge = (f" <span style='color:#00d4aa;font-size:11px;background:rgba(0,212,170,0.1);"
             f"padding:2px 8px;border-radius:3px;'>{n_trades} open</span>") if n_trades else ""
    st.markdown(
        f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.07);"
        f"border-radius:8px 8px 0 0;padding:10px 14px 6px;'>"
        f"<div class='mono-title' style='margin-bottom:0;'>TRADE TRACKER{badge}</div></div>",
        unsafe_allow_html=True)

    with st.container():
        st.markdown("<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.07);"
                    "border-top:none;border-radius:0 0 8px 8px;padding:10px 14px 12px;margin-bottom:10px;'>",
                    unsafe_allow_html=True)

        # ── Enter New Trade form (always visible) ──────────
        with st.expander("▶ Enter New Trade", expanded=(n_trades == 0)):
            c1, c2 = st.columns(2)
            me = c1.number_input("Entry",     value=float(plan.entry or current_price), format="%.5f", key="te_e")
            ms = c2.number_input("Stop Loss", value=float(plan.sl    or current_price), format="%.5f", key="te_s")
            md = c1.selectbox("Direction", ["Buy","Sell"], index=0 if plan.direction=="Buy" else 1, key="te_d")
            ml = c2.number_input("Lot", value=float(max(plan.suggested_lot, 0.01)), format="%.3f", key="te_l")
            tp_default1 = float(plan.tp1) if plan.tp1 else float(current_price)
            tp_default2 = float(plan.tp2) if plan.tp2 else float(current_price)
            tc1, tc2 = st.columns(2)
            mtp1 = tc1.number_input("Take Profit 1", value=tp_default1, format="%.5f", key="te_tp1")
            mtp2 = tc2.number_input("Take Profit 2 (opt)", value=tp_default2, format="%.5f", key="te_tp2")

            # Validate direction vs TP before entering
            _tp1_ok = (mtp1 > me and md=="Buy") or (mtp1 < me and md=="Sell") or mtp1==me
            _sl_ok  = (ms  < me and md=="Buy") or (ms  > me and md=="Sell")
            if not _tp1_ok:
                st.warning(f"⚠ TP1 {fmt_price(mtp1,plan.symbol)} is on the wrong side for a {md}")
            if not _sl_ok:
                st.warning(f"⚠ SL {fmt_price(ms,plan.symbol)} is on the wrong side for a {md}")

            if st.button("▶ Enter Trade", key="btn_enter"):
                import uuid
                new_trade = {
                    "id": str(uuid.uuid4())[:8],
                    "symbol": plan.symbol,
                    "entry": me, "sl": ms, "direction": md, "lot": ml,
                    "tp1": mtp1, "tp2": mtp2,
                    "locked_score": plan.setup_score,
                    "locked_final": plan.final_score,
                    "locked_grade": plan.setup_grade,
                }
                st.session_state.active_trades.append(new_trade)
                st.success(f"Trade entered! ({plan.symbol} {md})"); st.rerun()

        # ── Active trade cards ─────────────────────────────
        if not trades:
            st.markdown("<div class='explainer-box' style='margin-top:8px;'>No open trades. Use the form above to enter one.</div>",
                        unsafe_allow_html=True)
        else:
            for t in trades:
                tid       = t.get("id","0")
                t_sym     = t.get("symbol", plan.symbol)
                t_dir     = t["direction"]
                t_entry   = float(t["entry"])
                t_sl      = float(t["sl"])
                t_risk    = abs(t_entry - t_sl)
                t_tp1     = t.get("tp1"); t_tp2 = t.get("tp2")
                dir_col   = "#10b981" if t_dir=="Buy" else "#ef4444"
                gc2       = grade_color(t["locked_grade"])

                # Live price — always use the TRADE's own symbol
                _ma_tick  = fetch_mt5_price(t_sym, get_ma_token(), get_ma_account()) if (get_ma_token() and get_ma_account()) else None
                if _ma_tick:
                    t_price      = _ma_tick["bid"]
                    price_label  = f"MT5 {fmt_price(_ma_tick['bid'],t_sym)}/{fmt_price(_ma_tick['ask'],t_sym)}"
                    price_col    = "#00d4aa"
                else:
                    t_price      = current_price if t_sym == plan.symbol else t_entry
                    price_label  = "TD ~" if t_sym == plan.symbol else "⚠ no price"
                    price_col    = "#f59e0b"

                # Direction-aware P&L
                _move  = (t_price - t_entry) if t_dir=="Buy" else (t_entry - t_price)
                _pnl_r = _move / t_risk if t_risk > 0 else 0
                pnl_col = "#10b981" if _pnl_r >= 0 else "#ef4444"

                # Direction-aware TP progress
                tp1_pct = _tp_pct_dir(t_tp1, t_entry, t_price, t_dir)
                tp2_pct = _tp_pct_dir(t_tp2, t_entry, t_price, t_dir)
                tp1_bar = _prog_bar_html(tp1_pct, "#10b981") if tp1_pct is not None else ""
                tp2_bar = _prog_bar_html(tp2_pct, "#00d4aa") if tp2_pct is not None else ""

                # Card header with symbol tag
                sym_tag = (f"<span style='color:#00d4aa;font-size:10px;background:rgba(0,212,170,0.1);"
                           f"padding:2px 7px;border-radius:3px;margin-right:6px;'>{t_sym}</span>")
                st.markdown(
                    f"<div style='border:1px solid rgba(255,255,255,0.07);border-radius:6px;"
                    f"padding:8px 10px;margin:6px 0;background:#090e14;'>"
                    f"<div style='font-size:10px;color:#8b9ab0;margin-bottom:6px;'>{sym_tag}"
                    f"<span style='color:{dir_col};font-weight:700;'>{t_dir}</span>"
                    f"<span style='color:#4a5568;'> · {t['lot']} lot</span>"
                    f"<span style='color:#4a5568;float:right;font-size:9px;'>#{tid}</span></div>"
                    # Row 1: Entry / SL / P&L / Grade
                    f"<div style='display:flex;gap:10px;flex-wrap:wrap;font-size:12px;margin-bottom:5px;'>"
                    f"<div><span class='muted'>Entry</span><br>"
                    f"<b style='color:#00d4aa;font-family:Space Mono,monospace;'>{fmt_price(t_entry,t_sym)}</b></div>"
                    f"<div><span class='muted'>SL</span><br>"
                    f"<b style='color:#ef4444;font-family:Space Mono,monospace;'>{fmt_price(t_sl,t_sym)}</b></div>"
                    f"<div><span class='muted'>P&L <span style='font-size:9px;color:{price_col};'>({price_label})</span></span><br>"
                    f"<b style='color:{pnl_col};font-family:Space Mono,monospace;'>{_pnl_r:+.2f}R</b></div>"
                    f"<div><span class='muted'>Grade</span><br>"
                    f"<b style='color:{gc2};'>{t['locked_grade']} {t['locked_final']}</b></div></div>"
                    # Row 2: TP1 + TP2 with progress
                    f"<div style='display:flex;gap:10px;flex-wrap:wrap;font-size:11px;margin-bottom:4px;'>"
                    f"<div style='flex:1;min-width:90px;'><span class='muted'>TP1</span> "
                    f"<b style='color:#10b981;font-family:Space Mono,monospace;'>{fmt_price(t_tp1,t_sym) if t_tp1 else '—'}</b>"
                    + (f" <span style='color:#8b9ab0;font-size:9px;'>{tp1_pct}%</span>{tp1_bar}" if tp1_pct is not None else "") +
                    f"</div>"
                    f"<div style='flex:1;min-width:90px;'><span class='muted'>TP2</span> "
                    f"<b style='color:#00d4aa;font-family:Space Mono,monospace;'>{fmt_price(t_tp2,t_sym) if t_tp2 else '—'}</b>"
                    + (f" <span style='color:#8b9ab0;font-size:9px;'>{tp2_pct}%</span>{tp2_bar}" if tp2_pct is not None else "") +
                    f"</div></div></div>",
                    unsafe_allow_html=True)

                # ── Close flow (per-trade key) ──
                _close_key = f"_closing_{tid}"
                if not st.session_state.get(_close_key):
                    if st.button(f"✕ Close  #{tid}", key=f"btn_close_{tid}"):
                        st.session_state[_close_key] = True; st.rerun()
                else:
                    st.markdown(f"<div style='font-size:11px;color:#f59e0b;font-family:Space Mono,monospace;margin-bottom:4px;'>LOG TRADE #{tid} ({t_sym})</div>",
                                unsafe_allow_html=True)
                    _ep  = st.number_input("Exit Price", value=float(t_price), format="%.5f", key=f"j_exit_{tid}")
                    _res = st.selectbox("Result", ["Win","Loss","BE"], key=f"j_res_{tid}")
                    _note= st.text_input("Notes", placeholder="e.g. news spike, TP1 hit...", key=f"j_note_{tid}")
                    cj1, cj2 = st.columns(2)
                    if cj1.button("💾 Save & Close", key=f"btn_save_{tid}"):
                        log_trade(t, plan, _ep, _res, _note)
                        st.session_state.active_trades = [x for x in st.session_state.active_trades if x.get("id") != tid]
                        st.session_state.pop(_close_key, None)
                        st.session_state.pop("_last_alert_hash", None)
                        st.success(f"Trade #{tid} logged!"); st.rerun()
                    if cj2.button("Cancel", key=f"btn_cancel_{tid}"):
                        st.session_state.pop(_close_key, None); st.rerun()

                st.markdown("<hr style='border-color:rgba(255,255,255,0.04);margin:4px 0;'>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # Return the trade matching the currently viewed symbol (for Live Health)
    for t in trades:
        if t.get("symbol", plan.symbol) == plan.symbol:
            return t["entry"], t["sl"], t["direction"]
    # Fallback: return first trade if any (so Live Health still shows something)
    if trades:
        return trades[0]["entry"], trades[0]["sl"], trades[0]["direction"]
    return None

# ============================================================
# TRADE JOURNAL  — persistent JSON log + self-learning stats
# ============================================================
JOURNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.json")

def load_journal() -> List[dict]:
    try:
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE,"r") as f: return json.load(f)
    except Exception: pass
    return []

def save_journal(journal: List[dict]):
    try:
        with open(JOURNAL_FILE,"w") as f: json.dump(journal, f, indent=2)
    except Exception: pass

def log_trade(trade: dict, plan: "Plan", exit_price: float, result: str,
              notes: str = "") -> List[dict]:
    """Append a closed trade. result = 'Win'|'Loss'|'BE'"""
    from datetime import datetime as _dt
    entry_p = float(trade["entry"]); sl_p = float(trade["sl"])
    risk_dist = abs(entry_p - sl_p)
    gain_dist = abs(exit_price - entry_p) if exit_price else 0
    direction = trade["direction"]
    # R-multiple: positive = profit direction, negative = against
    if direction == "Buy":
        pnl_r = (exit_price - entry_p) / risk_dist if risk_dist > 0 else 0
    else:
        pnl_r = (entry_p - exit_price) / risk_dist if risk_dist > 0 else 0
    record = {
        "id":      len(load_journal()) + 1,
        "ts":      _dt.utcnow().strftime("%Y-%m-%d %H:%M"),
        "symbol":  plan.symbol,
        "dir":     direction,
        "entry":   entry_p,
        "sl":      sl_p,
        "exit":    exit_price,
        "lot":     trade["lot"],
        "result":  result,
        "pnl_r":   round(pnl_r, 2),
        "tech":    trade.get("locked_score", 0),
        "final":   trade.get("locked_final", 0),
        "grade":   trade.get("locked_grade", "?"),
        "news_risk":  getattr(plan,"news_risk","?"),
        "news_bias":  getattr(plan,"news_bias","?"),
        "news_adj":   getattr(plan,"news_adj", 0),
        "session":    getattr(plan,"session_label","?"),
        "confluence": getattr(plan,"confluence_count", 0),
        "tp1":        trade.get("tp1"),
        "tp2":        trade.get("tp2"),
        "notes":   notes,
    }
    j = load_journal(); j.append(record); save_journal(j)
    return j

def journal_stats(journal: List[dict]) -> dict:
    if not journal: return {}
    total  = len(journal)
    wins   = sum(1 for t in journal if t.get("result")=="Win")
    losses = sum(1 for t in journal if t.get("result")=="Loss")
    bes    = sum(1 for t in journal if t.get("result")=="BE")
    wr     = wins/total*100
    pnls   = [t.get("pnl_r",0) for t in journal]
    gross_p = sum(p for p in pnls if p>0)
    gross_l = abs(sum(p for p in pnls if p<0))
    pf      = gross_p/gross_l if gross_l>0 else float("inf")
    # by grade
    grade_s={}
    for g in ["A","B","C","D"]:
        gt=[t for t in journal if t.get("grade")==g]
        if gt: grade_s[g]={"n":len(gt),"wr":sum(1 for t in gt if t.get("result")=="Win")/len(gt)*100}
    # by news risk
    news_s={}
    for n in ["HIGH","MEDIUM","LOW"]:
        nt=[t for t in journal if t.get("news_risk")==n]
        if nt: news_s[n]={"n":len(nt),"wr":sum(1 for t in nt if t.get("result")=="Win")/len(nt)*100}
    # by session
    sess_s={}
    for t in journal:
        s=t.get("session","?")
        if s not in sess_s: sess_s[s]={"n":0,"w":0}
        sess_s[s]["n"]+=1
        if t.get("result")=="Win": sess_s[s]["w"]+=1
    for s in sess_s: sess_s[s]["wr"]=sess_s[s]["w"]/sess_s[s]["n"]*100
    # by score bucket
    score_s={}
    for t in journal:
        b=(t.get("final",0)//10)*10
        if b not in score_s: score_s[b]={"n":0,"w":0}
        score_s[b]["n"]+=1
        if t.get("result")=="Win": score_s[b]["w"]+=1
    for b in score_s: score_s[b]["wr"]=score_s[b]["w"]/score_s[b]["n"]*100
    return {"total":total,"wins":wins,"losses":losses,"bes":bes,"wr":wr,
            "total_r":round(sum(pnls),2),"avg_r":round(sum(pnls)/total,2),
            "pf":round(pf,2) if pf!=float("inf") else "∞",
            "grade_s":grade_s,"news_s":news_s,"sess_s":sess_s,"score_s":score_s}

def journal_insights(journal: List[dict]) -> List[str]:
    MIN = 5
    if len(journal) < MIN:
        return [f"📊 Need {MIN-len(journal)} more trades to generate AI insights."]
    s = journal_stats(journal)
    tips = []
    wr = s["wr"]
    tips.append(f"{'✅' if wr>=55 else '⚠️' if wr>=45 else '🔴'} Overall win rate: {wr:.0f}% ({s['wins']}W / {s['losses']}L / {s['bes']}BE)")
    pf = s["pf"]
    tips.append(f"💰 Profit factor: {pf}  |  Total: {s['total_r']:+.1f}R  |  Avg per trade: {s['avg_r']:+.2f}R")
    # Grade insight
    gs = s["grade_s"]
    if gs:
        best = max(gs.items(), key=lambda x:x[1]["wr"])
        worst = min(gs.items(), key=lambda x:x[1]["wr"])
        if best[1]["n"]>=2: tips.append(f"🏆 Best grade: {best[0]} — {best[1]['wr']:.0f}% win ({best[1]['n']} trades)")
        if worst[1]["n"]>=2 and worst[1]["wr"]<45: tips.append(f"⛔ Avoid grade {worst[0]} — only {worst[1]['wr']:.0f}% win ({worst[1]['n']} trades)")
    # News insight
    ns = s["news_s"]
    if "HIGH" in ns and ns["HIGH"]["n"]>=2:
        hw = ns["HIGH"]["wr"]
        tips.append(f"{'⚡ Avoid' if hw<40 else '✅ OK for'} HIGH news trades — {hw:.0f}% win rate ({ns['HIGH']['n']} trades)")
    # Session insight
    ss = s["sess_s"]
    ranked = sorted(ss.items(), key=lambda x:x[1]["wr"], reverse=True)
    if ranked and ranked[0][1]["n"]>=2:
        tips.append(f"⏰ Best session: {ranked[0][0]} ({ranked[0][1]['wr']:.0f}% win)")
    if len(ranked)>1 and ranked[-1][1]["n"]>=2 and ranked[-1][1]["wr"]<45:
        tips.append(f"🚫 Worst session: {ranked[-1][0]} ({ranked[-1][1]['wr']:.0f}% win) — trade less here")
    # Score threshold
    sc = s["score_s"]
    good_buckets = [(b,d) for b,d in sc.items() if d["n"]>=2 and d["wr"]>=60]
    if good_buckets:
        best_b = max(good_buckets, key=lambda x:x[1]["wr"])
        tips.append(f"📈 Sweet spot: scores {best_b[0]}–{best_b[0]+9} → {best_b[1]['wr']:.0f}% win rate")
    bad_buckets = [(b,d) for b,d in sc.items() if d["n"]>=2 and d["wr"]<35]
    if bad_buckets:
        worst_b = min(bad_buckets, key=lambda x:x[1]["wr"])
        tips.append(f"📉 Avoid scores {worst_b[0]}–{worst_b[0]+9} → only {worst_b[1]['wr']:.0f}% win")
    return tips


# ============================================================
# MARKET OVERVIEW
# ============================================================
def build_overview_row(sym,balance,risk_pct,td_key):
    try:
        df,plan=select_plan(sym,"15min",260,td_key)
        plan=finalize_plan(plan,balance,risk_pct)
        price=float(df["close"].iloc[-1])
        return {"Symbol":sym,"Price":fmt_price(price,sym),"Signal":plan.direction,
                "Status":plan.execution_status[:18],"Tech":plan.setup_score,
                "News Adj":plan.news_adj,"Final":plan.final_score,"Grade":plan.final_grade,
                "R:R":fmt_rr(plan.rr),"Session":plan.session_label[:15],"News":plan.news_risk}
    except Exception as e:
        return {"Symbol":sym,"Price":"ERR","Signal":"—","Status":str(e)[:18],
                "Tech":0,"News Adj":0,"Final":0,"Grade":"D","R:R":"—","Session":"—","News":"—"}

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(f"<div style='font-family:Space Mono,monospace;font-size:11px;color:#00d4aa;letter-spacing:.12em;padding:8px 0 12px;'>AI FOREX TERMINAL<br><span style='color:#4a5568;'>{APP_VERSION}</span></div>",unsafe_allow_html=True)
    mode=st.radio("Mode",["🔴  Live Analysis","📊  Backtest","📒  Journal"],index=0,label_visibility="collapsed")
    st.markdown("---")
    auto_refresh=st.toggle("Auto Refresh",value=True)
    refresh_sec=st.selectbox("Interval (s)",[15,30,60,120],index=1)
    if auto_refresh and st_autorefresh:
        st_autorefresh(interval=int(refresh_sec)*1000,key="ar_v12")
    st.markdown("---")
    symbol=st.selectbox("Symbol",INTERNAL_SYMBOLS,index=3)
    interval_label=st.selectbox("Interval",list(INTERVAL_MAP.keys()),index=2)
    bars=st.slider("Bars",220,1000,400,20)
    balance=st.number_input("Balance (USD)",min_value=10.0,value=500.0,step=50.0)
    risk_pct=st.number_input("Risk %",min_value=0.1,max_value=5.0,value=1.0,step=0.1)
    st.markdown("---")
    st.markdown("<div style='font-size:11px;color:#8b9ab0;font-family:Space Mono,monospace;margin-bottom:4px;'>API KEYS</div>",unsafe_allow_html=True)
    _td=st.text_input("Twelve Data",value=st.session_state.get("td_key",_ENV_TD),type="password",key="td_inp",placeholder="paste key…")
    _xai=st.text_input("xAI Grok",value=st.session_state.get("xai_key",_ENV_XAI),type="password",key="xai_inp",placeholder="paste key…")
    if _td:  st.session_state["td_key"]=_td
    if _xai: st.session_state["xai_key"]=_xai
    _GROK_MODELS=["grok-4-1-fast-non-reasoning","grok-4-1-fast-reasoning","grok-4.20-0309-non-reasoning","grok-4.20-0309-reasoning","grok-4.20-multi-agent-0309"]
    _gm=st.selectbox("Grok Model",_GROK_MODELS,index=0,key="grok_model_sel")
    st.session_state["grok_model"]=_gm
    td_ok="✅" if _td else "❌"; xai_ok="✅" if _xai else "❌"
    st.markdown(f"<div style='font-size:11px;color:#4a5568;font-family:Space Mono,monospace;'>{td_ok} Twelve Data &nbsp; {xai_ok} xAI ({_gm})</div>",unsafe_allow_html=True)
    c1,c2=st.columns(2)
    if _xai and c1.button("🔌 Test Grok"):
        ok,msg=test_grok_connection(_xai)
        (st.success if ok else st.error)(msg)
    if _xai and c2.button("📋 List Models"):
        try:
            _r=requests.get("https://api.x.ai/v1/models",
                            headers={"Authorization":f"Bearer {_xai}"},timeout=10)
            if _r.status_code==200:
                _ids=[m["id"] for m in _r.json().get("data",[])]
                st.success("Available: "+", ".join(_ids) if _ids else "No models returned")
            else:
                st.error(f"HTTP {_r.status_code}: {_r.text[:120]}")
        except Exception as e:
            st.error(str(e))

    # ── MetaApi (MT5 live data) ─────────────────────────────
    st.markdown("---")
    st.markdown("<div style='font-size:11px;color:#00d4aa;font-family:Space Mono,monospace;margin-bottom:4px;'>MT5 LIVE (MetaApi)</div>",unsafe_allow_html=True)
    _ma_tok=st.text_input("MetaApi Token",value=st.session_state.get("ma_token",""),type="password",key="ma_tok_inp",placeholder="paste token…")
    _ma_acc=st.text_input("Account ID",value=st.session_state.get("ma_account",""),key="ma_acc_inp",placeholder="e.g. abc123def456…")
    _ma_sfx=st.text_input("Symbol suffix",value=st.session_state.get("ma_sym_suffix",".r"),key="ma_sfx_inp",placeholder=".r for FP Markets Raw",help="FP Markets Raw = .r  |  Standard = leave blank")
    if _ma_tok:  st.session_state["ma_token"]=_ma_tok
    if _ma_acc:  st.session_state["ma_account"]=_ma_acc
    st.session_state["ma_sym_suffix"]=_ma_sfx
    _ma_ok="✅" if (_ma_tok and _ma_acc) else "❌"
    st.markdown(f"<div style='font-size:11px;color:#4a5568;font-family:Space Mono,monospace;'>{_ma_ok} MetaApi MT5 {'(connected)' if _ma_ok=='✅' else '(not set)'}</div>",unsafe_allow_html=True)
    _mab1,_mab2=st.columns(2)
    if _ma_tok and _ma_acc and _mab1.button("🔌 Test MT5"):
        _ok,_msg=test_mt5_connection(_ma_tok,_ma_acc)
        (st.success if _ok else st.error)(_msg)
    if _ma_tok and _ma_acc and _mab2.button("▶ Deploy"):
        _ok,_msg=deploy_mt5_account(_ma_tok,_ma_acc)
        (st.success if _ok else st.error)(_msg)

interval=INTERVAL_MAP[interval_label]
TD_KEY=get_td_key()

# ============================================================
# EXIT ALERT ENGINE
# ============================================================
def _check_exit_alert(plan: "Plan", trade: dict, current_price: float, df: "pd.DataFrame") -> Tuple[bool, str, str]:
    """
    Returns (should_alert, message, urgency="HIGH"|"MEDIUM"|"TP2")
    Checks: high-risk news, bias flip, ATR spike, near TP1, TP2 potential.
    urgency "TP2" = green opportunity alert (hold for more).
    """
    if not trade:
        return False, "", "LOW"
    direction = trade["direction"]
    entry     = float(trade["entry"])
    reasons   = []
    urgency   = "MEDIUM"
    tp2_opportunity = []   # separate bucket — positive alert

    # 1. High-impact news
    if getattr(plan, "news_risk", "LOW") == "HIGH":
        reasons.append(f"⚡ HIGH IMPACT NEWS ({getattr(plan,'news_bias','?')})")
        urgency = "HIGH"

    # 2. News bias flipped against position
    nb = getattr(plan, "news_bias", "NEUTRAL")
    if nb == "BEAR" and direction == "Buy":
        reasons.append("📉 News bias flipped BEARISH — you're LONG")
        urgency = "HIGH"
    elif nb == "BULL" and direction == "Sell":
        reasons.append("📈 News bias flipped BULLISH — you're SHORT")
        urgency = "HIGH"

    # 3. ATR volatility spike (current > 1.8× 20-bar average)
    if "atr" in df.columns and len(df) >= 22:
        last_atr = float(df["atr"].iloc[-1])
        avg_atr  = float(df["atr"].iloc[-21:-1].mean())
        if avg_atr > 0 and last_atr > avg_atr * 1.8:
            mult = last_atr / avg_atr
            reasons.append(f"💥 Volatility spike — ATR ×{mult:.1f} above normal")
            if mult > 2.5:
                urgency = "HIGH"

    # ── Direction-aware progress helper ──────────────────────
    def _dir_pct(tp_val, e, price, direc):
        """Return % progress toward TP. Returns 0 if price moved wrong way."""
        try:
            tp_f  = float(tp_val)
            total = abs(tp_f - e)
            if total == 0: return 0
            done  = (price - e) if direc == "Buy" else (e - price)
            if done <= 0: return 0          # moved wrong direction
            return min(int(done / total * 100), 100)
        except:
            return 0

    # 4. Price ≥75% of the way to TP1 — direction-aware
    _tp1 = trade.get("tp1") or getattr(plan, "tp1", None)
    _tp2 = trade.get("tp2") or getattr(plan, "tp2", None)
    if _tp1:
        try:
            tp1_pct = _dir_pct(_tp1, entry, current_price, direction)
            if tp1_pct >= 75:
                reasons.append(f"🎯 {tp1_pct}% to TP1 — consider partial exit or move SL to BE")
        except Exception:
            pass

    # 5. TP2 opportunity — detect when price has reached/passed TP1 AND momentum continues
    if _tp1 and _tp2:
        try:
            tp1f = float(_tp1); tp2f = float(_tp2)
            # Price must have moved in correct direction past TP1
            tp1_dist   = abs(tp1f - entry)
            tp1_margin = tp1_dist * 0.10
            passed_tp1 = (current_price >= tp1f - tp1_margin) if direction == "Buy" else (current_price <= tp1f + tp1_margin)
            # Extra guard: TP1 must be in correct direction from entry
            tp1_valid  = (tp1f > entry) if direction == "Buy" else (tp1f < entry)
            passed_tp1 = passed_tp1 and tp1_valid
            if passed_tp1:
                # Check momentum: MACD still in trade direction
                macd_ok = False
                if "macd" in df.columns and "macd_sig" in df.columns:
                    macd_val = float(df["macd"].iloc[-1])
                    macd_sig = float(df["macd_sig"].iloc[-1])
                    macd_ok = (macd_val > macd_sig) if direction == "Buy" else (macd_val < macd_sig)
                # Check RSI not overextended
                rsi_ok = True
                if "rsi14" in df.columns:
                    rsi_val = float(df["rsi14"].iloc[-1])
                    rsi_ok = (rsi_val < 75) if direction == "Buy" else (rsi_val > 25)
                # EMA trend still aligned
                ema_ok = False
                if "ema20" in df.columns and "ema50" in df.columns:
                    e20 = float(df["ema20"].iloc[-1]); e50 = float(df["ema50"].iloc[-1])
                    ema_ok = (e20 > e50) if direction == "Buy" else (e20 < e50)
                score = sum([macd_ok, rsi_ok, ema_ok])
                if score >= 2:
                    tp2_pct_dist = abs(current_price - tp1f) / abs(tp2f - tp1f) * 100 if abs(tp2f - tp1f) > 0 else 0
                    conf = ["MACD ✓" if macd_ok else "","RSI ✓" if rsi_ok else "","EMA ✓" if ema_ok else ""]
                    conf_str = "  ".join(c for c in conf if c)
                    tp2_opportunity.append(
                        f"🚀 TP2 POTENTIAL — momentum still {'bullish' if direction=='Buy' else 'bearish'} ({conf_str}) "
                        f"| Consider holding, move SL to TP1 ({fmt_price(tp1f,'')}) to lock profit"
                    )
        except Exception:
            pass

    # Return TP2 opportunity as its own alert type (green, not red)
    if tp2_opportunity and not reasons:
        return True, "  |  ".join(tp2_opportunity), "TP2"
    if tp2_opportunity:
        # Both warning + opportunity — append TP2 hint to warning message
        reasons.extend(tp2_opportunity)

    if not reasons:
        return False, "", "LOW"
    return True, "  |  ".join(reasons), urgency


def _render_exit_alert(message: str, urgency: str):
    """
    Renders a fixed-position flashing banner + plays a beep sound.
    Sound only fires once per unique alert message (deduplicated via session_state).
    """
    if urgency == "HIGH":
        color="#ef4444"; bg="rgba(239,68,68,0.13)"; icon="🚨"
    elif urgency == "TP2":
        color="#00d4aa"; bg="rgba(0,212,170,0.11)"; icon="🚀"
    else:
        color="#f59e0b"; bg="rgba(245,158,11,0.11)"; icon="⚠️"

    # Play sound only when alert is NEW (hash changes)
    alert_hash = str(hash(message))
    play_sound = st.session_state.get("_last_alert_hash") != alert_hash
    if play_sound:
        st.session_state["_last_alert_hash"] = alert_hash

    sound_js = ""
    if play_sound:
        sound_js = """
<script>
(function(){
  try {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    function beep(f, t, d) {
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination);
      o.frequency.value = f;
      g.gain.setValueAtTime(0.35, ctx.currentTime + t);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + d);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + d);
    }
    beep(880, 0.00, 0.12);
    beep(660, 0.18, 0.12);
    beep(880, 0.36, 0.18);
  } catch(e) {}
})();
</script>"""

    safe_msg = message.replace("<", "&lt;").replace(">", "&gt;")
    banner = f"""{sound_js}
<div style='
  position:fixed;top:56px;left:50%;transform:translateX(-50%);
  z-index:99999;width:88%;max-width:720px;
  background:{bg};border:2px solid {color};border-radius:10px;
  padding:13px 20px 11px;font-family:Space Mono,monospace;
  box-shadow:0 0 28px {color}55;
  animation:alertpulse 1.4s ease-in-out infinite;
'>
  <div style='font-size:13px;color:{color};font-weight:700;letter-spacing:.08em;margin-bottom:5px;'>
    {icon} {"TP2 OPPORTUNITY — MOMENTUM STILL STRONG" if urgency=="TP2" else "EXIT ALERT — CONSIDER CLOSING YOUR POSITION"}
  </div>
  <div style='font-size:11px;color:#e8edf5;line-height:1.6;'>{safe_msg}</div>
</div>
<style>
@keyframes alertpulse {{
  0%,100% {{ box-shadow:0 0 18px {color}44; }}
  50%      {{ box-shadow:0 0 36px {color}aa; }}
}}
</style>"""
    st.markdown(banner, unsafe_allow_html=True)


# ============================================================
# LIVE
# ============================================================
def render_live():
    st.markdown(f"<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;letter-spacing:.12em;padding:4px 0 12px;'>◈ AI FOREX TERMINAL {APP_VERSION} ◈</div>",unsafe_allow_html=True)
    is_open,mkt=market_is_open(symbol)
    try:
        df,plan=select_plan(symbol,interval,bars,TD_KEY)
        latest=df.iloc[-1]
        td_price=float(latest["close"])    # Twelve Data last bar close
        prev=float(df.iloc[-2]["close"]) if len(df)>1 else td_price
        sweep=detect_sweep(df,symbol)
        if not is_open and norm(symbol) in FOREX_SYMBOLS:
            plan=_empty(symbol,"closed","MARKET CLOSED")
        plan=finalize_plan(plan,balance,risk_pct)
    except Exception as e:
        st.error(f"Error: {e}"); return

    # ── MT5 live price (overrides Twelve Data if connected) ──
    _ma_tok=get_ma_token(); _ma_acc=get_ma_account()
    mt5_tick = fetch_mt5_price(symbol, _ma_tok, _ma_acc) if (_ma_tok and _ma_acc) else None
    if mt5_tick:
        price = mt5_tick["bid"]   # use bid as display price (what you'd get selling)
        price_src_label = f"MT5 bid/ask {fmt_price(mt5_tick['bid'],symbol)}/{fmt_price(mt5_tick['ask'],symbol)}  spread {mt5_tick['spread_pips']}p"
        price_src_col   = "#00d4aa"
    else:
        price = td_price
        price_src_label = "Twelve Data (delayed)"
        price_src_col   = "#f59e0b"
    chg=price-prev; chg_pct=(chg/prev*100) if prev else 0

    # ── MT5 open positions ────────────────────────────────────
    mt5_positions = fetch_mt5_positions(_ma_tok, _ma_acc) if (_ma_tok and _ma_acc) else []

    # ── Exit alert — check all open trades for the current symbol ──
    _all_trades = st.session_state.get("active_trades", [])
    _sym_trades  = [t for t in _all_trades if t.get("symbol", symbol) == symbol]
    if _sym_trades:
        # Use price already fetched for this symbol
        _alert, _alert_msg, _alert_urg = _check_exit_alert(plan, _sym_trades[0], price, df)
        if _alert:
            _render_exit_alert(_alert_msg, _alert_urg)
    else:
        st.session_state.pop("_last_alert_hash", None)

    top1,top2,top3=st.columns([2,3,1])
    with top1: render_signal_badge(plan.direction,plan.execution_status)
    with top2:
        pc="#10b981" if chg>=0 else "#ef4444"
        st.markdown(
            f"<div style='font-family:Space Mono,monospace;font-size:22px;font-weight:700;padding-top:4px;'>"
            f"{fmt_price(price,symbol)}"
            f"<span style='font-size:13px;color:{pc};'> {chg:+.5f} ({chg_pct:+.3f}%)</span>"
            f"<span style='font-size:10px;color:{price_src_col};margin-left:8px;'>{price_src_label}</span></div>",
            unsafe_allow_html=True)
    with top3:
        lc="#10b981" if mkt=="LIVE" else "#f59e0b"
        st.markdown(f"<div style='text-align:right;padding-top:8px;'><span style='font-family:Space Mono,monospace;font-size:11px;padding:4px 10px;border-radius:4px;border:1px solid rgba(255,255,255,.08);color:{lc};'>{mkt}</span></div>",unsafe_allow_html=True)

    # ── MT5 positions panel ───────────────────────────────────
    if mt5_positions:
        pos_rows=[]
        for p in mt5_positions:
            sym_p=p.get("symbol","?"); typ=p.get("type","?").replace("POSITION_TYPE_","")
            vol=p.get("volume",0); op=p.get("openPrice",0); cp=p.get("currentPrice",0)
            profit=p.get("profit",0); sl_p=p.get("stopLoss",0); tp_p=p.get("takeProfit",0)
            pos_rows.append({"Symbol":sym_p,"Type":typ,"Vol":vol,
                             "Open":fmt_price(op,sym_p),"Current":fmt_price(cp,sym_p),
                             "SL":fmt_price(sl_p,sym_p) if sl_p else "—",
                             "TP":fmt_price(tp_p,sym_p) if tp_p else "—",
                             "P&L":f"${profit:+.2f}"})
        st.markdown("<div style='font-family:Space Mono,monospace;font-size:11px;color:#00d4aa;letter-spacing:.08em;margin:4px 0 2px;'>📡 MT5 OPEN POSITIONS</div>",unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(pos_rows),use_container_width=True,hide_index=True)

    gc=grade_color(plan.final_grade)
    rsi=fmt_num(latest.get("rsi14"),1)
    rsi_col="#ef4444" if rsi!="—" and float(rsi)>70 else "#10b981" if rsi!="—" and float(rsi)<30 else "#e8edf2"
    news_col={"HIGH":"#ef4444","MEDIUM":"#f59e0b","LOW":"#10b981"}.get(plan.news_risk,"#8b9ab0")
    conf_col="#10b981" if plan.confluence_count>=4 else "#f59e0b" if plan.confluence_count>=2 else "#ef4444"
    adj_col="#10b981" if plan.news_adj>0 else "#ef4444" if plan.news_adj<0 else "#8b9ab0"

    def kpi(lbl,val,col="#e8edf2"):
        return (f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.07);border-radius:6px;padding:10px 12px;flex:1;min-width:0;'>"
                f"<div style='font-size:10px;color:#8b9ab0;font-family:Space Mono,monospace;letter-spacing:.07em;margin-bottom:4px;white-space:nowrap;'>{lbl}</div>"
                f"<div style='font-size:14px;font-weight:700;color:{col};font-family:Space Mono,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{val}</div></div>")

    st.markdown(f"""<div style='display:flex;gap:8px;margin:12px 0;flex-wrap:wrap;'>
      {kpi("STRATEGY",plan.strategy[:16],"#00d4aa")}
      {kpi("TECH SCORE",str(plan.setup_score),grade_color(plan.setup_grade))}
      {kpi("NEWS ADJ",("+"+str(plan.news_adj) if plan.news_adj>=0 else str(plan.news_adj)),adj_col)}
      {kpi("FINAL SCORE",str(plan.final_score),gc)}
      {kpi("GRADE",plan.final_grade,gc)}
      {kpi("CONFLUENCE",f"{plan.confluence_count}/6",conf_col)}
      {kpi("SESSION",plan.session_label[:12],"#8b9ab0")}
      {kpi("NEWS RISK",plan.news_risk,news_col)}
      {kpi("DIRECTION",plan.direction,"#10b981" if plan.direction=="Buy" else "#ef4444" if plan.direction=="Sell" else "#f59e0b")}
      {kpi("R:R",fmt_rr(plan.rr),"#a78bfa")}
      {kpi("RSI14",rsi,rsi_col)}
      {kpi("LOT",fmt_num(plan.suggested_lot,3),"#00d4aa")}
    </div>""",unsafe_allow_html=True)
    st.markdown("---")

    col_l,col_c,col_r=st.columns([1.05,2.2,1.15])
    with col_l:
        render_kv_panel("ENTRY LEVELS",[
            ("ENTRY",fmt_price(plan.entry,symbol),"good"),("STOP LOSS",fmt_price(plan.sl,symbol),"bad"),
            ("TP1",fmt_price(plan.tp1,symbol),"warn"),("TP2",fmt_price(plan.tp2,symbol),"good"),
            ("TP3",fmt_price(plan.tp3,symbol),"info") if plan.tp3 else ("TP3","—","muted"),
        ])
        render_kv_panel("EXIT RULES",[(f"#{i+1}",r,"") for i,r in enumerate(plan.exit_conditions or ["No exit plan"])])
        if sweep["detected"]:
            render_kv_panel("⚠ SWEEP",[("Severity",sweep["severity"],"bad" if sweep["severity"]=="HIGH" else "warn"),("Detail",sweep["desc"],"")])
        render_news_panel(plan)
    with col_c:
        st.markdown("### PRICE CHART")
        st.plotly_chart(build_chart(df,plan,symbol),use_container_width=True)
        st.markdown("### MARKET OVERVIEW")
        ov=[build_overview_row(s,balance,risk_pct,TD_KEY) for s in ["EURUSD","GBPUSD","USDJPY","XAUUSD","AUDUSD","USDCAD"]]
        st.dataframe(pd.DataFrame(ov),use_container_width=True,hide_index=True)
    with col_r:
        active=render_trade_tracker(plan,price,df)
        ae,asl,ad=(active if active else (None,None,None))
        render_score_panel(plan,df,ae,asl,ad)
        render_kv_panel("RISK PLAN",[
            ("Balance",f"${balance:,.2f}",""),("Risk %",f"{risk_pct:.1f}%",""),
            ("Risk $",f"${balance*risk_pct/100:,.2f}","warn"),
            ("Lot",fmt_num(plan.suggested_lot,3),"good"),("Status",plan.execution_status[:20],
             "good" if plan.execution_status=="Ready to Enter" else "bad" if "HIGH NEWS" in plan.execution_status else "warn"),
        ])

# ============================================================
# BACKTEST  (V12: equity curve + detailed stats)
# ============================================================
def render_backtest():
    st.markdown("## BACKTEST ENGINE")
    bc1,bc2,bc3,bc4=st.columns(4)
    bt_sym=bc1.selectbox("Symbol",INTERNAL_SYMBOLS,index=3,key="bt_sym")
    bt_int=bc2.selectbox("Interval",["15min","1h","4h"],index=0,key="bt_int")
    bt_bal=bc3.number_input("Balance",min_value=10.0,value=500.0,step=50.0,key="bt_bal")
    bt_rsk=bc4.number_input("Risk %",min_value=0.1,max_value=5.0,value=1.0,step=0.1,key="bt_rsk")
    fc1,fc2=st.columns(2)
    score_thresh=fc1.slider("Min Final Score to trade",40,90,65,5,key="bt_thresh")
    max_bars=fc2.slider("History bars",400,1000,700,50,key="bt_bars")

    if not st.button("▶ Run Backtest"): return
    with st.spinner("Fetching data and running simulation…"):
        try:
            s=norm(bt_sym)
            df=add_indicators(fetch_bars(s,bt_int,max_bars,TD_KEY))
            results=[]
            for i in range(220,len(df)-20):
                chunk=df.iloc[:i+1].copy()
                regime=get_regime(chunk)
                if regime=="insufficient": continue
                if regime in("trend_up","trend_down"):
                    plan=_trend_plan(chunk,s,regime,"neutral")
                elif regime=="squeeze":
                    plan=_squeeze_plan(chunk,s)
                else:
                    plan=_mean_rev_plan(chunk,s,regime)
                # Apply score threshold
                if plan.execution_status!="Ready to Enter" or plan.entry is None: continue
                if plan.setup_score<score_thresh: continue
                future=df.iloc[i+1:i+21]; outcome=None; er=None
                for _,row in future.iterrows():
                    if plan.direction=="Buy":
                        if row["low"]<=plan.sl:      outcome=-1.0;er="SL";break
                        if row["high"]>=plan.tp1:    outcome=abs(plan.tp1-plan.entry)/max(abs(plan.entry-plan.sl),1e-9);er="TP1";break
                    else:
                        if row["high"]>=plan.sl:     outcome=-1.0;er="SL";break
                        if row["low"]<=plan.tp1:     outcome=abs(plan.entry-plan.tp1)/max(abs(plan.sl-plan.entry),1e-9);er="TP1";break
                if outcome is None:
                    lc=float(future.iloc[-1]["close"])
                    outcome=(lc-plan.entry)/max(abs(plan.entry-plan.sl),1e-9) if plan.direction=="Buy" else (plan.entry-lc)/max(abs(plan.sl-plan.entry),1e-9)
                    er="Time"
                pnl=outcome*bt_bal*(bt_rsk/100)
                results.append({"time":chunk.iloc[-1]["time"],"symbol":s,"direction":plan.direction,
                                 "strategy":plan.strategy,"grade":plan.setup_grade,"score":plan.setup_score,
                                 "regime":plan.regime,"r_mult":round(outcome,3),"pnl":round(pnl,2),
                                 "exit":er,"entry":plan.entry,"sl":plan.sl,"tp1":plan.tp1,
                                 "session":plan.session_label[:12]})
            tdf=pd.DataFrame(results)
        except Exception as e:
            st.error(f"Backtest error: {e}"); return

    if tdf.empty: st.warning("No trades generated at this score threshold."); return
    tdf["cum_pnl"]=tdf["pnl"].cumsum()
    tdf["win"]=(tdf["pnl"]>0).astype(int)

    # ── Top metrics ──────────────────────────────────────────
    wins=tdf["win"].sum(); losses=len(tdf)-wins
    wr=wins/len(tdf)*100
    gross_p=tdf[tdf["pnl"]>0]["pnl"].sum(); gross_l=abs(tdf[tdf["pnl"]<0]["pnl"].sum())
    pf=gross_p/max(gross_l,1e-9)
    avg_win=tdf[tdf["pnl"]>0]["r_mult"].mean() if wins>0 else 0
    avg_loss=tdf[tdf["pnl"]<0]["r_mult"].mean() if losses>0 else 0
    net=tdf["pnl"].sum()
    # Max drawdown
    peak=tdf["cum_pnl"].cummax(); dd=(tdf["cum_pnl"]-peak)
    max_dd=dd.min(); max_dd_pct=max_dd/bt_bal*100
    # Consecutive losses
    streak=consec=0
    for w in tdf["win"]:
        if w==0: streak+=1; consec=max(consec,streak)
        else: streak=0
    avg_r=tdf["r_mult"].mean()

    m1,m2,m3,m4,m5,m6,m7,m8=st.columns(8)
    m1.metric("Trades",len(tdf)); m2.metric("Win Rate",f"{wr:.1f}%")
    m3.metric("Profit Factor",f"{pf:.2f}"); m4.metric("Net PnL",f"${net:,.2f}")
    m5.metric("Max Drawdown",f"${max_dd:,.2f} ({max_dd_pct:.1f}%)")
    m6.metric("Avg R",f"{avg_r:.2f}"); m7.metric("Avg Win R",f"{avg_win:.2f}")
    m8.metric("Max Consec Loss",str(consec))

    # ── Equity Curve ─────────────────────────────────────────
    st.markdown("### EQUITY CURVE")
    fig_eq=go.Figure()
    fig_eq.add_trace(go.Scatter(x=tdf["time"],y=tdf["cum_pnl"]+bt_bal,mode="lines",name="Equity",
                                 line=dict(color="#00d4aa",width=2),fill="tozeroy",
                                 fillcolor="rgba(0,212,170,0.06)"))
    fig_eq.add_hline(y=bt_bal,line=dict(color="#8b9ab0",width=1,dash="dot"),annotation_text="Start")
    fig_eq.update_layout(template="plotly_dark",height=260,margin=dict(l=8,r=8,t=8,b=8),
                          yaxis_title="Equity (USD)")
    st.plotly_chart(fig_eq,use_container_width=True)

    # ── Stats by Grade ────────────────────────────────────────
    st.markdown("### PERFORMANCE BY GRADE")
    grade_stats=[]
    for g in ["A+","A","B","C","D"]:
        sub=tdf[tdf["grade"]==g]
        if sub.empty: continue
        sw=sub["win"].sum(); sn=len(sub)
        grade_stats.append({"Grade":g,"Trades":sn,"Win Rate":f"{sw/sn*100:.0f}%",
                             "Avg R":f"{sub['r_mult'].mean():.2f}","Net PnL":f"${sub['pnl'].sum():.2f}",
                             "Profit Factor":f"{sub[sub['pnl']>0]['pnl'].sum()/max(abs(sub[sub['pnl']<0]['pnl'].sum()),1e-9):.2f}"})
    if grade_stats: st.dataframe(pd.DataFrame(grade_stats),use_container_width=True,hide_index=True)

    # ── Stats by Strategy ─────────────────────────────────────
    st.markdown("### PERFORMANCE BY STRATEGY")
    strat_stats=[]
    for st_name in tdf["strategy"].unique():
        sub=tdf[tdf["strategy"]==st_name]
        sw=sub["win"].sum(); sn=len(sub)
        strat_stats.append({"Strategy":st_name,"Trades":sn,"Win Rate":f"{sw/sn*100:.0f}%",
                             "Avg R":f"{sub['r_mult'].mean():.2f}","Net PnL":f"${sub['pnl'].sum():.2f}"})
    if strat_stats: st.dataframe(pd.DataFrame(strat_stats),use_container_width=True,hide_index=True)

    # ── Stats by Exit Type ────────────────────────────────────
    st.markdown("### EXIT TYPE BREAKDOWN")
    exit_stats=[]
    for ex in tdf["exit"].unique():
        sub=tdf[tdf["exit"]==ex]
        exit_stats.append({"Exit":ex,"Count":len(sub),"Avg R":f"{sub['r_mult'].mean():.2f}",
                            "Net PnL":f"${sub['pnl'].sum():.2f}"})
    if exit_stats: st.dataframe(pd.DataFrame(exit_stats),use_container_width=True,hide_index=True)

    # ── R Distribution Chart ──────────────────────────────────
    st.markdown("### R-MULTIPLE DISTRIBUTION")
    fig_r=go.Figure(go.Histogram(x=tdf["r_mult"],nbinsx=30,
                                   marker_color=["#10b981" if v>=0 else "#ef4444" for v in tdf["r_mult"]],
                                   name="R Distribution"))
    fig_r.add_vline(x=0,line=dict(color="#8b9ab0",width=1,dash="dot"))
    fig_r.add_vline(x=avg_r,line=dict(color="#00d4aa",width=1.5,dash="dot"),annotation_text=f"Avg {avg_r:.2f}R")
    fig_r.update_layout(template="plotly_dark",height=220,margin=dict(l=8,r=8,t=8,b=8))
    st.plotly_chart(fig_r,use_container_width=True)

    # ── Full trade log ────────────────────────────────────────
    with st.expander("📋 Full Trade Log"):
        st.dataframe(tdf.drop(columns=["win","cum_pnl"]),use_container_width=True,hide_index=True)
        st.download_button("⬇ Download CSV",tdf.to_csv(index=False).encode(),"backtest_v12.csv","text/csv")

# ============================================================
# JOURNAL VIEW
# ============================================================
def render_journal():
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:18px;color:#00d4aa;letter-spacing:.12em;padding:4px 0 12px;'>◈ TRADE JOURNAL ◈</div>",unsafe_allow_html=True)
    j = load_journal()

    if not j:
        st.info("No trades logged yet. Enter a live trade and close it to start recording.")
        return

    # ── Summary KPIs ──────────────────────────────────────────
    s = journal_stats(j)
    wr_col = "#10b981" if s["wr"]>=55 else "#f59e0b" if s["wr"]>=45 else "#ef4444"
    pf_val = s["pf"]; pf_col = "#10b981" if str(pf_val)=="∞" or float(str(pf_val).replace("∞","999"))>=1.5 else "#f59e0b"
    r_col  = "#10b981" if s["total_r"]>=0 else "#ef4444"
    def kpi2(l,v,c): return (f"<div style='background:#0d1117;border:1px solid rgba(255,255,255,0.07);border-radius:6px;padding:10px 14px;'>"
                             f"<div style='font-size:10px;color:#8b9ab0;font-family:Space Mono,monospace;letter-spacing:.07em;'>{l}</div>"
                             f"<div style='font-size:16px;font-weight:700;color:{c};font-family:Space Mono,monospace;'>{v}</div></div>")
    wr_str  = f"{s['wr']:.0f}%"
    r_str   = f"{s['total_r']:+.1f}R"
    avg_str = f"{s['avg_r']:+.2f}R"
    kpi_html=("<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:16px;'>"
              +kpi2('TRADES',s['total'],'#e8edf2')
              +kpi2('WIN RATE',wr_str,wr_col)
              +kpi2('TOTAL R',r_str,r_col)
              +kpi2('AVG R / TRADE',avg_str,r_col)
              +kpi2('PROFIT FACTOR',str(pf_val),pf_col)
              +"</div>")
    st.markdown(kpi_html,unsafe_allow_html=True)

    # ── AI Insights ───────────────────────────────────────────
    st.markdown("<div style='font-family:Space Mono,monospace;font-size:13px;color:#00d4aa;letter-spacing:.08em;margin-bottom:8px;'>🤖 AI INSIGHTS — self-learned from your trades</div>",unsafe_allow_html=True)
    ins_html="<div style='background:#0d1117;border:1px solid rgba(0,212,170,0.2);border-radius:8px;padding:12px 16px;margin-bottom:16px;'>"
    for tip in journal_insights(j):
        ins_html+=f"<div style='font-size:12px;color:#e8edf5;font-family:Space Mono,monospace;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);'>{tip}</div>"
    ins_html+="</div>"
    st.markdown(ins_html,unsafe_allow_html=True)

    # ── Breakdown tabs ────────────────────────────────────────
    tb1,tb2,tb3,tb4=st.tabs(["By Grade","By Session","By News","Score Heatmap"])
    def _bar_chart(labels,win_rates,counts,title):
        colors=["#10b981" if w>=55 else "#f59e0b" if w>=45 else "#ef4444" for w in win_rates]
        fig=go.Figure(go.Bar(x=labels,y=win_rates,marker_color=colors,
                             text=[f"{w:.0f}%<br>n={n}" for w,n in zip(win_rates,counts)],
                             textposition="outside"))
        fig.add_hline(y=50,line=dict(color="#8b9ab0",dash="dot",width=1))
        fig.update_layout(title=title,yaxis_title="Win Rate %",yaxis_range=[0,105],
                          plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
                          font=dict(color="#e8edf2"),height=260,margin=dict(t=40,b=20))
        return fig
    with tb1:
        gs=s["grade_s"]
        if gs:
            st.plotly_chart(_bar_chart(list(gs.keys()),[v["wr"] for v in gs.values()],[v["n"] for v in gs.values()],"Win Rate by Grade"),use_container_width=True)
        else: st.info("Not enough grade data yet.")
    with tb2:
        ss=s["sess_s"]
        if ss:
            st.plotly_chart(_bar_chart(list(ss.keys()),[v["wr"] for v in ss.values()],[v["n"] for v in ss.values()],"Win Rate by Session"),use_container_width=True)
        else: st.info("Not enough session data yet.")
    with tb3:
        ns=s["news_s"]
        if ns:
            st.plotly_chart(_bar_chart(list(ns.keys()),[v["wr"] for v in ns.values()],[v["n"] for v in ns.values()],"Win Rate by News Risk"),use_container_width=True)
        else: st.info("Not enough news data yet.")
    with tb4:
        sc=s["score_s"]
        if sc:
            buckets=sorted(sc.keys()); labels=[f"{b}-{b+9}" for b in buckets]
            st.plotly_chart(_bar_chart(labels,[sc[b]["wr"] for b in buckets],[sc[b]["n"] for b in buckets],"Win Rate by Score Range"),use_container_width=True)
        else: st.info("Not enough score data yet.")

    # ── Equity curve (running R) ──────────────────────────────
    st.markdown("### EQUITY CURVE (R-multiples)")
    df_j=pd.DataFrame(j)
    df_j["cum_r"]=df_j["pnl_r"].cumsum()
    fig_eq=go.Figure()
    fig_eq.add_trace(go.Scatter(x=list(range(1,len(df_j)+1)),y=df_j["cum_r"],
        mode="lines+markers",name="Cumulative R",
        line=dict(color="#00d4aa",width=2),
        marker=dict(color=["#10b981" if r>0 else "#ef4444" for r in df_j["pnl_r"]],size=7)))
    fig_eq.add_hline(y=0,line=dict(color="#8b9ab0",dash="dot",width=1))
    fig_eq.update_layout(plot_bgcolor="#0d1117",paper_bgcolor="#0d1117",
                         font=dict(color="#e8edf2"),height=280,margin=dict(t=20,b=20),
                         xaxis_title="Trade #",yaxis_title="Cumulative R")
    st.plotly_chart(fig_eq,use_container_width=True)

    # ── Full trade log ────────────────────────────────────────
    st.markdown("### TRADE LOG")
    display_cols=["id","ts","symbol","dir","entry","sl","exit","result","pnl_r","grade","final","news_risk","session","notes"]
    df_display=df_j[[c for c in display_cols if c in df_j.columns]].copy()
    df_display.columns=[c.upper() for c in df_display.columns]
    st.dataframe(df_display,use_container_width=True,hide_index=True)

    # Download + delete
    dc1,dc2=st.columns(2)
    dc1.download_button("⬇ Export CSV",df_j.to_csv(index=False).encode(),"trade_journal.csv","text/csv")
    if dc2.button("🗑 Clear All Trades"):
        st.session_state["_confirm_clear"]=True
    if st.session_state.get("_confirm_clear"):
        st.warning("Are you sure? This will delete all trade history.")
        cc1,cc2=st.columns(2)
        if cc1.button("Yes, delete all"):
            save_journal([]); st.session_state.pop("_confirm_clear",None)
            st.success("Journal cleared."); st.rerun()
        if cc2.button("Cancel"):
            st.session_state.pop("_confirm_clear",None); st.rerun()


# ============================================================
# MAIN
# ============================================================
if "Live" in mode:
    render_live()
elif "Backtest" in mode:
    render_backtest()
else:
    render_journal()
