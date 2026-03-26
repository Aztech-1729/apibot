# bot/bot.py — AzTech API Marketplace Bot
# Users can buy any 1, 2, or all 3 APIs independently

import secrets
import asyncio
from datetime import datetime, timezone, timedelta

from pymongo import MongoClient
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler,
)

from config import (
    BOT_TOKEN, ADMIN_ID, MONGO_URI, UPI_ID, QR_IMAGE_URL, BOT_IMAGE_URL,
    CHANNEL_ID, CHANNEL_LINK, APIS, PLANS, get_api_url
)

# ── MongoDB ───────────────────────────────────────────────────────────────────
mongo      = MongoClient(MONGO_URI)
db         = mongo["aztech_api"]
users_col  = db["users"]
usage_col  = db["usage"]
orders_col = db["orders"]

# Create indexes (drop existing if conflict)
try:
    users_col.create_index("telegram_id", unique=True)
except:
    pass
try:
    users_col.create_index("api_key", unique=True, sparse=True)
except:
    pass
try:
    orders_col.create_index("order_id", unique=True)
except:
    pass

# ── Conversation states ───────────────────────────────────────────────────────
SELECT_APIS, CONFIRM_ORDER, AWAIT_SCREENSHOT, SELECT_PLAN = range(4)

# ── Helpers ───────────────────────────────────────────────────────────────────

def today():
    return datetime.now(timezone.utc).date().isoformat()

def gen_api_key():
    return "aztech_" + secrets.token_hex(16)

def gen_order_id():
    return "ORD" + secrets.token_hex(4).upper()

def get_or_create_user(tg_user):
    uid  = tg_user.id
    name = tg_user.full_name
    user = users_col.find_one({"telegram_id": uid})
    if not user:
        api_key = gen_api_key()
        users_col.insert_one({
            "telegram_id": uid,
            "name":        name,
            "api_key":     api_key,
            "plan":        "free",
            "apis":        [],           # purchased api_ids
            "active":      True,
            "joined":      datetime.now(timezone.utc),
        })
        user = users_col.find_one({"telegram_id": uid})
    return user

def get_usage_today(api_key):
    doc = usage_col.find_one({"api_key": api_key, "date": today()}) or {}
    return doc

def calc_total_price(selected_apis: list) -> int:
    return sum(APIS[a]["price_per_day"] for a in selected_apis)

async def check_channel(bot, user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status not in ("left", "kicked")
    except:
        return True

def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy API Access",   callback_data="buy")],
        [InlineKeyboardButton("🔑 My API Key",       callback_data="mykey"),
         InlineKeyboardButton("📊 My Usage",         callback_data="usage")],
        [InlineKeyboardButton("📖 API Docs",         callback_data="docs"),
         InlineKeyboardButton("💬 Support",          url="https://t.me/AzTechDeveloper")],
    ])


async def safe_show(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str, kb):
    """Edit caption if message is a photo, otherwise delete+resend as photo."""
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try:
                await update.callback_query.message.delete()
            except Exception:
                pass
            await ctx.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=BOT_IMAGE_URL,
                caption=text,
                parse_mode="HTML",
                reply_markup=kb,
            )
    else:
        await update.message.reply_photo(photo=BOT_IMAGE_URL, caption=text, parse_mode="HTML", reply_markup=kb)

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user)

    # Force join check
    if not await check_channel(ctx.bot, update.effective_user.id):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK),
            InlineKeyboardButton("✅ Verify",       callback_data="verify_join"),
        ]])
        await update.message.reply_text(
            "⚠️ <b>Join Required</b>\n\nJoin our channel to use this bot.",
            parse_mode="HTML", reply_markup=kb,
        )
        return

    text = (
        f"👋 Welcome to <b>AzTech API Marketplace</b>, {update.effective_user.first_name}!\n\n"
        f"🚀 <b>3 powerful APIs available:</b>\n"
    )
    for aid, meta in APIS.items():
        text += f"  {meta['name']} — ₹{meta['price_per_day']}/day\n"
    text += (
        f"\n✅ <b>Your account is active</b>\n"
        f"📦 Plan: <code>{user.get('plan','free').upper()}</code>\n"
        f"🔑 You have a free trial key ready!\n\n"
        f"Use the menu below to get started:"
    )
    await update.message.reply_photo(photo=BOT_IMAGE_URL, caption=text, parse_mode="HTML", reply_markup=build_main_menu())

