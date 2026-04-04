"""
AlphaEdge Gold Signals — Telegram Bot Module

Full onboarding flow:
1. User sends /start → Welcome message
2. Bot asks how much capital they plan to deposit
3. If < USD 500 → rejected, must have minimum $500
4. Bot asks how long they've been trading (data collection)
5. Bot sends registration steps (VPN + FP Markets referral link)
6. User proves they registered → admin approves
7. Admin sends /approve → bot sends group invite + manual/video

Also handles:
- Gold signal broadcasts to channel
- TP hit / SL update / close notifications
- Admin commands (/signal, /close, /approve, /reject, /users)
"""
import json
import logging
import os
from datetime import datetime, timezone
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, PLATFORM_NAME
import requests

logger = logging.getLogger("alphaedge.telegram")

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ── User data storage ──
USER_DATA_FILE = os.path.join(os.path.dirname(__file__), "user_data.json")

# ── FP Markets Referral ──
FP_MARKETS_LINK = "https://portal.fpmarkets.com/register?fpm-affiliate-utm-source=IB&fpm-affiliate-agt=66209"
FP_MARKETS_CODE = "M4-66209"

# ── Onboarding States ──
STATE_NEW = "new"
STATE_ASKED_CAPITAL = "asked_capital"
STATE_ASKED_EXPERIENCE = "asked_experience"
STATE_SENT_STEPS = "sent_steps"
STATE_WAITING_PROOF = "waiting_proof"
STATE_PENDING_APPROVAL = "pending_approval"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"


def _load_users():
    """Load user data from JSON file."""
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_users(users):
    """Save user data to JSON file."""
    try:
        with open(USER_DATA_FILE, "w") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save user data: {e}")


