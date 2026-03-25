import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ConversationHandler
)

from database import (
    register_user, get_bluesky_pref, update_bluesky_pref,
    get_user_realms, add_realm, remove_realm
)
from blizzard_api import BlizzardAPI

logger = logging.getLogger(__name__)

# States for ConversationHandler
AWAITING_REGION = 1
AWAITING_REALM_NAME = 2

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
    
    for region, slug, name in realms:
        keyboard.append([
            InlineKeyboardButton(f"{region.upper()}-{name}", callback_data="ignore"),
            InlineKeyboardButton("❌ Remove", callback_data=f"remove_{region}_{slug}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⚙️ **Your Configuration Menu**\n\nConfigure your tracked realms and Blizzard Support Bluesky feed alerts:"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
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
    
    parts = query.data.split('_', 2)
    if len(parts) == 3:
        _, region, slug = parts
        await remove_realm(chat_id, region, slug)
        await query.answer(f"Removed realm!")
        await show_menu(update, context)
    else:
        await query.answer("Error parsing callback.")


async def start_add_realm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to select a region."""
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.message
        
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
    
    await message.reply_text(
        "Which region is the realm in?\n"
        "Type /cancel to abort.",
        reply_markup=InlineKeyboardMarkup(region_keyboard)
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
        "Please type the name of the realm you want to add (e.g. 'Frostmourne').\n"
        "Type /cancel to abort."
    )
    return AWAITING_REALM_NAME

async def handle_realm_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text input for realm name, and add to database."""
    search_term = update.message.text.strip().lower()
    
    if search_term == '/cancel':
        return await cancel_add(update, context)

    region = context.user_data.get('adding_region', 'us')
    slug = BlizzardAPI.to_slug(search_term)
    
    chat_id = update.effective_chat.id
    
    await add_realm(chat_id, region, slug, search_term.title())
    
    await update.message.reply_text(f"✅ Added {region.upper()}-{search_term.title()} to your watchlist.")
    await show_menu(update, context)
    return ConversationHandler.END

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the realm addition flow."""
    await update.message.reply_text("Realm addition cancelled.")
    await show_menu(update, context)
    return ConversationHandler.END


def get_bot_handlers():
    """Return an array of handlers to bind to the application."""
    
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_realm, pattern='^add_realm$'),
            CommandHandler('addrealm', start_add_realm)
        ],
        states={
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
        CommandHandler("start", start),
        CommandHandler("menu", show_menu),
        conv_handler,
        CallbackQueryHandler(toggle_bsky, pattern='^toggle_bsky$'),
        CallbackQueryHandler(handle_remove_realm, pattern='^remove_'),
        CallbackQueryHandler(lambda u,c: u.callback_query.answer(), pattern='^ignore$'),
        MessageHandler(filters.TEXT | filters.COMMAND, unknown_command)
    ]