# ── Buy flow — Step 1: Show API selection ────────────────────────────────────

async def buy_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Show buy options: Individual APIs or Subscription Plans
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy Individual APIs", callback_data="buy_apis")],
        [InlineKeyboardButton("📅 Buy Subscription Plan", callback_data="buy_plan")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])
    
    await query.message.delete()
    await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🛒 <b>Choose Purchase Type</b>\n\nSelect how you want to buy API access:\n\n🛒 <b>Individual APIs</b> — Buy specific APIs per day\n📅 <b>Subscription Plans</b> — Unlimited access to ALL APIs",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return SELECT_APIS

async def buy_apis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Reset selection
    ctx.user_data["selected_apis"] = []

    await query.message.delete()
    await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🛒 <b>Select APIs to Purchase</b>\n\n"
        "Tap to select/deselect. You can pick <b>any combination</b>:\n\n"
        + "\n".join(f"  {m['name']} — ₹{m['price_per_day']}/day  ({m['daily_limit']} req/day)"
                    for m in APIS.values())
        + "\n\n<i>Tap an API below to toggle selection:</i>",
        parse_mode="HTML",
        reply_markup=_build_api_selector([]),
    )
    return SELECT_APIS

async def buy_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Show subscription plan options
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Weekly Unlimited — ₹99/7 days", callback_data="plan_weekly")],
        [InlineKeyboardButton("📆 Monthly Unlimited — ₹299/30 days", callback_data="plan_monthly")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])
    
    await query.message.delete()
    await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📅 <b>Choose Subscription Plan</b>\n\nGet <b>UNLIMITED access</b> to ALL 3 APIs:\n🎬 Movie Search\n🎨 Image Generation\n📱 Phone Lookup\n\nSelect your plan:",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return SELECT_PLAN

def _build_api_selector(selected: list):
    rows = []
    for aid, meta in APIS.items():
        tick  = "✅ " if aid in selected else "⬜ "
        rows.append([InlineKeyboardButton(
            tick + meta["name"] + f"  ₹{meta['price_per_day']}/day",
            callback_data=f"toggle_{aid}",
        )])
    total = calc_total_price(selected)
    rows.append([InlineKeyboardButton(
        f"➡️ Proceed  (Total: ₹{total}/day)" if selected else "➡️ Proceed",
        callback_data="proceed_order",
    )])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