def send_message(chat_id, text, parse_mode="HTML", disable_preview=True, reply_markup=None):
    """Send a message to a Telegram chat/channel."""
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = requests.post(
            f"{BASE_URL}/sendMessage",
            json=payload,
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Telegram send failed: {data}")
            return None
        return data["result"]["message_id"]
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return None


def edit_message(chat_id, message_id, text, parse_mode="HTML"):
    """Edit an existing message."""
    try:
        resp = requests.post(
            f"{BASE_URL}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception as e:
        logger.error(f"Telegram edit error: {e}")
        return False


def send_photo(chat_id, photo_url, caption="", parse_mode="HTML"):
    """Send a photo with caption."""
    try:
        resp = requests.post(
            f"{BASE_URL}/sendPhoto",
            json={
                "chat_id": chat_id,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception as e:
        logger.error(f"Telegram photo error: {e}")
        return False


def get_chat_invite_link(chat_id):
    """Generate an invite link for the group/channel."""
    try:
        resp = requests.post(
            f"{BASE_URL}/exportChatInviteLink",
            json={"chat_id": chat_id},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return data["result"]
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  TELEGRAM NOTIFIER — Signal broadcasts to channel
# ═══════════════════════════════════════════════════════════

class TelegramNotifier:
    """Sends gold trade updates to the Telegram channel."""

    def __init__(self, channel_id=None):
        self.channel_id = channel_id or TELEGRAM_CHANNEL_ID
        self.signal_messages = {}

    def broadcast_signal(self, trade):
        text = trade.format_signal_message()
        msg_id = send_message(self.channel_id, text)
        if msg_id:
            self.signal_messages[trade.id] = msg_id
            logger.info(f"Gold signal sent ({trade.direction}) — msg {msg_id}")
        return msg_id

    def broadcast_tp_hit(self, trade, tp_level, price):
        text = trade.format_tp_hit_message(tp_level, price)
        msg_id = send_message(self.channel_id, text)
        logger.info(f"TP{tp_level} hit notification sent")
        return msg_id

    def broadcast_sl_update(self, trade, reason, new_sl):
        if reason == "BREAKEVEN":
            text = (
                f"🛡 <b>SL → BREAKEVEN</b> — XAUUSD\n"
                f"{'━' * 28}\n"
                f"New SL: <code>{new_sl:.2f}</code>\n"
                f"Your entry is now protected! ✅\n"
                f"{'━' * 28}\n"
                f"🥇 {PLATFORM_NAME}"
            )
        else:
            text = (
                f"📐 <b>SL TRAILED</b> — XAUUSD\n"
                f"{'━' * 28}\n"
                f"New SL: <code>{new_sl:.2f}</code>\n"
                f"Profit locked at {reason} level 🔒\n"
                f"{'━' * 28}\n"
                f"🥇 {PLATFORM_NAME}"
            )
        return send_message(self.channel_id, text)

    def broadcast_close(self, trade):
        text = trade.format_close_message()
        msg_id = send_message(self.channel_id, text)
        logger.info(f"Close notification sent — {trade.close_reason}")
        return msg_id

    def broadcast_daily_summary(self, stats):
        text = (
            f"📊 <b>DAILY GOLD SUMMARY</b>\n"
            f"{'━' * 28}\n"
            f"Trades: {stats.get('total', 0)}\n"
            f"Wins: {stats.get('wins', 0)} | Losses: {stats.get('losses', 0)}\n"
            f"Win Rate: {stats.get('win_rate', 0):.0f}%\n"
            f"Total P&L: {stats.get('pnl_pips', 0):+.0f} pips\n"
            f"{'━' * 28}\n"
            f"🥇 {PLATFORM_NAME} — Automated Gold Signals"
        )
        return send_message(self.channel_id, text)

    def send_admin_alert(self, admin_chat_id, message):
        text = f"⚠️ <b>ADMIN ALERT</b>\n{'━' * 28}\n{message}"
        return send_message(admin_chat_id, text)

    def process_actions(self, actions):
        for action in actions:
            trade = action.get("trade")
            if not trade:
                continue
            act_type = action["action"]
            if act_type == "PARTIAL_CLOSE":
                tp_level = int(action["reason"].replace("TP", "").replace("_HIT", ""))
                self.broadcast_tp_hit(trade, tp_level, action["price"])
            elif act_type == "MOVE_SL":
                self.broadcast_sl_update(trade, action["reason"], action["new_sl"])
            elif act_type == "TRAIL_SL":
                self.broadcast_sl_update(trade, action["reason"], action["new_sl"])
            elif act_type in ("CLOSE_ALL", "FULLY_CLOSED"):
                self.broadcast_close(trade)


# ═══════════════════════════════════════════════════════════
#  ONBOARDING HANDLER — New user registration flow
# ═══════════════════════════════════════════════════════════

class OnboardingHandler:
    """
    Manages the full onboarding conversation flow:

    /start → Welcome → Ask capital → Ask experience →
    Send registration steps → Wait for proof →
    Admin approves → Send group invite
    """

    def __init__(self, admin_ids=None, group_invite_link=None):
        self.admin_ids = admin_ids or []
        self.group_invite_link = group_invite_link
        self.users = _load_users()

    def _get_user(self, user_id):
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "state": STATE_NEW,
                "name": "",
                "username": "",
                "capital": "",
                "experience": "",
                "fp_account": "",
                "joined_at": datetime.now(timezone.utc).isoformat(),
                "approved": False,
            }
        return self.users[uid]

    def _save(self):
        _save_users(self.users)

    def handle_message(self, chat_id, user_id, text, first_name="", username=""):
        """
        Route message based on user's current onboarding state.
        Returns True if handled, False if should pass to command handler.
        """
        user = self._get_user(user_id)
        user["name"] = first_name
        user["username"] = username
        state = user["state"]

        # Commands always pass through
        if text.startswith("/"):
            return False

        # ── State machine ──

        if state == STATE_ASKED_CAPITAL:
            return self._handle_capital_response(chat_id, user_id, user, text)

        elif state == STATE_ASKED_EXPERIENCE:
            return self._handle_experience_response(chat_id, user_id, user, text)

        elif state == STATE_WAITING_PROOF:
            return self._handle_proof(chat_id, user_id, user, text)

        elif state == STATE_PENDING_APPROVAL:
            send_message(chat_id, (
                "⏳ Your application is being reviewed by our team.\n"
                "We'll get back to you shortly!"
            ))
            return True

        elif state == STATE_APPROVED:
            send_message(chat_id, (
                "✅ You're already approved!\n"
                "Check the group for live gold signals. 🥇"
            ))
            return True

        return False

    def handle_photo(self, chat_id, user_id, first_name="", username=""):
        """Handle photo uploads (for account proof screenshots)."""
        user = self._get_user(user_id)
        state = user["state"]

        if state == STATE_WAITING_PROOF:
            user["state"] = STATE_PENDING_APPROVAL
            user["proof_submitted"] = datetime.now(timezone.utc).isoformat()
            self._save()

            send_message(chat_id, (
                "📸 <b>Screenshot received!</b>\n\n"
                "Thank you! Our team will review your account shortly.\n"
                "You'll receive a notification once approved. ⏳"
            ))

            # Notify all admins
            for admin_id in self.admin_ids:
                name = user.get("name", "Unknown")
                uname = f"@{user.get('username')}" if user.get("username") else "No username"
                send_message(admin_id, (
                    f"🔔 <b>NEW APPLICATION</b>\n"
                    f"{'━' * 28}\n"
                    f"User: {name} ({uname})\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"Capital: {user.get('capital', 'N/A')}\n"
                    f"Experience: {user.get('experience', 'N/A')}\n"
                    f"{'━' * 28}\n"
                    f"📸 Proof screenshot submitted\n\n"
                    f"To approve: /approve {user_id}\n"
                    f"To reject: /reject {user_id}"
                ))

            logger.info(f"New application from {first_name} ({user_id})")
            return True

        return False

    def start_onboarding(self, chat_id, user_id, first_name="", username=""):
        """Send welcome message and start the flow."""
        user = self._get_user(user_id)
        user["name"] = first_name
        user["username"] = username

        # If already approved, just welcome back
        if user["state"] == STATE_APPROVED:
            send_message(chat_id, (
                f"🥇 Welcome back, {first_name}!\n"
                "You're already a member. Check the group for signals!"
            ))
            return

        # If pending, remind them
        if user["state"] == STATE_PENDING_APPROVAL:
            send_message(chat_id, (
                f"⏳ Hi {first_name}, your application is still under review.\n"
                "We'll notify you once approved!"
            ))
            return

        # Fresh start or restart
        user["state"] = STATE_NEW
        self._save()

        # Step 1: Welcome message
        send_message(chat_id, (
            f"🥇 <b>Welcome to {PLATFORM_NAME}!</b>\n\n"
            "We trade ONE asset — <b>XAUUSD (Gold)</b>\n"
            "Focused. Disciplined. Profitable.\n\n"
            "As a member, you'll receive:\n"
            "• Live gold trade signals\n"
            "• Real-time TP hit notifications\n"
            "• SL updates (breakeven + trailing)\n"
            "• Daily gold performance summaries\n\n"
            f"{'━' * 28}\n"
            "To join our exclusive signals group, we need to set up your trading account first.\n\n"
            "Let's get started! 👇"
        ))

        # Step 2: Ask about capital
        import time
        time.sleep(1)

        user["state"] = STATE_ASKED_CAPITAL
        self._save()

        send_message(chat_id, (
            "💰 <b>Step 1 of 3 — Capital</b>\n"
            f"{'━' * 28}\n\n"
            "How much capital are you planning to deposit?\n\n"
            "1️⃣  USD 300 - USD 499\n"
            "2️⃣  USD 500 - USD 1,000\n"
            "3️⃣  More than USD 1,000\n\n"
            "Reply with <b>1</b>, <b>2</b>, or <b>3</b>"
        ))

    def _handle_capital_response(self, chat_id, user_id, user, text):
        """Process capital amount response."""
        text = text.strip()

        if text == "1" or "300" in text or "499" in text:
            # Below minimum
            user["capital"] = "USD 300-499"
            user["state"] = STATE_REJECTED
            self._save()

            send_message(chat_id, (
                "⚠️ <b>Minimum Requirement Not Met</b>\n"
                f"{'━' * 28}\n\n"
                "We require a <b>minimum deposit of USD 500</b> to join our signals group.\n\n"
                "This is to ensure you have enough margin to follow our gold signals safely "
                "and manage risk properly.\n\n"
                "When you're ready to deposit USD 500 or more, "
                "just send /start again and we'll get you set up! 🥇"
            ))
            return True

        elif text == "2" or "500" in text or "1000" in text or "1,000" in text:
            user["capital"] = "USD 500-1,000"
        elif text == "3" or "1000" in text.replace(",", "") or "more" in text.lower():
            user["capital"] = "USD 1,000+"
        else:
            send_message(chat_id, "Please reply with <b>1</b>, <b>2</b>, or <b>3</b>")
            return True

        # Move to experience question
        user["state"] = STATE_ASKED_EXPERIENCE
        self._save()

        send_message(chat_id, (
            "📊 <b>Step 2 of 3 — Experience</b>\n"
            f"{'━' * 28}\n\n"
            "How long have you been trading?\n\n"
            "1️⃣  I'm new to trading\n"
            "2️⃣  Less than 1 year\n"
            "3️⃣  1 - 3 years\n"
            "4️⃣  More than 3 years\n\n"
            "Reply with <b>1</b>, <b>2</b>, <b>3</b>, or <b>4</b>"
        ))
        return True

    def _handle_experience_response(self, chat_id, user_id, user, text):
        """Process experience response and send registration steps."""
        text = text.strip()

        exp_map = {
            "1": "New to trading",
            "2": "Less than 1 year",
            "3": "1-3 years",
            "4": "More than 3 years",
        }
        user["experience"] = exp_map.get(text, text)
        user["state"] = STATE_SENT_STEPS
        self._save()

        # Send registration steps
        send_message(chat_id, (
            "✅ <b>Great! Now let's set up your account.</b>\n\n"
            f"{'━' * 28}\n"
            "📋 <b>Step 3 of 3 — Account Registration</b>\n"
            f"{'━' * 28}\n\n"
            "<b>Follow these steps carefully:</b>\n\n"
            "1️⃣ Download the <b>1.1.1.1</b> app from App Store / Play Store\n"
            "   (It's a free VPN by Cloudflare)\n\n"
            "2️⃣ Open the app and <b>turn on the VPN</b>\n\n"
            "3️⃣ While VPN is ON, click the link below to register:\n\n"
            f"👉 <a href=\"{FP_MARKETS_LINK}\">Register FP Markets Account</a>\n\n"
            f"📌 Referral Code: <code>{FP_MARKETS_CODE}</code>\n\n"
            "4️⃣ Complete the registration and verify your account\n\n"
            "5️⃣ Deposit your capital (minimum USD 500)\n\n"
            f"{'━' * 28}\n"
            "⚠️ <b>IMPORTANT:</b> Make sure you register through our link above "
            "so we can verify your account."
        ))

        import time
        time.sleep(2)

        user["state"] = STATE_WAITING_PROOF
        self._save()

        send_message(chat_id, (
            "📸 <b>After you've registered and deposited:</b>\n\n"
            "Please send me a <b>screenshot</b> showing:\n"
            "• Your FP Markets account number\n"
            "• Your deposit confirmation\n\n"
            "Once verified, you'll receive:\n"
            "✅ Access to our exclusive signals group\n"
            "✅ Our trading manual / video guide\n\n"
            "Take your time — send the screenshot when you're ready! 🥇"
        ))
        return True

    def _handle_proof(self, chat_id, user_id, user, text):
        """Handle text messages while waiting for proof."""
        # Check if they're sending an account number
        if any(c.isdigit() for c in text) and len(text) >= 5:
            user["fp_account"] = text
            self._save()
            send_message(chat_id, (
                f"📝 Account info noted: <code>{text}</code>\n\n"
                "Now please also send a <b>screenshot</b> of your FP Markets "
                "dashboard or deposit confirmation to verify. 📸"
            ))
            return True

        send_message(chat_id, (
            "📸 Please send a <b>screenshot</b> of your FP Markets account "
            "to verify your registration.\n\n"
            "If you haven't registered yet, follow the steps above first!"
        ))
        return True

    def approve_user(self, admin_chat_id, user_id):
        """Admin approves a user — send them the group invite."""
        uid = str(user_id)
        if uid not in self.users:
            send_message(admin_chat_id, f"❌ User {user_id} not found.")
            return

        user = self.users[uid]
        user["state"] = STATE_APPROVED
        user["approved"] = True
        user["approved_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

        # Generate or use existing invite link
        invite_link = self.group_invite_link
        if not invite_link:
            invite_link = get_chat_invite_link(TELEGRAM_CHANNEL_ID)

        # Send approval to user
        send_message(int(user_id), (
            f"🎉 <b>APPROVED! Welcome to {PLATFORM_NAME}!</b>\n"
            f"{'━' * 28}\n\n"
            "You've been verified and approved to join our exclusive gold signals group.\n\n"
            f"👉 <b>Join the group:</b> {invite_link}\n\n"
            "📖 Our trading guide will be sent to you shortly.\n\n"
            "Remember:\n"
            "• Follow the signals discipline\n"
            "• Never risk more than you can afford\n"
            "• Gold is volatile — trust the system\n\n"
            f"Let's make money together! 🥇\n"
            f"{'━' * 28}\n"
            f"{PLATFORM_NAME}"
        ))

        name = user.get("name", "Unknown")
        send_message(admin_chat_id, f"✅ {name} ({user_id}) has been approved and notified.")
        logger.info(f"User approved: {name} ({user_id})")

    def reject_user(self, admin_chat_id, user_id, reason=""):
        """Admin rejects a user."""
        uid = str(user_id)
        if uid not in self.users:
            send_message(admin_chat_id, f"❌ User {user_id} not found.")
            return

        user = self.users[uid]
        user["state"] = STATE_REJECTED
        self._save()

        reject_msg = reason if reason else "Your application could not be verified at this time."
        send_message(int(user_id), (
            f"❌ <b>Application Update</b>\n"
            f"{'━' * 28}\n\n"
            f"{reject_msg}\n\n"
            "If you believe this is a mistake, please send /start to try again "
            "or contact our support."
        ))

        name = user.get("name", "Unknown")
        send_message(admin_chat_id, f"❌ {name} ({user_id}) has been rejected.")

    def get_all_users_summary(self):
        """Get summary of all users for admin."""
        total = len(self.users)
        approved = sum(1 for u in self.users.values() if u.get("approved"))
        pending = sum(1 for u in self.users.values() if u.get("state") == STATE_PENDING_APPROVAL)
        rejected = sum(1 for u in self.users.values() if u.get("state") == STATE_REJECTED)
        in_progress = total - approved - pending - rejected

        lines = [
            f"📊 <b>USER STATISTICS</b>",
            f"{'━' * 28}",
            f"Total users: {total}",
            f"✅ Approved: {approved}",
            f"⏳ Pending approval: {pending}",
            f"🔄 In progress: {in_progress}",
            f"❌ Rejected: {rejected}",
        ]

        if pending > 0:
            lines.append(f"\n<b>PENDING USERS:</b>")
            for uid, u in self.users.items():
                if u.get("state") == STATE_PENDING_APPROVAL:
                    name = u.get("name", "Unknown")
                    uname = f"@{u.get('username')}" if u.get("username") else ""
                    cap = u.get("capital", "?")
                    lines.append(f"• {name} {uname} | {cap} | /approve {uid}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  COMMAND HANDLER — Routes all messages
# ═══════════════════════════════════════════════════════════

class CommandHandler:
    """
    Main command handler with onboarding integration.
    Routes commands and free-text messages.
    """

    def __init__(self, trade_manager, notifier, admin_ids=None, group_invite_link=None):
        self.trade_manager = trade_manager
        self.notifier = notifier
        self.admin_ids = admin_ids or []
        self.onboarding = OnboardingHandler(
            admin_ids=self.admin_ids,
            group_invite_link=group_invite_link,
        )
        self.commands = {
            "/start": self._cmd_start,
            "/status": self._cmd_status,
            "/gold": self._cmd_status,
            "/trades": self._cmd_trades,
            "/help": self._cmd_help,
            "/signal": self._cmd_signal,
            "/close": self._cmd_close,
            "/approve": self._cmd_approve,
            "/reject": self._cmd_reject,
            "/users": self._cmd_users,
        }

    def handle_update(self, update):
        """Process a Telegram update (message or photo)."""
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        first_name = message.get("from", {}).get("first_name", "")
        username = message.get("from", {}).get("username", "")
        chat_type = message.get("chat", {}).get("type", "")

        if not chat_id:
            return

        # Only handle private messages for onboarding
        if chat_type != "private":
            return

        # Handle photo uploads (proof screenshots)
        if message.get("photo"):
            self.onboarding.handle_photo(chat_id, user_id, first_name, username)
            return

        # Handle document uploads (proof files)
        if message.get("document"):
            self.onboarding.handle_photo(chat_id, user_id, first_name, username)
            return

        text = message.get("text", "").strip()
        if not text:
            return

        # Check if it's a command
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            args = text.split()[1:] if len(text.split()) > 1 else []
            handler = self.commands.get(cmd)
            if handler:
                is_admin = user_id in self.admin_ids
                handler(chat_id, user_id, args, is_admin, first_name, username)
            else:
                send_message(chat_id, "Unknown command. Type /help for available commands.")
            return

        # Not a command — pass to onboarding handler
        handled = self.onboarding.handle_message(
            chat_id, user_id, text, first_name, username
        )
        if not handled:
            send_message(chat_id, (
                "Type /start to begin or /help for available commands."
            ))

    # ── Commands ──

    def _cmd_start(self, chat_id, user_id, args, is_admin, first_name="", username=""):
        """Start the onboarding flow."""
        self.onboarding.start_onboarding(chat_id, user_id, first_name, username)

    def _cmd_status(self, chat_id, user_id, args, is_admin, *_):
        summary = self.trade_manager.get_active_summary()
        if not summary:
            send_message(chat_id, "🥇 No active gold trades right now. Stay tuned!")
            return
        lines = [f"📊 <b>ACTIVE GOLD TRADES</b>\n"]
        for t in summary:
            emoji = "🟢" if t["direction"] == "Buy" else "🔴"
            lines.append(
                f"{emoji} XAUUSD {t['direction']} @ {t['entry']:.2f}\n"
                f"   SL: {t['sl']:.2f} | TP: {t['tp_hit']}/10 | "
                f"Lots: {t['lot_remaining']}"
            )
        lines.append(f"\n🥇 {PLATFORM_NAME}")
        send_message(chat_id, "\n".join(lines))

    def _cmd_trades(self, chat_id, user_id, args, is_admin, *_):
        closed = self.trade_manager.closed_trades[-10:]
        if not closed:
            send_message(chat_id, "No closed gold trades yet today.")
            return
        lines = ["📋 <b>RECENT GOLD TRADES</b>\n"]
        for t in closed:
            emoji = "🟢" if "TP" in str(t.get("close_reason", "")) else "🔴"
            lines.append(f"{emoji} XAUUSD — {t['close_reason']} | TPs: {t['tp_hit_count']}/10")
        lines.append(f"\n🥇 {PLATFORM_NAME}")
        send_message(chat_id, "\n".join(lines))

    def _cmd_help(self, chat_id, user_id, args, is_admin, *_):
        text = (
            f"📖 <b>{PLATFORM_NAME} — COMMANDS</b>\n\n"
            "/start — Start onboarding\n"
            "/gold — Active gold trade\n"
            "/trades — Recent closed trades\n"
            "/help — This message"
        )
        if is_admin:
            text += (
                "\n\n🔐 <b>ADMIN COMMANDS</b>\n"
                "/signal BUY/SELL ENTRY SL LOT\n"
                "/close TRADE_ID [reason]\n"
                "/approve USER_ID\n"
                "/reject USER_ID [reason]\n"
                "/users — View all users"
            )
        send_message(chat_id, text)

    def _cmd_signal(self, chat_id, user_id, args, is_admin, *_):
        if not is_admin:
            send_message(chat_id, "⛔ Admin only command.")
            return
        if len(args) < 4:
            send_message(chat_id, "Usage: /signal BUY 2350.00 2340.00 0.50")
            return
        try:
            direction = args[0].capitalize()
            entry = float(args[1])
            sl = float(args[2])
            lot = float(args[3])
            trade = self.trade_manager.open_trade("XAUUSD", direction, entry, sl, lot, source="manual")
            self.notifier.broadcast_signal(trade)
            send_message(chat_id, f"✅ Gold signal opened: {trade.id}")
        except Exception as e:
            send_message(chat_id, f"❌ Error: {e}")

    def _cmd_close(self, chat_id, user_id, args, is_admin, *_):
        if not is_admin:
            send_message(chat_id, "⛔ Admin only command.")
            return
        if len(args) < 1:
            send_message(chat_id, "Usage: /close TRADE_ID [reason]")
            return
        trade_id = args[0]
        reason = args[1] if len(args) > 1 else "manual"
        trade = self.trade_manager.close_trade(trade_id, reason)
        if trade:
            self.notifier.broadcast_close(trade)
            send_message(chat_id, f"✅ Trade {trade_id} closed ({reason})")
        else:
            send_message(chat_id, f"❌ Trade {trade_id} not found.")

    def _cmd_approve(self, chat_id, user_id, args, is_admin, *_):
        """Admin approves a user."""
        if not is_admin:
            send_message(chat_id, "⛔ Admin only command.")
            return
        if len(args) < 1:
            send_message(chat_id, "Usage: /approve USER_ID")
            return
        self.onboarding.approve_user(chat_id, args[0])

    def _cmd_reject(self, chat_id, user_id, args, is_admin, *_):
        """Admin rejects a user."""
        if not is_admin:
            send_message(chat_id, "⛔ Admin only command.")
            return
        if len(args) < 1:
            send_message(chat_id, "Usage: /reject USER_ID [reason]")
            return
        reason = " ".join(args[1:]) if len(args) > 1 else ""
        self.onboarding.reject_user(chat_id, args[0], reason)

    def _cmd_users(self, chat_id, user_id, args, is_admin, *_):
        """Admin views all users."""
        if not is_admin:
            send_message(chat_id, "⛔ Admin only command.")
            return
        summary = self.onboarding.get_all_users_summary()
        send_message(chat_id, summary)


# ═══════════════════════════════════════════════════════════
#  POLLING
# ═══════════════════════════════════════════════════════════

def start_polling(command_handler, interval=1):
    """Long-polling loop for Telegram updates."""
    offset = 0
    logger.info("Telegram polling started...")

    while True:
        try:
            resp = requests.get(
                f"{BASE_URL}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            data = resp.json()
            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    command_handler.handle_update(update)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            import time
            time.sleep(5)
