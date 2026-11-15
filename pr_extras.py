"""
PR BOT extras — قابلیت‌هایی که ربات قبلی داشت و prbot نداشت.

این فایل prbot.py رو دست نمی‌زنه؛ فقط یک زیرکلاس (PRBot) از HighriseBot می‌سازه:
  • تیپ طلا با محاسبه‌ی کارمزد:  !tip  !tipall  !wallet          (فقط مالک)
  • VIP:                          !addvip !remvip !vips
  • فریز کاربر (با اِنفورس):      !freeze !unfreeze
  • تعامل‌ها:                      !hug !kiss !punch !slap !fight  @user
  • فالو (start_follow/stop_follow؛ در prbot صدا زده می‌شد ولی تعریف نشده بود)
  • لباس بات:                     !saveoutfit !restoreoutfit (+ بازگردانی خودکار)
  • راهنما:                        !help [admin|loc|tip]
"""
import asyncio
import json
import os
import random
import re

import prbot
from prbot import HighriseBot, _data_path, _should_handle_command, _spam_allowed
from highrise import Position
from highrise.models import Error, Item

# ─────────────────────────────── tips ───────────────────────────────
BARS = [
    (10000, "gold_bar_10k"), (5000, "gold_bar_5000"), (1000, "gold_bar_1k"),
    (500, "gold_bar_500"), (100, "gold_bar_100"), (50, "gold_bar_50"),
    (10, "gold_bar_10"), (5, "gold_bar_5"), (1, "gold_bar_1"),
]
# کارمزد هایرایز به‌ازای هر شمش (روی موجودی ربات کم میشه، اضافه بر مبلغ تیپ)
FEES = {10000: 1000, 5000: 500, 1000: 100, 500: 50, 100: 10, 50: 5, 10: 1, 5: 1, 1: 1}
MAX_TIP = 10000        # سقف !tip
MAX_TIPALL = 1000      # سقف !tipall برای هر نفر

# پالت رنگی پیام‌های بات برای تنوع در روم: #5ad358, #ffde28, #ce291a, #f257bb, #8685d3, #ef6039
VARIETY_COLORS = [
    "#5ad358",  # سبز
    "#ffde28",  # زرد
    "#ce291a",  # قرمز
    "#f257bb",  # صورتی
    "#8685d3",  # یاسی / بنفش
    "#ef6039",  # نارنجی
]


def split_bars(amount: int):
    """مبلغ رو به شمش‌ها تقسیم می‌کنه → [(value, item_name), ...]"""
    out, left = [], int(amount)
    for value, name in BARS:
        while left >= value:
            out.append((value, name))
            left -= value
    return out


def total_with_fee(amount: int) -> int:
    return int(amount) + sum(FEES[v] for v, _ in split_bars(amount))


def _digits(s: str) -> str:
    for p, a, e in zip("۰۱۲۳۴۵۶۷۸۹", "٠١٢٣٤٥٦٧٨٩", "0123456789"):
        s = s.replace(p, e).replace(a, e)
    return s


# ─────────────────────────── commands / aliases ───────────────────────────
_ALIASES = {
    "help": ["!help", "!راهنما", "!دستورات", "!menu", "!منو"],
    "tip": ["!tip", "!تیپ"],
    "tipall": ["!tipall", "!تیپ_همه"],
    "wallet": ["!wallet", "!کیف", "!کیف_پول"],
    "addvip": ["!addvip", "!افزودن_وی_آی_پی"],
    "remvip": ["!remvip", "!حذف_وی_آی_پی"],
    "vips": ["!vips", "!وی_آی_پی"],
    "freeze": ["!freeze", "!فریز"],
    "unfreeze": ["!unfreeze", "!آنفریز"],
    "saveoutfit": ["!saveoutfit", "!ذخیره_لباس"],
    "restoreoutfit": ["!restoreoutfit", "!لباس_بات"],
    "hug": ["!hug", "!بغل"],
    "kiss": ["!kiss", "!بوس"],
    "punch": ["!punch", "!مشت"],
    "slap": ["!slap", "!سیلی"],
    "fight": ["!fight", "!دعوا"],
    "roll": ["!roll", "!تاس"],
    "flip": ["!flip", "!سکه", "!شیرخط"],
    "eightball": ["!8ball", "!فال", "!پیشگویی"],
    "love": ["!love", "!عشق", "!همسنجی"],
    "truth": ["!truth", "!حقیقت"],
    "dare": ["!dare", "!جرأت", "!شجاعت"],
    "syncdance": ["!syncdance", "!پارتی", "!دنس_جمعی"],
    "patrol": ["!patrol", "!گشت", "!گشت_زنی", "!نگهبانی"],
    "addpatrol": ["!addpatrol", "!ثبت_گشت"],
    "clearpatrol": ["!clearpatrol", "!پاک_گشت"],
    "botdance": ["!botdance", "!دنس_بات", "!loopdance", "!دنس_دائمی", "!دنس_مداوم", "!setdance", "!setbotdance", "!dancebot", "!تنظیم_دنس"],
    "stopbotdance": ["!stopbotdance", "!توقف_دنس_بات", "!stopdance", "!توقف_دنس", "!خاموش_دنس"],
    "welcome": ["!welcome", "!ورودی", "!پیام_ورود"],
    "setwelcome": ["!setwelcome", "!متن_ورود", "!تنظیم_ورود"],
    "leave": ["!leave", "!خروج", "!پیام_خروج"],
    "setleave": ["!setleave", "!متن_خروج", "!تنظیم_خروج"],
}
ALIAS_MAP = {a: cmd for cmd, al in _ALIASES.items() for a in al}