async def toggle_api(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    aid    = query.data.replace("toggle_", "")
    sel    = ctx.user_data.get("selected_apis", [])

    if aid in sel:
        sel.remove(aid)
    else:
        sel.append(aid)
    ctx.user_data["selected_apis"] = sel

    await query.edit_message_text(
        "🛒 <b>Select APIs to Purchase</b>\n\n"
        "Tap to select/deselect. You can pick <b>any combination</b>:\n\n"
        + "\n".join(f"  {m['name']} — ₹{m['price_per_day']}/day  ({m['daily_limit']} req/day)" for m in APIS.values())
        + "\n\n<i>Tap an API below to toggle selection:</i>",
        parse_mode="HTML",
        reply_markup=_build_api_selector(sel),
    )
    return SELECT_APIS

async def select_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_type = query.data.replace("plan_", "")
    if plan_type not in PLANS:
        await query.answer("Invalid plan", show_alert=True)
        return SELECT_PLAN
    
    plan = PLANS[plan_type]
    order_id = gen_order_id()
    ctx.user_data["order_id"] = order_id
    ctx.user_data["plan_type"] = plan_type
    ctx.user_data["order_total"] = plan["price"]
    
    summary = (
        f"📋 <b>Order Summary</b>  <code>#{order_id}</code>\n\n"
        f"📦 Plan: <b>{plan['name']}</b>\n"
        f"⏰ Duration: <b>{plan['duration_days']} days</b>\n"
        f"🚀 Features: <b>UNLIMITED access to ALL 3 APIs</b>\n\n"
        f"💰 <b>Total: ₹{plan['price']}</b>\n\n"
        f"─────────────────────\n"
        f"💳 Pay to UPI: <code>{UPI_ID}</code>\n"
        f"─────────────────────\n\n"
        f"After payment, tap <b>I've Paid</b> and send the screenshot."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I've Paid — Send Screenshot", callback_data="paid")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])
    
    # Send QR image + summary
    await query.message.delete()
    await ctx.bot.send_photo(
        chat_id   = update.effective_chat.id,
        photo     = QR_IMAGE_URL,
        caption   = summary,
        parse_mode="HTML",
        reply_markup=kb,
    )
    return CONFIRM_ORDER

# ── Buy flow — Step 2: Order summary + payment QR ────────────────────────────

async def proceed_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sel   = ctx.user_data.get("selected_apis", [])

    if not sel:
        await query.answer("⚠️ Please select at least 1 API!", show_alert=True)
        return SELECT_APIS

    total = calc_total_price(sel)
    order_id = gen_order_id()
    ctx.user_data["order_id"]    = order_id
    ctx.user_data["order_total"] = total

    lines = "\n".join(f"  • {APIS[a]['name']} — ₹{APIS[a]['price_per_day']}/day" for a in sel)
    summary = (
        f"📋 <b>Order Summary</b>  <code>#{order_id}</code>\n\n"
        f"{lines}\n\n"
        f"💰 <b>Total: ₹{total}/day</b>\n\n"
        f"─────────────────────\n"
        f"💳 Pay to UPI: <code>{UPI_ID}</code>\n"
        f"─────────────────────\n\n"
        f"After payment, tap <b>I've Paid</b> and send the screenshot."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I've Paid — Send Screenshot", callback_data="paid")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

    # Send QR image + summary
    await query.message.delete()
    await ctx.bot.send_photo(
        chat_id   = update.effective_chat.id,
        photo     = QR_IMAGE_URL,
        caption   = summary,
        parse_mode="HTML",
        reply_markup=kb,
    )
    return CONFIRM_ORDER

# ── Buy flow — Step 3: Await screenshot ──────────────────────────────────────

async def paid_pressed(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_caption(
        caption    = query.message.caption + "\n\n📷 <b>Now send your payment screenshot below:</b>",
        parse_mode = "HTML",
        reply_markup=None,
    )
    return AWAIT_SCREENSHOT

async def receive_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a <b>screenshot image</b> of your payment.",
                                        parse_mode="HTML")
        return AWAIT_SCREENSHOT

    user     = get_or_create_user(update.effective_user)
    sel      = ctx.user_data.get("selected_apis", [])
    plan_type = ctx.user_data.get("plan_type")
    total    = ctx.user_data.get("order_total", 0)
    order_id = ctx.user_data.get("order_id", gen_order_id())

    # Save order to DB
    order_data = {
        "order_id":   order_id,
        "telegram_id":update.effective_user.id,
        "name":       update.effective_user.full_name,
        "apis":       sel,
        "total":      total,
        "status":     "pending",
        "created_at": datetime.now(timezone.utc),
        "file_id":    update.message.photo[-1].file_id,
    }
    
    # Add plan_type if it's a subscription plan
    if plan_type:
        order_data["plan_type"] = plan_type
    
    orders_col.insert_one(order_data)

    # Notify admin
    if plan_type:
        # Subscription plan order
        plan = PLANS[plan_type]
        admin_text = (
            f"💰 <b>New Payment</b>  <code>#{order_id}</code>\n\n"
            f"👤 User: {update.effective_user.full_name} "
            f"(<code>{update.effective_user.id}</code>)\n"
            f"📦 Plan: <b>{plan['name']}</b>\n"
            f"⏰ Duration: <b>{plan['duration_days']} days</b>\n"
            f"🚀 Features: <b>UNLIMITED access to ALL APIs</b>\n"
            f"💵 Total: ₹{total}\n\n"
            f"Approve or reject:"
        )
    else:
        # Individual API order
        lines = "\n".join(f"  • {APIS[a]['name']}" for a in sel)
        admin_text = (
            f"💰 <b>New Payment</b>  <code>#{order_id}</code>\n\n"
            f"👤 User: {update.effective_user.full_name} "
            f"(<code>{update.effective_user.id}</code>)\n"
            f"🛒 APIs:\n{lines}\n"
            f"💵 Total: ₹{total}/day\n\n"
            f"Approve or reject:"
        )
    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
         InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{order_id}")],
    ])
    await ctx.bot.send_photo(
        chat_id      = ADMIN_ID,
        photo        = update.message.photo[-1].file_id,
        caption      = admin_text,
        parse_mode   = "HTML",
        reply_markup = admin_kb,
    )

    await update.message.reply_text(
        f"✅ <b>Screenshot received!</b>\n\n"
        f"Order <code>#{order_id}</code> is under review.\n"
        f"You'll be notified once approved (usually within a few minutes).",
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )
    ctx.user_data.clear()
    return ConversationHandler.END

# ── Admin: Approve / Reject ───────────────────────────────────────────────────

async def admin_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    action, order_id = query.data.split("_", 1)
    order = orders_col.find_one({"order_id": order_id})
    if not order:
        await query.answer("Order not found", show_alert=True)
        return

    tid  = order["telegram_id"]
    sel  = order["apis"]
    user = users_col.find_one({"telegram_id": tid})

    if action == "approve":
        # Check if this is a subscription plan order
        plan_type = order.get("plan_type")
        
        if plan_type:
            # Subscription plan approval
            plan = PLANS[plan_type]
            all_apis = list(APIS.keys())
            expires_at = datetime.now(timezone.utc) + timedelta(days=plan["duration_days"])
            
            users_col.update_one({"telegram_id": tid}, {"$set": {
                "apis":       all_apis,
                "plan":       plan_type,
                "expires_at": expires_at,
                "active":     True,
            }})
            orders_col.update_one({"order_id": order_id}, {"$set": {"status": "approved"}})
            
            await ctx.bot.send_message(
                chat_id    = tid,
                text       = (
                    f"🎉 <b>Payment Approved!</b>\n\n"
                    f"Your <b>{plan['name']}</b> is now active for <b>{plan['duration_days']} days</b>!\n\n"
                    f"🚀 You have <b>UNLIMITED access</b> to ALL 3 APIs:\n"
                    f"  ✅ {APIS['movie_search']['name']}\n"
                    f"  ✅ {APIS['image_gen']['name']}\n"
                    f"  ✅ {APIS['phone_lookup']['name']}\n\n"
                    f"Use /mykey to get your API key and /docs for integration guide."
                ),
                parse_mode = "HTML",
                reply_markup=build_main_menu(),
            )
        else:
            # Individual API approval
            existing   = set(user.get("apis", []))
            new_apis   = list(existing | set(sel))
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

            users_col.update_one({"telegram_id": tid}, {"$set": {
                "apis":       new_apis,
                "plan":       "paid",
                "expires_at": expires_at,
                "active":     True,
            }})
            orders_col.update_one({"order_id": order_id}, {"$set": {"status": "approved"}})

            lines = "\n".join(f"  ✅ {APIS[a]['name']}  ({APIS[a]['daily_limit']} req/day)" for a in sel)
            await ctx.bot.send_message(
                chat_id    = tid,
                text       = (
                    f"🎉 <b>Payment Approved!</b>\n\n"
                    f"Your APIs are now active for <b>24 hours</b>:\n{lines}\n\n"
                    f"Use /mykey to get your API key and /docs for integration guide."
                ),
                parse_mode = "HTML",
                reply_markup=build_main_menu(),
            )
        await query.edit_message_caption(
            caption    = query.message.caption + "\n\n✅ <b>APPROVED</b>",
            parse_mode = "HTML",
        )

    elif action == "reject":
        orders_col.update_one({"order_id": order_id}, {"$set": {"status": "rejected"}})
        await ctx.bot.send_message(
            chat_id    = tid,
            text       = (
                f"❌ <b>Payment Rejected</b>\n\n"
                f"We couldn't verify your payment for order <code>#{order_id}</code>.\n"
                f"Please try again or contact @AzTechDeveloper."
            ),
            parse_mode = "HTML",
            reply_markup=build_main_menu(),
        )
        await query.edit_message_caption(
            caption    = query.message.caption + "\n\n❌ <b>REJECTED</b>",
            parse_mode = "HTML",
        )

# ── /mykey ────────────────────────────────────────────────────────────────────

async def mykey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = get_or_create_user(update.effective_user)
    api_key = user.get("api_key", "N/A")
    plan    = user.get("plan", "free")
    apis    = user.get("apis", [])
    exp     = user.get("expires_at")
    exp_str = exp.strftime("%Y-%m-%d %H:%M UTC") if exp else "N/A"

    # Display plan name for subscription plans
    if plan in PLANS:
        plan_display = PLANS[plan]["name"]
        api_lines = "  ✅ ALL 3 APIs (UNLIMITED access)"
    else:
        plan_display = plan.upper()
        api_lines = "\n".join(f"  ✅ {APIS[a]['name']}" for a in apis) if apis else "  (none — free trial only)"

    text = (
        f"🔑 <b>Your API Key</b>\n\n"
        f"<code>{api_key}</code>\n\n"
        f"📦 Plan: <b>{plan_display}</b>\n"
        f"⏰ Expires: <b>{exp_str}</b>\n\n"
        f"🛒 Purchased APIs:\n{api_lines}\n\n"
        f"<b>How to use:</b>\n"
        f"Add header: <code>x-api-key: {api_key}</code>\n"
        f"Base URL: <code>{get_api_url()}</code>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy More APIs", callback_data="buy")],
        [InlineKeyboardButton("📖 API Docs",      callback_data="docs")],
        [InlineKeyboardButton("🔄 Revoke Key",   callback_data="revoke_key")],
        [InlineKeyboardButton("� Back to Menu", callback_data="menu")],
    ])
    await safe_show(update, ctx, text, kb)

