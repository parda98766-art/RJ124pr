"""PR BOT Pro - اجراکننده مستقل تمام قابلیت‌ها (رنگ‌های چرخشی، اسپم تبلیغاتی ۱ دقیقه‌ای، ۴۰۰ دنس، تیپ، گشت‌زنی و...)"""
import asyncio
import json
import os
from highrise.__main__ import BotDefinition, main as run_bot
import prbot
import pr_extras


def load_configs():
    configs = []
    if os.path.exists("bots_config.json"):
        try:
            with open("bots_config.json", "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries = (
                raw if isinstance(raw, list)
                else ([{"room_id": k, **v} for k, v in raw.items()] if isinstance(raw, dict) else [])
            )
            for entry in entries:
                r = str(entry.get("room_id", "")).strip()
                t = str(entry.get("api_token", "")).strip()
                a = str(entry.get("admin_username", "")).strip().lstrip("@")
                if r and t and "YOUR_" not in r and "YOUR_" not in t:
                    configs.append({"room_id": r, "api_token": t, "admin_username": a or "admin"})
        except Exception as e:
            print(f"⚠️ خطا در خواندن bots_config.json: {e}")

    if not configs:
        r = os.environ.get("ROOM_ID", "").strip()
        t = os.environ.get("HIGHRISE_API_TOKEN", "").strip()
        a = os.environ.get("ADMIN_USERNAME", "admin").strip().lstrip("@")
        if r and t:
            configs.append({"room_id": r, "api_token": t, "admin_username": a})

    return configs


async def run_forever():
    prbot.start_keep_alive()
    while True:
        configs = load_configs()
        if not configs:
            print("❌ لطفاً ابتدا bots_config.json را با ROOM_ID و API_TOKEN و ADMIN_USERNAME پر کنید.")
            return

        override_room = prbot._load_room_override()
        if override_room:
            configs[0]["room_id"] = override_room
            print(f"🚪 استفاده از روم تغییریافته با !gorom: {override_room}")

        definitions = []
        for idx, cfg in enumerate(configs):
            bot = pr_extras.PRBot(
                room_id=f"{cfg['room_id']}_{idx}",
                bot_admins=[cfg["admin_username"]],
                api_token=cfg["api_token"],
                real_room_id=cfg["room_id"],
            )
            definitions.append(BotDefinition(bot, cfg["room_id"], cfg["api_token"]))

        try:
            await run_bot(definitions)
        except Exception as e:
            print(f"⚠️ اتصال قطع شد؛ تلاش مجدد تا ۵ ثانیه دیگر: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_forever())