# cmd -> (emote id, آیا طرف مقابل هم همون ایموت رو اجرا کنه, متن)
INTERACT = {
    "hug": ("emote-hug", True, "🤗 بات @{t} رو بغل کرد!"),
    "kiss": ("emote-kiss", True, "😘 بات @{t} رو بوسید!"),
    "punch": ("emoji-punch", False, "👊 بات به @{t} مشت زد!"),
    "slap": ("emote-slap", False, "🖐️ بات به @{t} سیلی زد!"),
    "fight": ("emote-swordfight", True, "⚔️ بات با @{t} دعوا کرد!"),
}

HELP_TEXT = {
    "": [
        "📖 راهنمای PR BOT (رایگان — فروش ممنوع!)\n🎭 دنس: شماره ۱ تا ۴۰۰ یا اسم دنس | stop = توقف\n🏃 !follow [@user] / !unfollow\n🤗 !hug !kiss !punch !slap !fight @user\n💰 !daily  !balance | 🤖 !ai سوال",
        "🌐 دریافت رایگان بات:\nسایت: https://highrisepr.ir\nتلگرام: https://t.me/PR_BOT_HR\nبیشتر: !help admin | !help loc | !help tip",
    ],
    "admin": [
        "👑 ادمین:\n!addadmin !remadmin !admins\n!spam [ثانیه] [متن] | !stopspam\n!setwelcome متن | !copyoutfit on/off\n!savebotloc | !freeze !unfreeze @u\n!addvip !remvip !vips\n!saveoutfit !restoreoutfit",
    ],
    "loc": [
        "📍 نقاط:\n!save نام | !delloc نام | !locs\nنوشتن نام نقطه = تلپورت\n!tp !go !bring @u !goto @u !bot\n!adminsave !adminlocs",
    ],
    "tip": [
        "💸 (فقط مالک)\n!tip @user مبلغ\n!tipall مبلغ (سقف هر نفر ۱۰۰۰)\n!wallet = موجودی طلای بات\nکارمزد هایرایز به‌ازای هر شمش از موجودی بات کم میشه.",
    ],
}
HELP_TEXT["ادمین"] = HELP_TEXT["admin"]
HELP_TEXT["نقاط"] = HELP_TEXT["loc"]
HELP_TEXT["تیپ"] = HELP_TEXT["tip"]

_BASIC_OUTFIT_TYPES = {"body", "eye", "eyebrow", "mouth", "nose", "face_hair"}