# ── /usage ────────────────────────────────────────────────────────────────────

async def usage_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = get_or_create_user(update.effective_user)
    api_key = user.get("api_key")
    doc     = get_usage_today(api_key)
    plan    = user.get("plan", "free")
    purchased = user.get("apis", [])
    
    # Check if user is admin or has unlimited plan
    is_admin = user.get("telegram_id") == ADMIN_ID
    is_unlimited = plan in PLANS or is_admin
    
    lines = []
    for aid, meta in APIS.items():
        is_owned = aid in purchased or plan == "free" or is_unlimited or is_admin
        
        if is_admin:
            # Admin - truly unlimited
            used = doc.get(aid, 0)
            bar = "██████████"  # Full bar for unlimited
            icon = "👑"  # Crown for admin
            lines.append(f"{icon} {meta['name']}\n   {used}/UNLIMITED ♾️")
        elif is_unlimited:
            # Unlimited access for subscription plans
            limit = PLANS[plan]["daily_limit"]
            used = doc.get(aid, 0)
            bar = "██████████"  # Full bar for unlimited
            icon = "✅"
            lines.append(f"{icon} {meta['name']}\n   {used}/UNLIMITED  [{bar}]")
        else:
            # Regular limits for free/paid plans
            limit = meta["free_limit"] if plan == "free" else (meta["daily_limit"] if is_owned else 0)
            used = doc.get(aid, 0)
            bar = "█" * min(10, int((used / limit) * 10)) + "░" * max(0, 10 - int((used / limit) * 10)) if limit else "──────────"
            icon = "✅" if is_owned else "🔒"
            lines.append(f"{icon} {meta['name']}\n   {used}/{limit}  [{bar}]")
    
    if is_admin:
        text = (
            f"📊 <b>Admin Usage Stats</b>  ({today()})\n\n"
            + "\n\n".join(lines)
            + f"\n\n👑 <b>Admin Mode:</b> Unlimited access!"
        )
    else:
        text = (
            f"📊 <b>Today's API Usage</b>  ({today()})\n\n"
            + "\n\n".join(lines)
            + f"\n\n🔄 Resets at midnight UTC"
        )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy More", callback_data="buy")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")],
    ])

    await safe_show(update, ctx, text, kb)

