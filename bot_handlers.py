import asyncio
import logging
import warnings
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ConversationHandler
)
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

from database import (
    register_user, get_bluesky_pref, update_bluesky_pref,
    get_user_realms, add_realm, remove_realm,
    get_admin, get_total_users, get_total_realms
)
from blizzard_api import BlizzardAPI

logger = logging.getLogger(__name__)

# States for ConversationHandler
AWAITING_VERSION = 1
AWAITING_REGION = 2
AWAITING_REALM_NAME = 3

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler. Registers user and shows welcome menu."""
    user = update.effective_user
    await register_user(update.effective_chat.id)
    
    welcome_text = (
        f"Welcome {user.first_name} to the WoW Realm Monitor!\n\n"
        "I will send you alerts when your configured realms go offline or come back online.\n\n"
        "Use /menu to manage your realms and Bluesky feed preferences."
    )
    await update.message.reply_text(welcome_text)
    await show_menu(update, context)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the main configuration menu."""
    chat_id = update.effective_chat.id
    message = update.message if update.message else update.callback_query.message
    
    # Ensure user exists before displaying/modifying preferences
    await register_user(chat_id)
    
    realms = await get_user_realms(chat_id)
    bsky_pref = await get_bluesky_pref(chat_id)
    
    bsky_display = {
        'none': '🔕 Off',
        'maintenance': '🛠 Maintenance Only',
        'all': '📢 All Feeds'
    }.get(bsky_pref, 'Off')

    keyboard = [
        [InlineKeyboardButton("➕ Add Realm", callback_data="add_realm")],
        [InlineKeyboardButton(f"🐦 Support Feed: {bsky_display}", callback_data="toggle_bsky")]
    ]
    
    for region, slug, name, game_version in realms:
        v_tag = f"[{game_version.title().replace('-', ' ')}] "
        keyboard.append([
            InlineKeyboardButton(f"{v_tag}{region.upper()}-{name.title()}", callback_data="ignore"),
            InlineKeyboardButton("❌ Remove", callback_data=f"remove_{region}_{slug}_{game_version}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⚙️ **Your Configuration Menu**\n\nConfigure your tracked realms and Blizzard Support Bluesky feed alerts:"

    if update.callback_query:
        import telegram.error
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.error("Failed to edit menu: %s", e)
        await update.callback_query.answer()
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def toggle_bsky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle the bluesky preference."""
    query = update.callback_query
    chat_id = update.effective_chat.id
    
    current_pref = await get_bluesky_pref(chat_id)
    next_pref = {
        'none': 'maintenance',
        'maintenance': 'all',
        'all': 'none'
    }.get(current_pref, 'none')
    
    await update_bluesky_pref(chat_id, next_pref)
    await show_menu(update, context)

async def handle_remove_realm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a realm from the user's list."""
    query = update.callback_query
    chat_id = update.effective_chat.id
    
    parts = query.data.split('_', 3)
    if len(parts) == 4:
        _, region, slug, game_version = parts
        await remove_realm(chat_id, region, slug, game_version)
        await query.answer(f"Removed realm!")
        await show_menu(update, context)
    else:
        await query.answer("Error parsing callback.")


async def start_add_realm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select a game version."""
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
        
    version_keyboard = [
        [
            InlineKeyboardButton("Retail", callback_data="selectversion_retail"),
            InlineKeyboardButton("Classic", callback_data="selectversion_classic")
        ],
        [
            InlineKeyboardButton("Classic Era / SoD", callback_data="selectversion_classic-era")
        ]
    ]
    
    await message.reply_text(
        "Which Game Version is the realm in?\n"
        "Type /cancel to abort.",
        reply_markup=InlineKeyboardMarkup(version_keyboard)
    )
    return AWAITING_VERSION

async def select_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle game version selection, prompt for region."""
    query = update.callback_query
    await query.answer()
    
    version = query.data.split('_')[1]
    context.user_data['adding_version'] = version
    
    region_keyboard = [
        [
            InlineKeyboardButton("US", callback_data="selectregion_us"),
            InlineKeyboardButton("EU", callback_data="selectregion_eu")
        ],
        [
            InlineKeyboardButton("KR", callback_data="selectregion_kr"),
            InlineKeyboardButton("TW", callback_data="selectregion_tw")
        ]
    ]
    
    v_display = version.title().replace('-', ' ')
    await query.message.reply_text(
        f"Selected **{v_display}**.\n"
        "Which region is the realm in?\n"
        "Type /cancel to abort.",
        reply_markup=InlineKeyboardMarkup(region_keyboard),
        parse_mode="Markdown"
    )
    return AWAITING_REGION

async def select_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle region selection, prompt for realm name."""
    query = update.callback_query
    await query.answer()
    
    region = query.data.split('_')[1]
    context.user_data['adding_region'] = region
    
    await query.message.reply_text(
        f"You selected {region.upper()}.\n"
        "Please type the name of the realm you want to add (e.g. 'Frostmourne', 'Arugal').\n"
        "Type /cancel to abort."
    )
    return AWAITING_REALM_NAME

async def handle_realm_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text input for realm name, and add to database."""
    search_term = update.message.text.strip().lower()
    
    if search_term == '/cancel':
        return await cancel_add(update, context)

    version = context.user_data.get('adding_version', 'retail')
    region = context.user_data.get('adding_region', 'us')
    
    # Process validation
    from database import is_realm_index_expired, update_realm_index, find_known_realm
    
    expired = await is_realm_index_expired(region, version)
    if expired:
        monitor = context.bot_data.get('monitor')
        if monitor and monitor.api:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                realms = await monitor.api.fetch_realm_index(session, region, version)
                if realms:
                    await update_realm_index(region, version, realms)
                    
    match = await find_known_realm(region, version, search_term)
    if not match:
        await update.message.reply_text(
            f"❌ Realm '{search_term.title()}' not found in {region.upper()} {version.title()}.\n"
            "Please check your spelling and try again. Use /cancel to abort."
        )
        return AWAITING_REALM_NAME
        
    slug, official_name = match
    official_name = official_name.title()
    
    chat_id = update.effective_chat.id
    
    await add_realm(chat_id, region, slug, official_name, version)
    
    v_tag = f"[{version.title()}] " if version != "retail" else ""
    await update.message.reply_text(f"✅ Added {v_tag}{region.upper()}-{official_name} to your watchlist.")
    await show_menu(update, context)
    return ConversationHandler.END

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the realm addition flow."""
    await update.message.reply_text("Realm addition cancelled.")
    await show_menu(update, context)
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin stats."""
    admin_id = await get_admin()
    if update.effective_chat.id != admin_id:
        return
        
    monitor = context.bot_data.get('monitor')
    if not monitor:
        await update.message.reply_text("Stats are currently unavailable.")
        return
        
    stats_data = monitor.get_stats()
    total_users = await get_total_users()
    total_realms = await get_total_realms()
    
    msg = (
        "📊 **Bot Statistics**\n\n"
        f"⏱ **Uptime:** `{stats_data['uptime']}`\n"
        f"👥 **Users Tracking:** `{total_users}`\n"
        f"🌍 **Realms Tracked:** `{total_realms}`\n"
        f"🔥 **Blizzard RPM:** `{stats_data['blizzard_rpm']}` requests/min\n"
        f"🐦 **Bluesky RPM:** `{stats_data['bluesky_rpm']}` requests/min"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")


async def check_realm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check a specific realm's status inline."""
    if not context.args:
        await update.message.reply_text("Usage: /check <version>-<region>-<realmname>\nExample: /check retail-us-Frostmourne")
        return
        
    query = " ".join(context.args).strip()
    parts = query.split("-")
    
    valid_versions = ['retail', 'classic', 'classic-era', 'sod']
    if parts[0].lower() in valid_versions:
        version = parts.pop(0).lower()
        if version == 'sod':
            version = 'classic-era'
    else:
        version = 'retail'
        
    if len(parts) < 2:
        await update.message.reply_text("Invalid format. Use `[version]-<region>-<realmname>` (e.g. `us-Frostmourne` or `classic-eu-Firemaw`)", parse_mode="Markdown")
        return
        
    region = parts.pop(0).lower()
    valid_regions = ['us', 'eu', 'kr', 'tw']
    if region not in valid_regions:
        await update.message.reply_text(f"Invalid region '{region}'. Valid options: {', '.join(valid_regions)}")
        return
        
    search_term = "-".join(parts).lower()
    
    from database import is_realm_index_expired, update_realm_index, find_known_realm
    
    expired = await is_realm_index_expired(region, version)
    monitor = context.bot_data.get('monitor')
    
    if not monitor or not monitor.api:
        await update.message.reply_text("Bot API is currently unavailable.")
        return
        
    if expired:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            realms = await monitor.api.fetch_realm_index(session, region, version)
            if realms:
                await update_realm_index(region, version, realms)
                
    match = await find_known_realm(region, version, search_term)
    if not match:
        await update.message.reply_text(
            f"❌ Realm '{search_term.title()}' not found in {region.upper()} {version.title()}.\n"
            "Please check your spelling and try again."
        )
        return
        
    slug, official_name = match
    official_name = official_name.title()
    
    import aiohttp
    from datetime import datetime, timezone
    
    status_msg = await update.message.reply_text(f"⏳ Checking {region.upper()}-{official_name}...")
    
    async with aiohttp.ClientSession() as session:
        realm_data, _ = await monitor.api.get_realm_status(session, region, slug, version)
        
    if not realm_data:
        await status_msg.edit_text(f"❌ Failed to fetch data for {region.upper()}-{official_name}.")
        return
        
    status = realm_data.get("status")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    v_tag = f"[{version.title()}] " if version != "retail" else ""
    
    if status == "UP":
        msg = f"🟢 <b>Realm {v_tag}\"{official_name}\" ({region.upper()}) is ONLINE</b>\n🕐 {now}"
    else:
        msg = f"🔴 <b>Realm {v_tag}\"{official_name}\" ({region.upper()}) is OFFLINE</b>\n🕐 {now}"
        
    await status_msg.edit_text(msg, parse_mode="HTML")


def get_bot_handlers():
    """Return an array of handlers to bind to the application."""
    
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_realm, pattern='^add_realm$'),
            CommandHandler('addrealm', start_add_realm)
        ],
        states={
            AWAITING_VERSION: [
                CallbackQueryHandler(select_version, pattern='^selectversion_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_add)
            ],
            AWAITING_REGION: [
                CallbackQueryHandler(select_region, pattern='^selectregion_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_add)
            ],
            AWAITING_REALM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_realm_name)]
        },
        fallbacks=[CommandHandler('cancel', cancel_add)]
    )
    
    async def unknown_command(update, context):
        await update.message.reply_text("Sorry, I didn't understand that. Use /menu to manage realms, or /addrealm to add a new one.")

    return [
        CommandHandler("check", check_realm),
        CommandHandler("start", start),
        CommandHandler("menu", show_menu),
        CommandHandler("stats", stats),
        conv_handler,
        CallbackQueryHandler(toggle_bsky, pattern='^toggle_bsky$'),
        CallbackQueryHandler(handle_remove_realm, pattern='^remove_'),
        CallbackQueryHandler(lambda u,c: u.callback_query.answer(), pattern='^ignore$'),
        MessageHandler(filters.TEXT | filters.COMMAND, unknown_command)
    ]