class PRBot(HighriseBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._freeze_pos = {}
        self._extras_file = os.path.basename(self.db_file).replace("bot_database_", "pr_extras_")
        self._extras_file = _data_path(self._extras_file)
        self._extras = {
            "outfit": None,
            "patrol_points": [],
            "patrol_delay": 4.0,
            "auto_ad_enabled": True,
            "auto_ad_interval": 60.0,
            "auto_ad_text": "برای دریافت بات هشتک #botpr  و به سایت highrisepr.ir مراجعه کنید 🤖🕹️",
            "welcome_enabled": True,
            "welcome_text": "سلام @{user}! به روم ما خوش اومدی 🌱",
            "goodbye_enabled": True,
            "goodbye_text": "خداحافظ @{user}! به امید دیدار 👋",
            "bot_dance_active": False,
            "bot_dance_id": "emote-tired",
            "bot_dance_name": "خستگی (Tired)",
            "bot_dance_duration": 4.6,
            "color_chat_enabled": True,
            "color_cycling_enabled": True,
            "color_default": "#5ad358",
            "color_highlight": "#ffde28",
            "palette_colors": list(VARIETY_COLORS),
        }
        self.patrol_active = False
        self.patrol_task = None
        self.auto_ad_task = None
        self.bot_dance_task = None
        self._chat_wrapper_installed = False
        try:
            if os.path.exists(self._extras_file):
                with open(self._extras_file, "r", encoding="utf-8") as f:
                    self._extras.update(json.load(f))
        except Exception as e:
            print(f"⚠️ extras load error: {e}")

        # قفل دائمی تبلیغات خودکار و پالت ۶ رنگ (غیرقابل تغییر یا غیرفعال‌سازی)
        self._lock_permanent_features()

        self.patrol_points = list(self._extras.get("patrol_points", []))
        self.patrol_delay = float(self._extras.get("patrol_delay", 4.0))

    def _lock_permanent_features(self):
        self._extras["auto_ad_enabled"] = True
        self._extras["auto_ad_interval"] = 60.0
        self._extras["auto_ad_text"] = "برای دریافت بات هشتک #botpr  و به سایت highrisepr.ir مراجعه کنید 🤖🕹️"
        self._extras["color_chat_enabled"] = True
        self._extras["color_cycling_enabled"] = True
        self._extras["color_default"] = "#5ad358"
        self._extras["color_highlight"] = "#ffde28"
        self._extras["palette_colors"] = list(VARIETY_COLORS)
        for obsolete_key in ("dj_setup_code", "dj_max_per_user", "dj_update_url", "dj_update_key", "dj_ids", "dj_names", "song_queue"):
            self._extras.pop(obsolete_key, None)

    # ───────────────────────── helpers ─────────────────────────
    def _save_extras(self):
        self._lock_permanent_features()
        try:
            with open(self._extras_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self._extras, f, ensure_ascii=False, indent=2)
            os.replace(self._extras_file + ".tmp", self._extras_file)
        except Exception as e:
            print(f"⚠️ extras save error: {e}")

    def is_vip(self, user) -> bool:
        name = (getattr(user, "username", "") or "").lower()
        return name in self.vip_users or getattr(user, "id", "") in self.vip_users

    async def _room_users(self):
        try:
            resp = await self.highrise.get_room_users()
            if isinstance(resp, Error):
                return []
            return list(resp.content)
        except Exception as e:
            print(f"get_room_users error: {e}")
            return []

    async def _find_user(self, who: str):
        who = (who or "").strip().lstrip("@").lower()
        if not who:
            return None, None
        for u, pos in await self._room_users():
            if u.username.lower() == who or u.id == who:
                return u, pos
        return None, None

    async def _say(self, text: str):
        await self.highrise.chat(text)

    async def _whisper_lines(self, user_id: str, lines):
        for ln in lines:
            await self.highrise.send_whisper(user_id, ln[:250])

    # ───────────────────────── colored chat wrapper (#5ad358 & #ffde28) ─────────────────────────
    def _install_chat_color_wrapper(self):
        if not hasattr(self, "highrise") or getattr(self.highrise, "_is_colored_wrapper", False):
            return
        orig_chat = self.highrise.chat

        async def colored_chat(message: str) -> None:
            msg = str(message or "").strip()
            if not msg:
                return
            if self._extras.get("color_chat_enabled", True):
                if not (msg.startswith("<#") or msg.startswith("<color=")):
                    # Special check: ads, #botpr, highrisepr.ir, gold, tips, economy use highlight yellow #ffde28
                    if any(k in msg for k in ("#botpr", "highrisepr.ir", "PR_BOT_HR", "📢", "💰", "!tip", "موجودی", "کارمزد", "هشتگ", "هشتک")):
                        color = self._extras.get("color_highlight", "#ffde28")
                    elif self._extras.get("color_cycling_enabled", True):
                        self._color_index = getattr(self, "_color_index", 0) + 1
                        palette = self._extras.get("palette_colors") or VARIETY_COLORS
                        color = palette[self._color_index % len(palette)]
                    else:
                        color = self._extras.get("color_default", "#5ad358")
                    msg = f"<{color}>{msg}"
            try:
                return await orig_chat(msg)
            except Exception as chat_err:
                # If room chat fails or rejects tags, try sending plain message
                try:
                    plain = str(message or "").strip()
                    if plain != msg:
                        return await orig_chat(plain)
                except Exception as plain_err:
                    print(f"⚠️ chat error: {plain_err}")

        colored_chat._is_colored_wrapper = True
        self.highrise.chat = colored_chat

    # ───────────────────────── 1-minute auto ad (#botpr) ─────────────────────────
    def _start_auto_ad_task(self):
        if self.auto_ad_task and not self.auto_ad_task.done():
            self.auto_ad_task.cancel()
        self.auto_ad_task = asyncio.create_task(self._auto_ad_loop())

    async def _auto_ad_loop(self):
        while True:
            try:
                interval = float(self._extras.get("auto_ad_interval", 60.0))
                await asyncio.sleep(max(10.0, interval))
                ad_msg = "برای دریافت بات هشتک #botpr  و به سایت highrisepr.ir مراجعه کنید 🤖🕹️"
                highlight = "#ffde28"
                await self.highrise.chat(f"<{highlight}>📢 {ad_msg}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"auto_ad_loop error: {e}")
                await asyncio.sleep(10)

    # ───────────────────────── continuous bot dance ─────────────────────────
    def _resolve_emote(self, query: str):
        q = str(query or "").strip().lower()
        if not q:
            return "emote-tired", 4.6, "خستگی (Tired)"

        # Handle links/URLs or slashes (e.g. https://.../dance-macarena or /dance-floss)
        if "/" in q or "http" in q:
            import re
            m = re.search(r"(dance-[a-z0-9_-]+|emote-[a-z0-9_-]+|idle-[a-z0-9_-]+|emoji-[a-z0-9_-]+)", q)
            if m:
                q = m.group(1)
            else:
                q = q.rstrip("/").split("/")[-1].split("?")[0].strip()

        tuples = getattr(prbot, "ALL_EMOTE_TUPLES", [])
        if q.isdigit():
            idx = int(q) - 1
            if 0 <= idx < len(tuples):
                return tuples[idx][1], float(tuples[idx][2]), tuples[idx][0]

        # Match exact ID or stripped prefix
        for item in tuples:
            clean_id = item[1].lower().replace("emote-", "").replace("dance-", "").replace("emoji-", "").replace("idle-", "")
            if item[1].lower() == q or clean_id == q:
                return item[1], float(item[2]), item[0]

        # Match Persian/English name
        for item in tuples:
            if item[0].lower() == q or item[0].lower().replace(" ", "") == q.replace(" ", ""):
                return item[1], float(item[2]), item[0]

        for item in tuples:
            if q in item[0].lower():
                return item[1], float(item[2]), item[0]

        for item in tuples:
            if q in item[1].lower():
                return item[1], float(item[2]), item[0]

        # Custom emote ID passed directly
        if q.startswith("dance-") or q.startswith("emote-") or q.startswith("idle-") or q.startswith("emoji-"):
            clean_name = q.replace("dance-", "Dance ").replace("emote-", "Emote ").replace("idle-", "Idle ").title()
            return q, 6.0, clean_name

        return "emote-tired", 4.6, "خستگی (Tired)"

    async def start_bot_continuous_dance(self, query: str):
        await self.stop_bot_continuous_dance()
        emote_id, duration, name = self._resolve_emote(query)
        self._extras["bot_dance_active"] = True
        self._extras["bot_dance_id"] = emote_id
        self._extras["bot_dance_name"] = name
        self._extras["bot_dance_duration"] = float(duration)
        self.bot_dance_emote = emote_id
        self._save_extras()
        # Immediately trigger the dance once, then maintain in loop
        try:
            await self.highrise.send_emote(emote_id)
        except Exception as e:
            print(f"⚠️ immediate dance error: {e}")
        self.bot_dance_task = asyncio.create_task(self._continuous_dance_loop(emote_id, duration))
        return name, emote_id

    async def stop_bot_continuous_dance(self):
        self._extras["bot_dance_active"] = False
        self._save_extras()
        if self.bot_dance_task and not self.bot_dance_task.done():
            self.bot_dance_task.cancel()
            self.bot_dance_task = None

    async def _continuous_dance_loop(self, emote_id: str, duration: float):
        sleep_sec = max(2.0, float(duration) - 0.5)
        while self._extras.get("bot_dance_active", False):
            try:
                # In Highrise SDK, sending emote to bot itself must pass target_user_id = None
                await self.highrise.send_emote(emote_id)
            except Exception as e:
                print(f"⚠️ continuous dance error: {e}")
            await asyncio.sleep(sleep_sec)

    async def _bot_dance_loop(self):
        """Overrides prbot's basic 6-second dance loop so prbot's on_start can call it without arguments."""
        while True:
            try:
                if not self._extras.get("bot_dance_active", False):
                    dance_emote = getattr(self, "bot_dance_emote", "emote-tired")
                    await self.highrise.send_emote(dance_emote)
                await asyncio.sleep(6)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)

    # ───────────────────────── follow (missing in prbot) ─────────────────────────
    async def start_follow(self, target):
        await self.stop_follow()
        self.follow_target = str(target).strip().lstrip("@").lower()
        self.follow_task = asyncio.create_task(self._follow_loop(self.follow_target))

    async def stop_follow(self):
        self.follow_target = None
        t, self.follow_task = self.follow_task, None
        if t and not t.done():
            t.cancel()

    async def _follow_loop(self, who: str):
        last, missing = None, 0
        try:
            while self.follow_target == who:
                u, pos = await self._find_user(who)
                if u is None:
                    missing += 1
                    if missing >= 15:
                        print(f"follow: {who} not in room, stopping")
                        break
                elif isinstance(pos, Position):
                    missing = 0
                    if last is None or abs(pos.x - last[0]) + abs(pos.z - last[1]) > 0.4:
                        last = (pos.x, pos.z)
                        await self.highrise.walk_to(Position(pos.x + 1, pos.y, pos.z))
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"follow loop error: {e}")

    # ───────────────────────── patrol (گشت‌زنی نگهبانی در روم) ─────────────────────────
    async def start_patrol(self):
        await self.stop_patrol()
        await self.stop_follow()
        self.patrol_active = True
        self.patrol_task = asyncio.create_task(self._patrol_loop())
        print("🚶‍♂️ حالت گشت‌زنی بات فعال شد")
        await self._say("🚶‍♂️ حالت گشت‌زنی و نگهبانی ربات فعال شد! 🛡️")

    async def stop_patrol(self):
        self.patrol_active = False
        t, self.patrol_task = self.patrol_task, None
        if t and not t.done():
            t.cancel()
        print("⏹ حالت گشت‌زنی متوقف شد")

    async def _patrol_loop(self):
        try:
            while self.patrol_active:
                pts = self.patrol_points
                if not pts:
                    # اگر نقطه‌ای ثبت نشده باشد، گشت‌زنی محیطی هوشمند در روم انجام می‌دهد
                    cur_pos = None
                    if getattr(self, "bot_id", None):
                        cur_pos = await self.get_user_pos(self.bot_id)
                    cx = cur_pos.x if cur_pos else 10.0
                    cy = cur_pos.y if cur_pos else 0.0
                    cz = cur_pos.z if cur_pos else 10.0
                    pts = [
                        {"x": cx - 2.5, "y": cy, "z": cz - 2.5},
                        {"x": cx + 2.5, "y": cy, "z": cz - 2.5},
                        {"x": cx + 2.5, "y": cy, "z": cz + 2.5},
                        {"x": cx - 2.5, "y": cy, "z": cz + 2.5},
                    ]

                for p in pts:
                    if not self.patrol_active:
                        break
                    try:
                        target = Position(float(p["x"]), float(p["y"]), float(p["z"]))
                        await self.highrise.walk_to(target)
                    except Exception as e:
                        print(f"patrol walk error: {e}")

                    # زمان رسیدن به ایستگاه
                    await asyncio.sleep(4.0)
                    if not self.patrol_active:
                        break

                    # حرکت دیده‌بانی یا ایموت کوتاه در ایستگاه
                    try:
                        em = random.choice(["emote-wave", "idle-enthusiastic", "emoji-thumbsup", "emote-hello"])
                        await self.highrise.send_emote(em)
                    except Exception:
                        pass

                    await asyncio.sleep(self.patrol_delay)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"patrol loop error: {e}")
        finally:
            self.patrol_active = False

    async def cmd_patrol(self, user, args):
        sub = args[0].lower() if args else ""
        if sub in ("on", "start", "روشن", "شروع"):
            await self.start_patrol()
        elif sub in ("off", "stop", "خاموش", "توقف"):
            await self.stop_patrol()
            await self._say("⏹ حالت گشت‌زنی ربات خاموش شد.")
        elif sub in ("add", "ثبت", "نقطه"):
            await self.cmd_addpatrol(user, args[1:])
        elif sub in ("clear", "reset", "پاک"):
            await self.cmd_clearpatrol(user, args[1:])
        elif sub in ("speed", "delay", "سرعت", "تایم") and len(args) > 1 and _digits(args[1]).isdigit():
            sec = max(2.0, min(30.0, float(_digits(args[1]))))
            self.patrol_delay = sec
            self._extras["patrol_delay"] = sec
            self._save_extras()
            await self._say(f"⏱️ توقف در هر ایستگاه گشت‌زنی به {sec:.0f} ثانیه تنظیم شد.")
        elif sub in ("info", "وضعیت"):
            st = "فعال 🟢" if self.patrol_active else "غیرفعال ⚪"
            await self._say(f"🚶‍♂️ وضعیت گشت‌زنی: {st} | تعداد نقاط ثبت‌شده: {len(self.patrol_points)} | مکث: {self.patrol_delay:.0f}ثانیه")
        else:
            if self.patrol_active:
                await self.stop_patrol()
                await self._say("⏹ گشت‌زنی ربات متوقف شد.")
            else:
                await self.start_patrol()

    async def cmd_addpatrol(self, user, args):
        pos = await self.get_user_pos(user.id)
        if not pos:
            return await self._say("❌ موقعیت شما در روم پیدا نشد.")
        self.patrol_points.append({"x": round(pos.x, 2), "y": round(pos.y, 2), "z": round(pos.z, 2)})
        self._extras["patrol_points"] = self.patrol_points
        self._save_extras()
        await self._say(f"📍 ایستگاه شماره {len(self.patrol_points)} به مسیر گشت‌زنی اضافه شد! (x={pos.x:.1f}, z={pos.z:.1f})")

    async def cmd_clearpatrol(self, user, args):
        self.patrol_points = []
        self._extras["patrol_points"] = []
        self._save_extras()
        await self._say("🧹 تمام نقاط مسیر گشت‌زنی پاک شدند. (گشت‌زنی خودکار فعال خواهد بود)")

    # ───────────────────────── tipping ─────────────────────────
    async def _wallet_gold(self):
        w = await self.highrise.get_wallet()
        if isinstance(w, Error):
            return None
        return sum(int(getattr(c, "amount", 0)) for c in getattr(w, "content", [])
                   if getattr(c, "type", "") == "gold")

    async def _send_tip(self, user_id: str, amount: int) -> bool:
        for _, name in split_bars(amount):
            res = await self.highrise.tip_user(user_id, name)
            if isinstance(res, Error) or (isinstance(res, str) and res != "success"):
                return False
            await asyncio.sleep(0.3)
        return True

    async def cmd_tip(self, user, args):
        nums = [p for p in args if _digits(p).isdigit()]
        names = [p for p in args if not _digits(p).isdigit()]
        if not nums or not names:
            return await self._say("❌ مثال: !tip @username 10")
        amount = int(_digits(nums[0]))
        if not 1 <= amount <= MAX_TIP:
            return await self._say(f"❌ مبلغ باید بین ۱ تا {MAX_TIP} باشه")
        target, _ = await self._find_user(names[0])
        if target is None:
            return await self._say("❌ کاربر توی روم پیدا نشد")
        gold = await self._wallet_gold()
        if gold is None:
            return await self._say("❌ نتونستم کیف پول بات رو بخونم")
        need = total_with_fee(amount)
        if gold < need:
            return await self._say(f"❌ موجودی کافی نیست! نیاز: {need} (با کارمزد) | موجودی: {gold}")
        if await self._send_tip(target.id, amount):
            await self._say(f"💰 به @{target.username} مبلغ {amount} سکه تیپ شد!")
        else:
            await self._say("❌ خطا در ارسال تیپ")

    async def cmd_tipall(self, user, args):
        if not args or not _digits(args[0]).isdigit():
            return await self._say("❌ مثال: !tipall 5")
        amount = int(_digits(args[0]))
        if not 1 <= amount <= MAX_TIPALL:
            return await self._say(f"❌ مبلغ هر نفر باید بین ۱ تا {MAX_TIPALL} باشه")
        targets = [u for u, _ in await self._room_users() if u.id != self.bot_id]
        if not targets:
            return await self._say("❌ کسی توی روم نیست")
        gold = await self._wallet_gold()
        if gold is None:
            return await self._say("❌ نتونستم کیف پول بات رو بخونم")
        need = total_with_fee(amount) * len(targets)
        if gold < need:
            return await self._say(f"❌ موجودی کافی نیست! نیاز: {need} برای {len(targets)} نفر | موجودی: {gold}")
        ok = 0
        for u in targets:
            if await self._send_tip(u.id, amount):
                ok += 1
        await self._say(f"💰 به {ok} نفر هرکدوم {amount} سکه تیپ شد!")

    async def cmd_wallet(self, user, args):
        gold = await self._wallet_gold()
        await self._say("❌ نتونستم موجودی رو بخونم" if gold is None else f"👛 موجودی طلای بات: {gold}")

    # ───────────────────────── VIP ─────────────────────────
    async def cmd_addvip(self, user, args):
        if not args:
            return await self._say("❌ مثال: !addvip @username")
        name = args[0].lstrip("@").lower()
        self.vip_users.add(name)
        self._save_data()
        await self._say(f"⭐ @{name} به لیست VIP اضافه شد")

    async def cmd_remvip(self, user, args):
        if not args:
            return await self._say("❌ مثال: !remvip @username")
        name = args[0].lstrip("@").lower()
        self.vip_users.discard(name)
        self._save_data()
        await self._say(f"🗑️ @{name} از VIP حذف شد")

    async def cmd_vips(self, user, args):
        v = sorted(x for x in self.vip_users if not x.isdigit() and len(x) < 40)
        await self._say("⭐ VIPها: " + (" ، ".join("@" + x for x in v) if v else "هیچکس"))

    # ───────────────────────── freeze ─────────────────────────
    async def cmd_freeze(self, user, args):
        if not args:
            return await self._say("❌ مثال: !freeze @username")
        target, pos = await self._find_user(args[0])
        if target is None:
            return await self._say("❌ کاربر توی روم پیدا نشد")
        if self.is_user_admin(target):
            return await self._say("⛔ ادمین‌ها رو نمیشه فریز کرد")
        if not isinstance(pos, Position):
            return await self._say("❌ کاربر الان نشسته؛ بعد از ایستادن فریزش کن")
        self._freeze_pos[target.id] = pos
        self.frozen_users.add(target.id)
        await self._say(f"🧊 @{target.username} فریز شد")

    async def cmd_unfreeze(self, user, args):
        if not args:
            return await self._say("❌ مثال: !unfreeze @username")
        target, _ = await self._find_user(args[0])
        if target is None:
            return await self._say("❌ کاربر توی روم پیدا نشد")
        self._freeze_pos.pop(target.id, None)
        self.frozen_users.discard(target.id)
        await self._say(f"🔥 @{target.username} آزاد شد")

    async def on_user_move(self, user, destination) -> None:
        try:
            fp = self._freeze_pos.get(user.id)
            if fp is None or self.is_user_admin(user):
                return
            if (isinstance(destination, Position)
                    and (abs(destination.x - fp.x) > 0.05 or abs(destination.z - fp.z) > 0.05)):
                await self.highrise.teleport(user.id, fp)
        except Exception as e:
            print(f"freeze enforce error: {e}")

    async def on_user_leave(self, user) -> None:
        u_id = getattr(user, "id", None)
        if u_id:
            self._freeze_pos.pop(u_id, None)
            self.frozen_users.discard(u_id)
        if self._extras.get("goodbye_enabled", True):
            try:
                username = getattr(user, "username", "") or self.user_name_cache.get(u_id, "")
                bot_user = (getattr(self, "bot_username", "") or "").lower()
                if username and username.lower() != bot_user:
                    tmpl = self._extras.get("goodbye_text", "خداحافظ @{user}! به امید دیدار 👋")
                    msg = tmpl.replace("{user}", username).replace("@{user}", f"@{username}")
                    await self.highrise.chat(msg)
            except Exception as e:
                print(f"goodbye msg error: {e}")

    # ───────────────────────── interactions ─────────────────────────
    async def cmd_interact(self, user, cmd, args):
        emote, both, text = INTERACT[cmd]
        if not args:
            return await self._say(f"❌ مثال: !{cmd} @username")
        target, pos = await self._find_user(args[0])
        if target is None:
            return await self._say("❌ کاربر توی روم پیدا نشد")
        if target.id == self.bot_id:
            return await self._say("😅 روی خودم نه!")
        try:
            if isinstance(pos, Position):
                await self.highrise.walk_to(Position(pos.x + 1, pos.y, pos.z))
                await asyncio.sleep(1.5)
            await self.highrise.send_emote(emote)
            if both:
                await self.highrise.send_emote(emote, target.id)
        except Exception as e:
            print(f"interact error: {e}")
        await self._say(text.format(t=target.username))

    # ───────────────────────── bot outfit ─────────────────────────
    @staticmethod
    def _item_to_dict(it):
        return {
            "type": it.type, "amount": getattr(it, "amount", 1), "id": it.id,
            "account_bound": getattr(it, "account_bound", False),
            "active_palette": getattr(it, "active_palette", -1),
        }

    @staticmethod
    def _dict_to_item(d):
        return Item(type=d["type"], amount=d.get("amount", 1), id=d["id"],
                    account_bound=d.get("account_bound", False),
                    active_palette=d.get("active_palette", -1))

    async def cmd_saveoutfit(self, user, args):
        resp = await self.highrise.get_my_outfit()
        if isinstance(resp, Error):
            return await self._say("❌ نتونستم لباس بات رو بخونم")
        self._extras["outfit"] = [self._item_to_dict(i) for i in resp.outfit]
        self._save_extras()
        await self._say(f"👕 لباس فعلی بات ذخیره شد ({len(resp.outfit)} آیتم)")

    async def _apply_saved_outfit(self) -> bool:
        saved = self._extras.get("outfit")
        if not saved:
            return False
        items = [self._dict_to_item(d) for d in saved]
        res = await self.highrise.set_outfit(outfit=items)
        if not isinstance(res, Error):
            return True
        # بعضی آیتم‌ها دیگه توی اکانت بات نیستن؛ با آیتم‌های موجود دوباره تلاش کن
        inv = await self.highrise.get_inventory()
        if isinstance(inv, Error):
            return False
        owned = {i.id for i in inv.items}
        keep = [i for i in items if i.id in owned or i.type in _BASIC_OUTFIT_TYPES]
        res = await self.highrise.set_outfit(outfit=keep)
        return not isinstance(res, Error)

    async def cmd_restoreoutfit(self, user, args):
        if not self._extras.get("outfit"):
            return await self._say("❌ هنوز لباسی ذخیره نشده. اول !saveoutfit")
        ok = await self._apply_saved_outfit()
        await self._say("👕 لباس ذخیره‌شده اعمال شد" if ok else "❌ نتونستم لباس رو اعمال کنم")

    async def _restore_outfit_on_start(self):
        await asyncio.sleep(4)
        if self.copy_outfit_enabled or not self._extras.get("outfit"):
            return
        try:
            if await self._apply_saved_outfit():
                print("👕 لباس ذخیره‌شده‌ی بات اعمال شد")
        except Exception as e:
            print(f"outfit restore error: {e}")

    # ───────────────────────── games & cool features ─────────────────────────
    async def cmd_roll(self, user, args):
        import random
        max_val = 6
        if args and _digits(args[0]).isdigit():
            max_val = max(2, min(1000, int(_digits(args[0]))))
        val = random.randint(1, max_val)
        await self._say(f"🎲 @{user.username} تاس انداخت: [{val}] (از ۱ تا {max_val})")

    async def cmd_flip(self, user, args):
        import random
        res = random.choice(["شیر 🦁", "خط ⚡"])
        await self._say(f"🪙 سکه انداخته شد برای @{user.username}: {res} اومد!")

    async def cmd_eightball(self, user, args):
        import random
        if not args:
            return await self._say(f"🎱 @{user.username} سوالت چیه؟ مثال: !8ball آیا امروز خوش‌شانسم؟")
        answers = [
            "شک نکن! صد در صد ✅", "احتمالش خیلی بالاست ✨", "شاید بله، شاید نه 🤔",
            "اصلاً روش حساب نکن ❌", "کائنات باهات یاره 🌟", "بهتره الان فکرشو نکنی 🔮",
            "نشانه‌ها مثبت هستن 🟢", "خیلی بعیده 🤷‍♂️", "حتماً اتفاق می‌افته 🎯"
        ]
        q = ' '.join(args)[:35]
        await self._say(f"🎱 پاسخ گوی جادویی به @{user.username}: {random.choice(answers)}")

    async def cmd_love(self, user, args):
        import random, hashlib
        if not args:
            return await self._say(f"❌ مثال: !love @username")
        target_name = args[0].lstrip('@').lower()
        seed = ''.join(sorted([user.username.lower(), target_name]))
        score = (int(hashlib.md5(seed.encode()).hexdigest(), 16) % 101)
        hearts = '❤️' * (score // 20) + '🤍' * (5 - (score // 20))
        comment = "عشق ابدی! 💍" if score > 80 else ("زوج فوق‌العاده 😍" if score > 50 else "فعلاً در حد دوست بمونید 😅")
        msg = f"💘 هماهنگی عشق بین @{user.username} و @{target_name}: {score}% [{hearts}] - {comment}"
        await self._say(msg)

    async def cmd_truth(self, user, args):
        import random
        truths = [
            "بزرگ‌ترین رازی که تاحالا به کسی نگفتی چیه؟",
            "اگه یک روز نامرئی بشی اولین کاری که می‌کنی چیه؟",
            "عجیب‌ترین عادتی که داری چیه؟",
            "توی این روم از استایل کی بیشتر خوشت میاد؟",
            "بامزه‌ترین یا خجالت‌آورترین سوتی که دادی چی بوده؟"
        ]
        t = random.choice(truths)
        await self._say(f"🤔 سوال حقیقت برای @{user.username}: {t}")

    async def cmd_dare(self, user, args):
        import random
        dares = [
            "همین الان یک دنس خنده‌دار برای ۳۰ ثانیه برو!",
            "به یکی از افراد حاضر در روم یه تعارف یا تعریف خیلی بامزه بکن!",
            "توی چت روم با حروف برعکس یک پیام بنویس!",
            "به بات بگو !hug و بغلش کن!",
            "به مدت ۱ دقیقه فقط با ایموجی چت کن!"
        ]
        d = random.choice(dares)
        await self._say(f"🔥 چالش شجاعت برای @{user.username}: {d}")

    async def cmd_syncdance(self, user, args):
        import random
        dance_name = args[0] if args else random.choice(["dance-tiktok11", "dance-macarena", "dance-shoppingcart", "dance-russian"])
        try:
            await self.highrise.send_emote(dance_name)
            await self._say(f"💃🎶 پارتی شروع شد! دنس همگانی: {dance_name} — همه دنس بزنید!")
        except Exception:
            await self.highrise.send_emote("dance-tiktok11")
            await self._say("💃🎶 پارتی شروع شد! همه دنس بزنید!")

    # ───────────────────────── help ─────────────────────────
    async def cmd_help(self, user, args):
        topic = args[0].lower() if args else ""
        lines = HELP_TEXT.get(topic, HELP_TEXT[""])
        await self._whisper_lines(user.id, lines)

    # ───────────────────────── events ─────────────────────────
    async def on_start(self, session_metadata) -> None:
        self._install_chat_color_wrapper()
        try:
            await super().on_start(session_metadata)
        except Exception as e:
            print(f"⚠️ super on_start error: {e}")
        try:
            asyncio.create_task(self._restore_outfit_on_start())
        except Exception:
            pass
        try:
            self._start_auto_ad_task()
        except Exception:
            pass
        if self._extras.get("bot_dance_active", False):
            d_id = self._extras.get("bot_dance_id", "emote-tired")
            d_dur = float(self._extras.get("bot_dance_duration", 4.6))
            self.bot_dance_task = asyncio.create_task(self._continuous_dance_loop(d_id, d_dur))

    async def on_user_join(self, user, position) -> None:
        if self._extras.get("welcome_enabled", True):
            self.welcome_text = self._extras.get("welcome_text", "سلام @{user}! به روم ما خوش اومدی 🌱")
        else:
            self.welcome_text = ""
        await super().on_user_join(user, position)
        try:
            fp = self._freeze_pos.get(user.id)
            if fp is not None:
                await self.highrise.teleport(user.id, fp)
        except Exception:
            pass

    async def on_whisper(self, user, message: str) -> None:
        parts = message.strip().split()
        if parts and ALIAS_MAP.get(parts[0].lower()) == "help":
            if self.is_user_admin(user) or _spam_allowed(user.id):
                try:
                    await self.cmd_help(user, parts[1:])
                except Exception as e:
                    print(f"help whisper error: {e}")
            return
        await super().on_whisper(user, message)

    async def on_chat(self, user, message: str) -> None:
        msg = message.strip()
        parts = msg.split()
        cmd = ALIAS_MAP.get(parts[0].lower()) if parts and msg.startswith("!") else None
        if cmd is None:
            return await super().on_chat(user, message)

        if user.id in self.muted_users:
            return
        admin = self.is_user_admin(user)
        if not admin and not _spam_allowed(user.id):
            return
        if not _should_handle_command(user.id, msg):
            return
        self.user_name_cache[user.id] = user.username
        args = parts[1:]

        try:
            owner = self.is_owner(user)
            if cmd == "help":
                await self.cmd_help(user, args)
            elif cmd in INTERACT:
                await self.cmd_interact(user, cmd, args)
            elif cmd in ("tip", "tipall", "wallet"):
                if not owner:
                    return await self._say("⛔ فقط مالک اصلی می‌تونه تیپ بده")
                await getattr(self, "cmd_" + cmd)(user, args)
            elif cmd in ("freeze", "unfreeze"):
                if not (admin or self.is_vip(user)):
                    return await self._say("⛔ فقط ادمین یا VIP")
                await getattr(self, "cmd_" + cmd)(user, args)
            elif cmd in ("addvip", "remvip", "vips", "saveoutfit", "restoreoutfit", "patrol", "addpatrol", "clearpatrol"):
                if not admin:
                    return await self._say("⛔ فقط ادمین")
                await getattr(self, "cmd_" + cmd)(user, args)
            elif cmd in ("roll", "flip", "eightball", "love", "truth", "dare", "syncdance"):
                await getattr(self, "cmd_" + cmd)(user, args)
            elif cmd in ("botdance", "stopbotdance", "welcome", "setwelcome", "leave", "setleave"):
                if not (admin or owner):
                    return await self._say("⛔ فقط ادمین یا مالک ربات")
                if cmd == "botdance":
                    q = " ".join(args).strip()
                    if not q:
                        await self._say("❌ راهنما: !botdance <اسم، شماره، آیدی یا لینک دنس>\nمثال: !botdance 33 | !botdance anime | !botdance dance-macarena\nتوقف دنس: !stopbotdance")
                    else:
                        name, e_id = await self.start_bot_continuous_dance(q)
                        await self._say(f"💃 دنس مداوم ربات روی «{name}» ({e_id}) تنظیم و شروع شد! ✨")
                elif cmd == "stopbotdance":
                    await self.stop_bot_continuous_dance()
                    await self._say("🛑 دنس دائمی ربات متوقف شد.")
                elif cmd == "welcome":
                    sub = args[0].lower() if args else ""
                    if sub in ("on", "1", "روشن", "فعال"):
                        self._extras["welcome_enabled"] = True
                        self._save_extras()
                        await self._say("🎉 پیام خوش‌آمدگویی ورودی فعال شد.")
                    elif sub in ("off", "0", "خاموش", "غیرفعال"):
                        self._extras["welcome_enabled"] = False
                        self._save_extras()
                        await self._say("🔇 پیام خوش‌آمدگویی ورودی غیرفعال شد.")
                elif cmd == "setwelcome":
                    new_txt = " ".join(args).strip()
                    if new_txt:
                        self._extras["welcome_text"] = new_txt
                        self._extras["welcome_enabled"] = True
                        self._save_extras()
                        await self._say(f"✅ متن ورودی تنظیم شد: {new_txt}")
                elif cmd == "leave":
                    sub = args[0].lower() if args else ""
                    if sub in ("on", "1", "روشن", "فعال"):
                        self._extras["goodbye_enabled"] = True
                        self._save_extras()
                        await self._say("👋 پیام خداحافظی خروجی فعال شد.")
                    elif sub in ("off", "0", "خاموش", "غیرفعال"):
                        self._extras["goodbye_enabled"] = False
                        self._save_extras()
                        await self._say("🔇 پیام خداحافظی خروجی غیرفعال شد.")
                elif cmd == "setleave":
                    new_txt = " ".join(args).strip()
                    if new_txt:
                        self._extras["goodbye_text"] = new_txt
                        self._extras["goodbye_enabled"] = True
                        self._save_extras()
                        await self._say(f"✅ متن خداحافظی تنظیم شد: {new_txt}")
        except Exception as e:
            print(f"Error in extras command {cmd}: {e}")