# ── /docs ─────────────────────────────────────────────────────────────────────

async def docs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = get_or_create_user(update.effective_user)
    api_key = user.get("api_key", "YOUR_KEY")
    base    = get_api_url()

    text = (
        f"📖 <b>AzTech API Documentation</b>\n\n"
        f"🔗 Base URL: <code>{base}</code>\n"
        f"🔑 Auth header: <code>x-api-key: YOUR_KEY</code>\n\n"

        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>1. Movie Search</b>  (₹10/day)\n"
        f"<code>GET {base}/search</code>\n"
        f"Params:\n"
        f"  <code>q</code> — movie/show name (required)\n"
        f"  <code>source</code> — terabox | gdrive | both\n"
        f"  <code>max_results</code> — 1-20 (default 10)\n"
        f"Example:\n"
        f"<code>curl -H 'x-api-key: {api_key}' '{base}/search?q=RRR&source=both'</code>\n\n"

        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎨 <b>2. Image Generation</b>  (₹15/day)\n"
        f"<code>POST {base}/generate</code>\n"
        f"Params: <code>prompt</code> (required), <code>width</code>, <code>height</code>, <code>steps</code> (1-8)\n"
        f"Example:\n"
        f"<code>curl -X POST -H 'x-api-key: {api_key}' '{base}/generate?prompt=sunset' --output image.png</code>\n\n"

        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>3. Phone Lookup</b>  (₹20/day)\n"
        f"<code>GET {base}/lookup</code>\n"
        f"Params: <code>number</code> — 10-digit Indian mobile\n"
        f"Example:\n"
        f"<code>curl -H 'x-api-key: {api_key}' '{base}/lookup?number=9876543210'</code>\n\n"

        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Usage Stats:</b> <code>GET {base}/usage</code>\n\n"
        f"⚠️ Rate limits reset daily at midnight UTC\n"
        f"💬 Support: @AzTechDeveloper"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy APIs", callback_data="buy"),
         InlineKeyboardButton("🔑 My Key",  callback_data="mykey")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")],
    ])
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

# ── Admin commands ────────────────────────────────────────────────────────────

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total_users    = users_col.count_documents({})
    paid_users     = users_col.count_documents({"plan": "paid"})
    pending_orders = orders_col.count_documents({"status": "pending"})

    text = (
        f"⚙️ <b>Admin Panel</b>\n\n"
        f"👥 Total users: <b>{total_users}</b>\n"
        f"💎 Paid users: <b>{paid_users}</b>\n"
        f"⏳ Pending orders: <b>{pending_orders}</b>\n\n"
        f"Commands:\n"
        f"/setlimit &lt;tg_id&gt; &lt;api&gt; &lt;limit&gt; — override daily limit\n"
        f"/revoke &lt;tg_id&gt; — disable a user's key\n"
        f"/givekey &lt;tg_id&gt; &lt;api1,api2&gt; — grant free access\n"
        f"/stats — full usage stats\n"
        f"/broadcast &lt;message&gt; — message all users"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_revoke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not ctx.args:
        await update.message.reply_text("Usage: /revoke <telegram_id>"); return
    tid = int(ctx.args[0])
    users_col.update_one({"telegram_id": tid}, {"$set": {"active": False, "plan": "free", "apis": []}})
    await update.message.reply_text(f"✅ User {tid} revoked.")
    try:
        await ctx.bot.send_message(tid, "⚠️ Your API access has been revoked. Contact @AzTechDeveloper.")
    except: pass

async def cmd_givekey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /givekey <tg_id> <api1,api2,...>\nAPIs: movie_search, image_gen, phone_lookup"); return
    tid      = int(ctx.args[0])
    api_list = [a.strip() for a in ctx.args[1].split(",") if a.strip() in APIS]
    expires  = datetime.now(timezone.utc) + timedelta(hours=24)
    users_col.update_one({"telegram_id": tid}, {"$set": {
        "apis": api_list, "plan": "paid", "active": True, "expires_at": expires,
    }})
    await update.message.reply_text(f"✅ Granted {api_list} to {tid} for 24h.")
    try:
        lines = "\n".join(f"  ✅ {APIS[a]['name']}" for a in api_list)
        await ctx.bot.send_message(tid,
            f"🎁 <b>Free Access Granted!</b>\n\n{lines}\n\nActive for 24 hours. Use /mykey to get your key.",
            parse_mode="HTML")
    except: pass

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    t = today()
    docs = list(usage_col.find({"date": t}))
    totals = {aid: sum(d.get(aid, 0) for d in docs) for aid in APIS}
    lines  = "\n".join(f"  {APIS[aid]['name']}: <b>{cnt}</b> calls" for aid, cnt in totals.items())
    await update.message.reply_text(
        f"📊 <b>Today's Stats</b>  ({t})\n\n{lines}\n\n"
        f"Active keys today: <b>{len(docs)}</b>",
        parse_mode="HTML",
    )

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not ctx.args:
        await update.message.reply_text("Usage: /broadcast <message>"); return
    msg  = " ".join(ctx.args)
    uids = [u["telegram_id"] for u in users_col.find({}, {"telegram_id": 1})]
    ok   = 0
    for uid in uids:
        try:
            await ctx.bot.send_message(uid, f"📢 <b>Announcement</b>\n\n{msg}", parse_mode="HTML")
            ok += 1
        except: pass
    await update.message.reply_text(f"✅ Sent to {ok}/{len(uids)} users.")

# ── Misc callbacks ────────────────────────────────────────────────────────────

async def verify_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_channel(ctx.bot, update.effective_user.id):
        await query.edit_message_text("✅ Verified! Use /start to begin.", parse_mode="HTML")
    else:
        await query.answer("⚠️ You haven't joined yet!", show_alert=True)

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.message.delete()
    await ctx.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=BOT_IMAGE_URL,
        caption="❌ Cancelled. Choose an option:",
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )
    return ConversationHandler.END

async def revoke_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle revoke key button - generates a new API key for the user"""
    query = update.callback_query
    await query.answer()
    
    user = get_or_create_user(update.effective_user)
    old_key = user.get("api_key", "N/A")
    new_key = gen_api_key()
    
    # Update the user's API key
    users_col.update_one(
        {"telegram_id": update.effective_user.id},
        {"$set": {"api_key": new_key}}
    )
    
    text = (
        f"✅ <b>API Key Regenerated!</b>\n\n"
        f"Old Key: <code>{old_key}</code>\n"
        f"New Key: <code>{new_key}</code>\n\n"
        f"⚠️ Your old key is now invalid. Please update your integration with the new key."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to My Key", callback_data="mykey")],
    ])
    
    await query.message.delete()
    await ctx.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=BOT_IMAGE_URL,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb,
    )

async def button_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "mykey":
        await mykey(update, ctx)
    elif data == "usage":
        await usage_cmd(update, ctx)
    elif data == "docs":
        await docs_cmd(update, ctx)
    elif data == "revoke_key":
        await revoke_key(update, ctx)
    elif data == "menu":
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_media(
                media=InputMediaPhoto(media=BOT_IMAGE_URL, caption="🏠 <b>Main Menu</b>\n\nWelcome back! Choose an option below:", parse_mode="HTML"),
                reply_markup=build_main_menu()
            )
        except Exception:
            # Message is plain text (not a photo), send a new photo message instead
            await update.callback_query.message.delete()
            await ctx.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=BOT_IMAGE_URL,
                caption="🏠 <b>Main Menu</b>\n\nWelcome back! Choose an option below:",
                parse_mode="HTML",
                reply_markup=build_main_menu(),
            )

# ── Auto-expire premium ───────────────────────────────────────────────────────

async def expire_loop():
    while True:
        await asyncio.sleep(60 * 10)   # check every 10 min
        now     = datetime.now(timezone.utc)
        # Check for expired paid, weekly, and monthly plans
        expired = users_col.find({
            "plan": {"$in": ["paid", "weekly", "monthly"]},
            "expires_at": {"$lt": now}
        })
        for u in expired:
            users_col.update_one({"_id": u["_id"]}, {"$set": {"plan": "free", "apis": []}})
            print(f"[Expire] Reverted {u['telegram_id']} to free")

async def post_init(app):
    asyncio.create_task(expire_loop())

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🔌 Connecting to MongoDB...")
    try:
        mongo.server_info()
        print("✅ MongoDB connected")
    except Exception as e:
        print(f"❌ MongoDB failed: {e}"); exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Buy conversation
    # Shared nav handlers reusable inside conversation states
    nav_handlers = [
        CallbackQueryHandler(button_router, pattern="^(mykey|usage|docs|menu)$"),
        CallbackQueryHandler(cancel,        pattern="^cancel$"),
    ]

    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_start, pattern="^buy$")],
        states={
            SELECT_APIS:      [CallbackQueryHandler(buy_apis,       pattern="^buy_apis$"),
                               CallbackQueryHandler(buy_plan,       pattern="^buy_plan$"),
                               CallbackQueryHandler(toggle_api,     pattern="^toggle_"),
                               CallbackQueryHandler(proceed_order,  pattern="^proceed_order$")]
                              + nav_handlers,
            SELECT_PLAN:      [CallbackQueryHandler(select_plan,    pattern="^plan_")]
                              + nav_handlers,
            CONFIRM_ORDER:    [CallbackQueryHandler(paid_pressed,   pattern="^paid$")]
                              + nav_handlers,
            AWAIT_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)]
                              + nav_handlers,
        },
        fallbacks=[CallbackQueryHandler(buy_start, pattern="^buy$")] + nav_handlers,
        per_user=True, per_chat=True,
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("mykey",     mykey))
    app.add_handler(CommandHandler("usage",     usage_cmd))
    app.add_handler(CommandHandler("docs",      docs_cmd))
    app.add_handler(CommandHandler("admin",     admin_panel))
    app.add_handler(CommandHandler("revoke",    cmd_revoke))
    app.add_handler(CommandHandler("givekey",   cmd_givekey))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    app.add_handler(buy_conv)
    app.add_handler(CallbackQueryHandler(verify_join,   pattern="^verify_join$"))
    app.add_handler(CallbackQueryHandler(admin_action,  pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(button_router, pattern="^(mykey|usage|docs|menu|revoke_key)$"))

    print("🤖 Bot running...")
    app.run_polling()
