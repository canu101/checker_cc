import logging
import re
import asyncio
import random
import string
import tempfile
import threading
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import TelegramError, TimedOut
from database import DatabaseManager
from gateway_engine import GatewayEngine
from bin_service import BINService
from config import (
    BOT_TOKEN, ADMIN_ID, ADMIN_PASSWORD, SUPPORT_USERNAME,
    BOT_SIGNATURE, MAX_CARDS_REGULAR, LOG_CHANNEL_ID, STRINGS
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

db = DatabaseManager()
engine = GatewayEngine(db)
bin_service = BINService()

BANNER_PATH = os.path.join(os.path.dirname(__file__), "banner.png")
_banner_id: str | None = None


# ─────────────────────────────────────────
#  BANNER
# ─────────────────────────────────────────

async def get_banner(bot) -> str | None:
    global _banner_id
    if _banner_id:
        return _banner_id
    if not os.path.exists(BANNER_PATH):
        return None
    try:
        cached = db.get_setting('banner_file_id', '')
        if cached:
            _banner_id = cached
            return _banner_id
        msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=open(BANNER_PATH, 'rb'),
            caption="🖼 Banner cached"
        )
        _banner_id = msg.photo[-1].file_id
        db.set_setting('banner_file_id', _banner_id)
        await msg.delete()
        logger.info(f"Banner cached: {_banner_id[:20]}…")
    except Exception as e:
        logger.warning(f"Banner upload failed: {e}")
    return _banner_id


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def _btn(text, callback_data=None, url=None):
    k = {'text': text}
    if callback_data:
        k['callback_data'] = callback_data
    if url:
        k['url'] = url
    return InlineKeyboardButton(**k)

def is_admin(uid): return uid == ADMIN_ID
def is_allowed(uid): return is_admin(uid) or db.is_subscribed(uid)
def get_lang(uid): return db.get_user_language(uid)

def s(uid, key, **kw):
    lang = get_lang(uid)
    st = STRINGS.get(lang, STRINGS["ar"])
    txt = st.get(key, STRINGS["ar"].get(key, key))
    return txt.format(**kw) if kw else txt

def parse_card(text):
    for pat in [
        r'(\d{13,19})[|\s/](\d{1,2})[|\s/](\d{4})[|\s/](\d{3,4})',
        r'(\d{13,19})[|\s/](\d{1,2})[|\s/](\d{2})[|\s/](\d{3,4})',
    ]:
        m = re.match(pat, text.strip())
        if m:
            yr = m.group(3)
            if len(yr) == 2:
                yr = '20' + yr
            return {'number': m.group(1), 'month': m.group(2).zfill(2), 'year': yr, 'cvv': m.group(4)}
    return None

def progress_bar(cur, tot, w=14):
    if tot == 0:
        return "░" * w + " 0%"
    f = int((cur / tot) * w)
    return '█' * f + '░' * (w - f) + f" {int(cur/tot*100)}%"


# ─────────────────────────────────────────
#  SEND / EDIT
# ─────────────────────────────────────────

async def bot_send(bot, chat_id, caption, kb, fid=None):
    if fid:
        return await bot.send_photo(chat_id=chat_id, photo=fid, caption=caption,
                                    reply_markup=kb, parse_mode="Markdown")
    return await bot.send_message(chat_id=chat_id, text=caption, reply_markup=kb, parse_mode="Markdown")

async def bot_edit(query, caption, kb, fid=None):
    msg = query.message
    has_photo = bool(msg.photo)
    if has_photo:
        try:
            await query.edit_message_caption(caption=caption, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception:
            pass
    if fid:
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(media=fid, caption=caption, parse_mode="Markdown"),
                reply_markup=kb)
            return
        except Exception:
            pass
    try:
        await query.edit_message_text(caption, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass

async def log_channel(bot, text, fid=None):
    if not LOG_CHANNEL_ID:
        return
    try:
        if fid:
            await bot.send_photo(chat_id=LOG_CHANNEL_ID, photo=fid, caption=text, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Channel log: {e}")


# ─────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────

def kb_main(uid, is_sub, is_adm):
    if is_sub or is_adm:
        return InlineKeyboardMarkup([
            [_btn("📂 رفع كروت", callback_data="menu_upload"),
             _btn("💳 فحص كارت",  callback_data="menu_check")],
            [_btn("👤 حسابي", callback_data="menu_account"),
             _btn("📊 السجل", callback_data="menu_history")],
            [_btn("🎫 كود تفعيل", callback_data="menu_redeem")],
            [_btn("⚙️ الإعدادات", callback_data="menu_settings"),
             _btn("📞 الدعم",  url=f"https://t.me/{SUPPORT_USERNAME}")],
        ])
    return InlineKeyboardMarkup([
        [_btn("💎 اشتراك", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [_btn("🎫 كود تفعيل", callback_data="menu_redeem")],
        [_btn("📞 الدعم", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

def kb_admin(uid):
    return InlineKeyboardMarkup([
        [_btn("📊 الإحصائيات",      callback_data="admin_stats"),
         _btn("👥 المستخدمين",      callback_data="admin_users")],
        [_btn("🎫 أكواد التفعيل",  callback_data="admin_codes"),
         _btn("⚡ البوابات",        callback_data="admin_gateways")],
        [_btn("🔌 البروكسيات",     callback_data="admin_proxies"),
         _btn("📋 السجلات",        callback_data="admin_logs")],
        [_btn("⚙️ الإعدادات",      callback_data="admin_settings"),
         _btn("🌐 لوحة الويب",     url=f"https://{os.environ.get('REPLIT_DEV_DOMAIN','localhost')}:5000")],
        [_btn("🔙 رجوع", callback_data="main_menu")],
    ])

def kb_back(uid, target="main_menu"):
    return InlineKeyboardMarkup([[_btn(s(uid,"btn_back"), callback_data=target)]])


# ─────────────────────────────────────────
#  /start
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)
    uid, is_sub, is_adm = user.id, db.is_subscribed(user.id), is_admin(user.id)

    if is_adm:
        cap = s(uid, "welcome_admin", name=user.first_name)
    elif is_sub:
        u = db.get_user(uid)
        cap = s(uid, "welcome_sub", name=user.first_name, exp=u.get('subscription_expiry','---'))
    else:
        cap = s(uid, "welcome_guest", name=user.first_name, support=SUPPORT_USERNAME)

    fid = await get_banner(context.bot)
    kb  = kb_main(uid, is_sub, is_adm)
    if update.message:
        await bot_send(context.bot, uid, cap, kb, fid)
    else:
        await bot_edit(update.callback_query, cap, kb, fid)


# ─────────────────────────────────────────
#  /admin
# ─────────────────────────────────────────

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    context.user_data['awaiting_admin_pass'] = True
    fid = await get_banner(context.bot)
    await bot_send(context.bot, uid,
                   "🔐 *لوحة الأدمن*\n\nأدخل كلمة المرور:",
                   kb_back(uid), fid)


# ─────────────────────────────────────────
#  /addgateway  (wizard)
# ─────────────────────────────────────────

async def addgateway_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("⛔ للأدمن فقط.")
        return
    context.user_data['gw_step'] = 'name'
    context.user_data['gw_data'] = {}
    fid = await get_banner(context.bot)
    cancel = InlineKeyboardMarkup([[_btn("❌ إلغاء", callback_data="main_menu")]])
    await bot_send(context.bot, uid,
                   "⚡ *إضافة بوابة جديدة*\nالخطوة 1/7\n\n📌 أرسل *اسم البوابة* (داخلي):",
                   cancel, fid)


# ─────────────────────────────────────────
#  Document handler
# ─────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    doc = update.message.document

    # Proxy file upload
    if context.user_data.get('awaiting_proxy_file'):
        context.user_data['awaiting_proxy_file'] = False
        if not doc.file_name.endswith('.txt'):
            await update.message.reply_text("❌ ملفات .txt فقط.")
            return
        file = await context.bot.get_file(doc.file_id)
        data = await file.download_as_bytearray()
        lines = data.decode('utf-8', errors='ignore').splitlines()
        added = db.add_proxies_bulk(lines)
        fid = await get_banner(context.bot)
        await bot_send(context.bot, uid,
                       f"✅ *تمت إضافة البروكسيات*\n\n"
                       f"📋 الكل: `{len(lines)}`\n✅ أُضيف: `{added}`",
                       kb_back(uid, "admin_proxies"), fid)
        return

    # Card file upload
    if not is_allowed(uid):
        await update.message.reply_text(s(uid, "no_sub"))
        return
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ ملفات .txt فقط.")
        return
    if context.user_data.get('is_checking'):
        await update.message.reply_text("⏳ يوجد فحص نشط.")
        return

    file = await context.bot.get_file(doc.file_id)
    raw  = await file.download_as_bytearray()
    text = raw.decode('utf-8', errors='ignore')
    cards = [c for line in text.splitlines() if (c := parse_card(line.strip()))]

    if not cards:
        await update.message.reply_text("❌ لا توجد كروت صالحة.\nالصيغة: `NUMBER|MM|YYYY|CVV`",
                                        parse_mode="Markdown")
        return

    limit = 999999 if is_admin(uid) else MAX_CARDS_REGULAR
    if len(cards) > limit:
        await update.message.reply_text(f"❌ الحد {limit} كارت. أرسلت {len(cards)}.")
        return

    context.user_data['bulk_cards'] = cards
    context.user_data['bulk_total'] = len(cards)
    gateways = db.get_active_gateways()
    if not gateways:
        await update.message.reply_text(s(uid, "no_gateways"))
        return

    rows = [[_btn(f"⚡  {gw['button_name']}", callback_data=f"bulk_gw|{gw['id']}")] for gw in gateways]
    rows.append([_btn(s(uid,"btn_cancel"), callback_data="main_menu")])
    fid = await get_banner(context.bot)
    await bot_send(context.bot, uid,
                   f"📂 *ملف الكروت*\n\n✅ صالحة: `{len(cards)}`\n\n🌐 اختر البوابة:",
                   InlineKeyboardMarkup(rows), fid)


# ─────────────────────────────────────────
#  Text handler
# ─────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # ── Admin password ─────────────────────
    if context.user_data.get('awaiting_admin_pass'):
        await update.message.delete()
        context.user_data['awaiting_admin_pass'] = False
        if text == ADMIN_PASSWORD:
            context.user_data['is_admin_verified'] = True
            fid = await get_banner(context.bot)
            await bot_send(context.bot, uid,
                           "✅ *تم الدخول!*\nأهلاً بك في لوحة الأدمن 👑",
                           kb_admin(uid), fid)
        else:
            await update.message.reply_text(s(uid, "wrong_pass"))
        return

    # ── Code creation wizard ───────────────
    code_step = context.user_data.get('admin_code_step')
    if code_step and is_admin(uid):
        await _handle_code_wizard(update, context, text, code_step)
        return

    # ── Proxy single input ─────────────────
    if context.user_data.get('awaiting_proxy'):
        context.user_data['awaiting_proxy'] = False
        if db.add_proxy(text):
            fid = await get_banner(context.bot)
            total = db.count_active_proxies()
            await bot_send(context.bot, uid,
                           f"✅ *تمت إضافة البروكسي*\n\n`{text}`\n\n📊 المجموع: `{total}`",
                           kb_back(uid, "admin_proxies"), fid)
        else:
            await update.message.reply_text("⚠️ البروكسي موجود مسبقاً.")
        return

    # ── Redeem code ────────────────────────
    if context.user_data.get('awaiting_redeem'):
        context.user_data['awaiting_redeem'] = False
        code_str = text.upper()
        code = db.get_code(code_str)
        if not code:
            await update.message.reply_text(s(uid, "invalid_code"))
        elif code['used_count'] >= code['max_uses']:
            await update.message.reply_text(s(uid, "code_maxed"))
        else:
            db.use_code(code['id'], uid)
            hours = code.get('duration_hours') or (code.get('duration_days', 1) * 24)
            new_exp = db.extend_subscription_hours(uid, hours)
            fid = await get_banner(context.bot)
            await bot_send(context.bot, uid,
                           s(uid, "redeemed", exp=new_exp.strftime('%Y-%m-%d %H:%M')),
                           kb_main(uid, True, is_admin(uid)), fid)
        return

    # ── Card input ─────────────────────────
    if context.user_data.get('awaiting_card'):
        if not is_allowed(uid):
            await update.message.reply_text(s(uid, "no_sub"))
            return
        card = parse_card(text)
        if not card:
            await update.message.reply_text(s(uid, "invalid_format"), parse_mode="Markdown")
            return
        context.user_data['last_card']    = card
        context.user_data['awaiting_card'] = False
        gateways = db.get_active_gateways()
        if not gateways:
            await update.message.reply_text(s(uid, "no_gateways"))
            return
        rows = [[_btn(f"⚡  {gw['button_name']}", callback_data=f"gw|{gw['id']}")] for gw in gateways]
        rows.append([_btn(s(uid,"btn_cancel"), callback_data="main_menu")])
        fid = await get_banner(context.bot)
        await bot_send(context.bot, uid,
                       f"💳 `····{card['number'][-4:]}`\n\n🌐 اختر البوابة:",
                       InlineKeyboardMarkup(rows), fid)
        return

    # ── Gateway wizard ─────────────────────
    gw_step = context.user_data.get('gw_step')
    if gw_step and is_admin(uid):
        await _handle_gw_wizard(update, context, text, gw_step)
        return

    # ── Setting value input ────────────────
    if context.user_data.get('awaiting_setting_value') and is_admin(uid):
        setting_key = context.user_data['awaiting_setting_value']
        context.user_data['awaiting_setting_value'] = None
        db.set_setting(setting_key, text)
        fid = await get_banner(context.bot)
        await bot_send(context.bot, uid,
                       f"✅ *تم تحديث الإعداد*\n\n📌 `{setting_key}`\n🆔 `{text}`",
                       kb_admin(uid), fid)
        return

    # ── Default ────────────────────────────
    fid  = await get_banner(context.bot)
    user = db.get_user(uid)
    name = user.get('first_name', 'User') if user else 'User'
    await bot_send(context.bot, uid,
                   s(uid, "menu_title", name=name),
                   kb_main(uid, db.is_subscribed(uid), is_admin(uid)), fid)


# ─────────────────────────────────────────
#  Code creation wizard
# ─────────────────────────────────────────

async def _handle_code_wizard(update, context, text, step):
    uid = update.effective_user.id
    fid = await get_banner(context.bot)
    cancel = InlineKeyboardMarkup([[_btn("❌ إلغاء", callback_data="admin_codes")]])

    if step == 'hours':
        try:
            hours = int(text)
            if hours < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل رقم صحيح (ساعات).")
            return
        context.user_data['admin_code_hours'] = hours
        context.user_data['admin_code_step']  = 'uses'
        await bot_send(context.bot, uid,
                       f"🎫 *مدة الكود:* `{hours}` ساعة\n\nالخطوة 2/2\n👥 كم مرة استخدام؟",
                       cancel, fid)
        return

    if step == 'uses':
        try:
            uses = int(text)
            if uses < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ أدخل رقم صحيح.")
            return
        hours = context.user_data.get('admin_code_hours', 24)
        code  = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        db.create_code(code, '', hours, uses, uid)
        context.user_data['admin_code_step'] = None

        days_str = f"{hours//24} يوم" if hours >= 24 else f"{hours} ساعة"
        await bot_send(context.bot, uid,
                       f"✅ *تم إنشاء الكود!*\n\n"
                       f"🔑 `{code}`\n"
                       f"⏰ المدة: `{days_str}` (`{hours}` ساعة)\n"
                       f"👥 الاستخدام: `{uses}` مرة",
                       kb_admin(uid), fid)
        return


# ─────────────────────────────────────────
#  Gateway wizard
# ─────────────────────────────────────────

_GW_STEPS = ['name','button','endpoint','method','headers','body','patterns']
_GW_PROMPTS = {
    'name':     "الخطوة 2/7\n🔘 *اسم الزرار* (للمستخدم):",
    'button':   "الخطوة 3/7\n🔗 *رابط API* (endpoint):",
    'endpoint': "الخطوة 4/7\n📡 *الميثود* (POST أو GET):",
    'method':   "الخطوة 5/7\n📋 *Headers* (JSON):\nمثال: `{\"Content-Type\": \"application/json\"}`",
    'headers':  "الخطوة 6/7\n📝 *Body Template*:\nمتغيرات: `{card}` `{month}` `{year}` `{cvv}`",
    'body':     "الخطوة 7/7\n🎯 *Patterns* (success|decline|error)\nأو `skip` لتخطي:",
}
_GW_FIELDS  = ['display_name','button_name','api_endpoint','method','headers_json','body_template']

async def _handle_gw_wizard(update, context, text, step):
    import json as _json
    uid = update.effective_user.id
    gd  = context.user_data.setdefault('gw_data', {})
    fid = await get_banner(context.bot)
    cancel = InlineKeyboardMarkup([[_btn("❌ إلغاء", callback_data="main_menu")]])

    if step == 'patterns':
        if text.lower() == 'skip':
            gd['success_pattern'] = gd['decline_pattern'] = gd['error_pattern'] = ''
        else:
            parts = [p.strip() for p in text.split('|')]
            gd['success_pattern'] = parts[0] if len(parts) > 0 else ''
            gd['decline_pattern'] = parts[1] if len(parts) > 1 else ''
            gd['error_pattern']   = parts[2] if len(parts) > 2 else ''
        try:
            hdrs = _json.loads(gd.get('headers_json', '{}'))
        except Exception:
            hdrs = {}
        db.add_gateway({
            'display_name': gd.get('display_name',''),
            'button_name':  gd.get('button_name', gd.get('display_name','')),
            'endpoint':     gd.get('api_endpoint',''),
            'method':       gd.get('method','POST').upper(),
            'headers': hdrs, 'body': gd.get('body_template',''),
            'success': gd.get('success_pattern',''), 'decline': gd.get('decline_pattern',''),
            'error':   gd.get('error_pattern',''),   'timeout': 30
        })
        context.user_data['gw_step'] = None
        context.user_data['gw_data'] = {}
        await bot_send(context.bot, uid,
                       f"✅ *تمت إضافة البوابة!*\n\n"
                       f"📌 `{gd.get('display_name')}`\n"
                       f"🔗 `{gd.get('api_endpoint','')[:60]}`",
                       kb_admin(uid), fid)
        return

    idx   = _GW_STEPS.index(step)
    field = _GW_FIELDS[idx]
    gd[field] = text
    next_step  = _GW_STEPS[idx + 1]
    context.user_data['gw_step'] = next_step
    await bot_send(context.bot, uid, _GW_PROMPTS[step], cancel, fid)


# ─────────────────────────────────────────
#  Callback queries
# ─────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data   = query.data
    uid    = update.effective_user.id
    is_sub = db.is_subscribed(uid)
    is_adm = is_admin(uid)
    is_adm_v = context.user_data.get('is_admin_verified', False) or is_adm
    fid = await get_banner(context.bot)

    async def edit(cap, kb):
        await bot_edit(query, cap, kb, fid)

    # ── Main menu ──────────────────────────
    if data == "main_menu":
        context.user_data.update({'is_checking': False, 'bulk_cancel': True, 'gw_step': None,
                                   'admin_code_step': None, 'awaiting_proxy': False,
                                   'awaiting_proxy_file': False})
        user = db.get_user(uid)
        name = user.get('first_name','User') if user else 'User'
        await edit(s(uid,"menu_title",name=name), kb_main(uid, is_sub, is_adm))
        return

    if data == "menu_upload":
        await edit(s(uid,"upload_title"), kb_back(uid))
        return

    if data == "menu_check":
        context.user_data['awaiting_card'] = True
        await edit(s(uid,"check_title"), kb_back(uid))
        return

    if data == "menu_account":
        u  = db.get_user(uid)
        exp = u.get('subscription_expiry','---') if not is_adm else '♾️'
        chk = u.get('total_checks', 0) if u else 0
        st  = "👑 أدمن" if is_adm else ("✅ نشط" if is_sub else "❌ منتهي")
        await edit(
            f"┌──────────────────────┐\n│      👤  حسابي       │\n└──────────────────────┘\n\n"
            f"🆔 `{uid}`\n📌 {st}\n📅 `{exp}`\n🔢 `{chk}` فحص",
            kb_main(uid, is_sub, is_adm)
        )
        return

    if data == "menu_history":
        logs_ = db.get_user_logs(uid, 10)
        msg = "📊 *آخر الفحوصات:*\n\n" if logs_ else "📭 لا يوجد سجل."
        for l in logs_:
            icon = "✅" if "APPROVED" in l.get('result_status','') else "❌"
            msg += f"{icon} `····{l['card_last4']}` — {l['gateway_name']}\n"
        await edit(msg, kb_main(uid, is_sub, is_adm))
        return

    if data == "menu_redeem":
        context.user_data['awaiting_redeem'] = True
        await edit(s(uid,"redeem_title"), kb_back(uid))
        return

    if data == "menu_settings":
        await edit(s(uid,"settings_title"), InlineKeyboardMarkup([
            [_btn("🇸🇦  العربية", callback_data="set_lang_ar"),
             _btn("🇬🇧  English",  callback_data="set_lang_en")],
            [_btn(s(uid,"btn_back"), callback_data="main_menu")],
        ]))
        return

    if data in ("set_lang_ar","set_lang_en"):
        db.set_user_language(uid, data.split("_")[-1])
        await edit(s(uid,"lang_changed"), kb_main(uid, is_sub, is_adm))
        return

    # ── Gateway select (single) ────────────
    if data.startswith("gw|"):
        card = context.user_data.get('last_card')
        if not card:
            await edit(s(uid,"session_expired"), kb_back(uid))
            return
        await _run_single(update, context, int(data.split("|")[1]), card, fid)
        return

    # ── Gateway select (bulk) ──────────────
    if data.startswith("bulk_gw|"):
        gw_id = int(data.split("|")[1])
        context.user_data['bulk_gw'] = gw_id
        gw    = db.get_gateway_by_id(gw_id)
        total = context.user_data.get('bulk_total', 0)
        await edit(
            f"⚡ *البوابة:* `{gw['display_name']}`\n💳 الكروت: `{total}`\n\nاضغط تأكيد للبدء:",
            InlineKeyboardMarkup([
                [_btn(s(uid,"confirm_btn"),  callback_data="bulk_confirm")],
                [_btn(s(uid,"change_gw_btn"), callback_data="bulk_back"),
                 _btn(s(uid,"btn_cancel"),    callback_data="main_menu")],
            ])
        )
        return

    if data == "bulk_back":
        gateways = db.get_active_gateways()
        rows = [[_btn(f"⚡  {gw['button_name']}", callback_data=f"bulk_gw|{gw['id']}")] for gw in gateways]
        rows.append([_btn(s(uid,"btn_cancel"), callback_data="main_menu")])
        await edit(f"🌐 اختر البوابة ({context.user_data.get('bulk_total',0)} كارت):",
                   InlineKeyboardMarkup(rows))
        return

    if data == "bulk_confirm":
        await _run_bulk(update, context, fid)
        return

    if data == "bulk_cancel":
        context.user_data['bulk_cancel'] = True
        await query.answer("⏹ جاري الإيقاف…")
        return

    # ── Admin guard ────────────────────────
    if data.startswith("admin_") and not is_adm_v:
        await query.answer("⛔ ممنوع!", show_alert=True)
        return

    if data == "admin_panel":
        await edit("👑 *لوحة الأدمن*", kb_admin(uid))
        return

    if data == "admin_stats":
        stats   = db.get_stats()[:7]
        tu, au  = db.count_users(), db.count_active_users()
        gw_c    = db.count_active_gateways()
        px_c    = db.count_active_proxies()
        msg = (f"📊 *الإحصائيات*\n\n"
               f"👥 مستخدمين: `{tu}` (✅ `{au}` نشط)\n"
               f"⚡ بوابات: `{gw_c}`\n🔌 بروكسيات: `{px_c}`\n\n📈 آخر 7 أيام:\n")
        for r in stats:
            msg += f"`{r['date']}` ➜ {r['total_checks']} (✅{r['approved']} ❌{r['declined']})\n"
        await edit(msg, kb_admin(uid))
        return

    if data == "admin_users":
        await _show_users(edit, uid, page=0)
        return

    if data.startswith("admin_users_page|"):
        page = int(data.split("|")[1])
        await _show_users(edit, uid, page=page)
        return

    if data.startswith("admin_user|"):
        tid = int(data.split("|")[1])
        u   = db.get_user(tid)
        if not u:
            return
        blk = u['is_blocked']
        kb_ = InlineKeyboardMarkup([
            [_btn("➕ +24 ساعة", callback_data=f"admin_ext|{tid}|24"),
             _btn("➕ +7 أيام",  callback_data=f"admin_ext|{tid}|168")],
            [_btn("➕ +30 يوم",  callback_data=f"admin_ext|{tid}|720"),
             _btn("✏️ مخصص",    callback_data=f"admin_ext_custom|{tid}")],
            [_btn("🚫 حظر" if not blk else "✅ رفع الحظر",
                  callback_data=f"admin_blk|{tid}|{1-blk}")],
            [_btn("🔙 رجوع", callback_data="admin_users")],
        ])
        st = "🔴 محظور" if blk else ("✅ نشط" if u.get('subscription_expiry') else "⚫ بلا اشتراك")
        await edit(
            f"👤 *{u.get('first_name','---')}*\n🆔 `{tid}`\n📌 {st}\n🔢 `{u.get('total_checks',0)}` فحص",
            kb_
        )
        return

    if data.startswith("admin_ext|"):
        _, tid, hrs = data.split("|")
        new_exp = db.extend_subscription_hours(int(tid), int(hrs))
        await query.answer(f"✅ تمت الإضافة حتى {new_exp.strftime('%Y-%m-%d %H:%M')}")
        return

    # ── Custom extension input ─────────────
    if context.user_data.get('awaiting_custom_ext'):
        tid = int(context.user_data['awaiting_custom_ext'])
        context.user_data['admin_code_step']      = None
        context.user_data['awaiting_custom_ext']  = None
        await edit(f"⏰ أرسل عدد الساعات للمستخدم `{tid}`:", kb_back(uid, f"admin_user|{tid}"))
        return



    if data.startswith("admin_blk|"):
        _, tid, blk = data.split("|")
        (db.block_user if int(blk) else db.unblock_user)(int(tid))
        await query.answer("🚫 تم الحظر!" if int(blk) else "✅ رُفع الحظر!")
        return

    # ── Codes ──────────────────────────────
    if data == "admin_codes":
        await _show_codes(edit, uid)
        return

    if data == "admin_gencode":
        context.user_data['admin_code_step'] = 'hours'
        await edit(
            "🎫 *إنشاء كود تفعيل*\n\nالخطوة 1/2\n⏰ كم ساعة مدة الكود؟\n\n`24` = يوم\n`168` = أسبوع\n`720` = شهر",
            InlineKeyboardMarkup([[_btn("❌ إلغاء", callback_data="admin_codes")]])
        )
        return

    if data.startswith("admin_delcode|"):
        db.delete_code(int(data.split("|")[1]))
        await query.answer("🗑 حُذف!")
        await _show_codes(edit, uid)
        return

    # ── Gateways ───────────────────────────
    if data == "admin_gateways":
        await _show_gateways(edit, uid)
        return

    if data == "admin_gw_hint":
        await query.answer("أرسل /addgateway لإضافة بوابة", show_alert=True)
        return

    if data.startswith("admin_delgw|"):
        db.delete_gateway(int(data.split("|")[1]))
        await query.answer("🗑 حُذفت!")
        await _show_gateways(edit, uid)
        return

    # ── Proxies ────────────────────────────
    if data == "admin_proxies":
        await _show_proxies(edit, uid)
        return

    if data == "admin_proxy_add":
        context.user_data['awaiting_proxy'] = True
        await edit(
            "🔌 *إضافة بروكسي*\n\nأرسل البروكسي:\n`host:port`\n`http://user:pass@host:port`\n`socks5://host:port`",
            kb_back(uid, "admin_proxies")
        )
        return

    if data == "admin_proxy_file":
        context.user_data['awaiting_proxy_file'] = True
        await edit(
            "📁 *رفع ملف بروكسيات*\n\nأرسل ملف `.txt` (سطر لكل بروكسي)",
            kb_back(uid, "admin_proxies")
        )
        return

    if data == "admin_proxy_clear":
        db.clear_all_proxies()
        await query.answer("🗑 تم حذف كل البروكسيات!")
        await _show_proxies(edit, uid)
        return

    if data.startswith("admin_delproxy|"):
        db.delete_proxy(int(data.split("|")[1]))
        await query.answer("🗑 حُذف!")
        await _show_proxies(edit, uid)
        return

    # ── Logs ────────────────────────────────
    if data == "admin_logs":
        await _show_logs(edit, uid, page=0)
        return

    if data.startswith("admin_logs_page|"):
        page = int(data.split("|")[1])
        await _show_logs(edit, uid, page=page)
        return

    # ── Settings ─────────────────────────────
    if data == "admin_settings":
        await _show_settings(edit, uid)
        return

    if data.startswith("admin_set_setting|"):
        setting_key = data.split("|")[1]
        context.user_data['awaiting_setting_value'] = setting_key
        await edit(f"⚙️ *تعديل الإعداد*\n\n📌 `{setting_key}`\n\nأرسل القيمة الجديدة:", kb_back(uid, "admin_settings"))
        return


# ─────────────────────────────────────────
#  Admin panel helpers
# ─────────────────────────────────────────

async def _show_codes(edit_fn, uid):
    codes = db.get_all_codes()
    rows  = [[_btn("➕  إنشاء كود جديد", callback_data="admin_gencode")]]
    for c in codes:
        hrs  = c.get('duration_hours') or c.get('duration_days', 1) * 24
        used = f"{c['used_count']}/{c['max_uses']}"
        lbl  = c.get('label') or c['code']
        tag  = f"{hrs}h" if hrs < 24 else f"{hrs//24}d"
        rows.append([_btn(f"🎫 {lbl} | ⏰{tag} | [{used}]", callback_data=f"admin_delcode|{c['id']}")])
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel")])
    await edit_fn("🎫 *أكواد التفعيل:*\n_(اضغط على كود لحذفه)_", InlineKeyboardMarkup(rows))

async def _show_gateways(edit_fn, uid):
    gateways = db.get_active_gateways()
    rows = [[_btn("➕  إضافة بوابة", callback_data="admin_gw_hint")]]
    for gw in gateways:
        rows.append([_btn(f"⚡ {gw['button_name']} — {gw['display_name']}",
                          callback_data=f"admin_delgw|{gw['id']}")])
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel")])
    await edit_fn(
        "⚡ *البوابات النشطة:*\n_(اضغط للحذف)_\n\nلإضافة بوابة: /addgateway",
        InlineKeyboardMarkup(rows)
    )

async def _show_proxies(edit_fn, uid):
    proxies = db.get_active_proxies()
    count   = len(proxies)
    rows = [
        [_btn("➕  بروكسي واحد",    callback_data="admin_proxy_add"),
         _btn("📁  رفع ملف (.txt)", callback_data="admin_proxy_file")],
    ]
    for p in proxies[:10]:
        label = f"{'✅' if p['fail_count'] < 3 else '⚠️'} {p['proxy_string'][:35]}"
        rows.append([_btn(label, callback_data=f"admin_delproxy|{p['id']}")])
    if count > 10:
        rows.append([_btn(f"… و{count-10} أخرى (من لوحة الويب)", callback_data="admin_proxies")])
    rows.append([_btn("🗑  حذف الكل", callback_data="admin_proxy_clear"),
                 _btn("🔙 رجوع",       callback_data="admin_panel")])
    await edit_fn(
        f"🔌 *البروكسيات*\n\n✅ نشط: `{count}`\n_(اضغط للحذف)_",
        InlineKeyboardMarkup(rows)
    )

async def _show_logs(edit_fn, uid, page=0):
    per_page = 10
    logs = db.get_recent_logs(100)
    total_pages = (len(logs) + per_page - 1) // per_page
    page = min(page, total_pages - 1) if total_pages > 0 else 0
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_logs = logs[start_idx:end_idx]

    msg = f"📋 *سجل الفحوصات*\n\nالصفحة `{page + 1}/{total_pages or 1}`\n\n"
    for l in page_logs:
        icon = "✅" if "APPROVED" in l.get('result_status', '') else "❌"
        msg += f"{icon} `····{l['card_last4']}` — {l['gateway_name']}\n"
        msg += f"   👤 `{l['user_id']}` | 🕐 {l['created_at'][:16]}\n\n"

    rows = []
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("◀️", callback_data=f"admin_logs_page|{page-1}"))
        nav_row.append(_btn(f"{page+1}/{total_pages}", callback_data="admin_logs"))
        if page < total_pages - 1:
            nav_row.append(_btn("▶️", callback_data=f"admin_logs_page|{page+1}"))
        rows.append(nav_row)
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel")])
    await edit_fn(msg, InlineKeyboardMarkup(rows))

async def _show_settings(edit_fn, uid):
    settings = db.get_all_settings() if hasattr(db, 'get_all_settings') else []
    if not settings:
        # Fallback: get individual settings
        settings_dict = {
            'thread_count': db.get_setting('thread_count', '5'),
            'request_timeout': db.get_setting('request_timeout', '30'),
            'auto_clean_logs': db.get_setting('auto_clean_logs', '1'),
            'bot_token': '***' if db.get_setting('bot_token') else 'غير محدد',
        }
        settings = [{'key': k, 'value': v} for k, v in settings_dict.items()]

    msg = "⚙️ *إعدادات البوت*\n\n"
    rows = []
    for s in settings:
        if isinstance(s, dict):
            key = s.get('key', '')
            value = s.get('value', '')
        else:
            key, value = s
        if key == 'bot_token' and value:
            value = '***'
        msg += f"📌 `{key}`: `{value}`\n"
        rows.append([_btn(f"✏️ تعديل {key}", callback_data=f"admin_set_setting|{key}")])

    rows.append([_btn("🔙 رجوع", callback_data="admin_panel")])
    await edit_fn(msg, InlineKeyboardMarkup(rows))

async def _show_users(edit_fn, uid, page=0):
    per_page = 10
    users_ = db.get_all_users()
    total_pages = (len(users_) + per_page - 1) // per_page
    page = min(page, total_pages - 1) if total_pages > 0 else 0
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_users = users_[start_idx:end_idx]

    rows = []
    for u in page_users:
        st   = "🟢" if u.get('subscription_expiry') and u['subscription_expiry'] > datetime.now().isoformat() else "🔴"
        name = u['first_name'] or f"User {u['user_id']}"
        rows.append([_btn(f"{st} {name} ({u['user_id']})", callback_data=f"admin_user|{u['user_id']}")])

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("◀️", callback_data=f"admin_users_page|{page-1}"))
        nav_row.append(_btn(f"{page+1}/{total_pages}", callback_data="admin_users"))
        if page < total_pages - 1:
            nav_row.append(_btn("▶️", callback_data=f"admin_users_page|{page+1}"))
        rows.append(nav_row)
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel")])
    await edit_fn(f"👥 *المستخدمون*\n\nالصفحة `{page + 1}/{total_pages or 1}`", InlineKeyboardMarkup(rows))


# ─────────────────────────────────────────
#  Single check
# ─────────────────────────────────────────

async def _run_single(update, context, gw_id, card, fid=None):
    query = update.callback_query
    uid   = update.effective_user.id

    await bot_edit(query, s(uid,"checking"), InlineKeyboardMarkup([]), fid)

    proxies = db.get_active_proxies()
    proxy   = random.choice(proxies) if proxies else None
    result  = await engine.check_single(gw_id, card, proxy)

    db.log_check(uid, gw_id, "Single", card['number'][-4:],
                 result.get('status_text',''), result.get('category',''), result.get('raw',''))
    db.increment_user_checks(uid)

    gw      = db.get_gateway_by_id(gw_id)
    gw_name = gw['display_name'] if gw else "Unknown"

    if result.get('category') in ('approved_charged','approved_auth_only','approved_insufficient','auth_required'):
        bi  = bin_service.lookup(card['number'])
        amt = f"\n💰 `{result['amount']}`" if result.get('amount') else ""
        tds = "\n🔐 `3DS Required`"         if result.get('requires_3ds') else ""
        msg = (
            "╔══════════════════════╗\n║    ✅  APPROVED ✅    ║\n╚══════════════════════╝\n\n"
            f"💳 `{card['number']}|{card['month']}|{card['year']}|{card['cvv']}`\n"
            f"📌 `{result['reason']}`{amt}{tds}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🏦 `{bi['bank']}`\n💎 `{bi['scheme']} — {bi['type']}`\n🌍 `{bi['country']} {bi['flag']}`\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`\n🔖 {BOT_SIGNATURE}"
        )
        await bot_edit(query, msg, InlineKeyboardMarkup([
            [_btn(s(uid,"check_another"), callback_data="menu_check"),
             _btn(s(uid,"main_menu_btn"), callback_data="main_menu")],
        ]), fid)
        await log_channel(context.bot, msg, fid)
    else:
        msg = (
            "╔══════════════════════╗\n║    ❌  DECLINED ❌    ║\n╚══════════════════════╝\n\n"
            f"💳 `····{card['number'][-4:]}`\n📌 `{result.get('reason','Unknown')}`\n\n"
            f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`"
        )
        await bot_edit(query, msg, InlineKeyboardMarkup([
            [_btn(s(uid,"try_again"),      callback_data="menu_check"),
             _btn(s(uid,"main_menu_btn"),  callback_data="main_menu")],
        ]), fid)


# ─────────────────────────────────────────
#  Bulk check
# ─────────────────────────────────────────

async def _run_bulk(update, context, fid=None):
    query  = update.callback_query
    uid    = update.effective_user.id
    cards  = context.user_data.get('bulk_cards', [])
    gw_id  = context.user_data.get('bulk_gw')
    total  = len(cards)

    if not cards or not gw_id:
        await bot_edit(query, s(uid,"session_expired"), kb_back(uid), fid)
        return

    gw      = db.get_gateway_by_id(gw_id)
    gw_name = gw['display_name'] if gw else "Unknown"
    context.user_data.update({'is_checking': True, 'bulk_cancel': False})
    approved_list, errors, checked = [], 0, 0

    stop_kb = InlineKeyboardMarkup([[_btn(s(uid,"stop_btn"), callback_data="bulk_cancel")]])
    await bot_edit(query, f"⚡ *بدء الفحص...*\n\n`{progress_bar(0,total)}`\n📊 `0/{total}`  ✅`0`  ⚠️`0`",
                   stop_kb, fid)
    prog_msg    = query.message
    last_update = asyncio.get_running_loop().time()

    for i, card in enumerate(cards, 1):
        if context.user_data.get('bulk_cancel'):
            break
        proxies = db.get_active_proxies()
        proxy   = random.choice(proxies) if proxies else None
        result  = await engine.check_single(gw_id, card, proxy)
        checked = i

        if result.get('category') in ('approved_charged','approved_auth_only','approved_insufficient','auth_required'):
            approved_list.append({'card': card, 'result': result})
            bi  = bin_service.lookup(card['number'])
            amt = f"\n💰 `{result['amount']}`" if result.get('amount') else ""
            msg = (
                "╔══════════════════════╗\n║    ✅  APPROVED ✅    ║\n╚══════════════════════╝\n\n"
                f"💳 `{card['number']}|{card['month']}|{card['year']}|{card['cvv']}`\n"
                f"📌 `{result['reason']}`{amt}\n\n"
                f"🏦 `{bi['bank']}`\n💎 `{bi['scheme']} — {bi['type']}`\n🌍 `{bi['country']} {bi['flag']}`\n\n"
                f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`\n🔖 {BOT_SIGNATURE}"
            )
            try:
                await bot_send(context.bot, uid, msg, InlineKeyboardMarkup([]), fid)
                await log_channel(context.bot, msg, fid)
            except Exception as e:
                logger.error(f"Bulk send: {e}")
        elif result.get('category') == 'error' or not result.get('success'):
            errors += 1

        now = asyncio.get_running_loop().time()
        if now - last_update >= 2 or i == total or i % 5 == 0:
            try:
                status = '🛑 جاري الإيقاف...' if context.user_data.get('bulk_cancel') else '⏳ يرجى الانتظار...'
                cap = (f"⚡ *جاري الفحص...*\n\n`{progress_bar(i,total)}`\n"
                       f"📊 `{i}/{total}`  ✅`{len(approved_list)}`  ⚠️`{errors}`\n\n{status}")
                if prog_msg.photo:
                    await prog_msg.edit_caption(caption=cap, reply_markup=stop_kb, parse_mode="Markdown")
                else:
                    await prog_msg.edit_text(cap, reply_markup=stop_kb, parse_mode="Markdown")
                last_update = now
            except Exception:
                pass

        await asyncio.sleep(0.2)

    context.user_data['is_checking'] = False

    if approved_list:
        content = "\n".join(
            f"{i['card']['number']}|{i['card']['month']}|{i['card']['year']}|{i['card']['cvv']}"
            for i in approved_list
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(content)
            tmp = f.name
        try:
            await context.bot.send_document(
                chat_id=uid, document=open(tmp,'rb'),
                caption=f"✅ Approved: {len(approved_list)} / {checked}",
                filename=f"approved_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
        except Exception as e:
            logger.error(f"File send: {e}")
        finally:
            os.remove(tmp)

    icon = "🛑 توقّف" if context.user_data.get('bulk_cancel') else "✅ اكتمل"
    final = (f"╔══════════════════════╗\n║   {icon}   ║\n╚══════════════════════╝\n\n"
             f"📊 `{checked}/{total}`  ✅`{len(approved_list)}`  ⚠️`{errors}`")
    final_kb = InlineKeyboardMarkup([[_btn(s(uid,"main_menu_btn"), callback_data="main_menu")]])
    try:
        if prog_msg.photo:
            await prog_msg.edit_caption(caption=final, reply_markup=final_kb, parse_mode="Markdown")
        else:
            await prog_msg.edit_text(final, reply_markup=final_kb, parse_mode="Markdown")
    except Exception:
        pass


# ─────────────────────────────────────────
#  post_init  — cache banner + start web panel
# ─────────────────────────────────────────

def _start_web_panel():
    try:
        from web_panel import app as flask_app
        port = int(os.environ.get("WEB_PORT", 5000))
        logger.info(f"🌐 Web panel starting on port {port}")
        flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Web panel error: {e}")

async def post_init(app):
    await get_banner(app.bot)
    t = threading.Thread(target=_start_web_panel, daemon=True, name="WebPanel")
    t.start()
    logger.info("Bot initialized. Banner cached. Web panel thread started.")


# ─────────────────────────────────────────
#  ERROR HANDLER
# ─────────────────────────────────────────

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and prevent bot hanging"""
    logger.error(f"Exception while handling update: {context.error}", exc_info=context.error)

    # If the error is a timeout, we want to prevent it from hanging the bot
    if isinstance(context.error, TimedOut):
        logger.warning("Timeout occurred - continuing polling")
        return

    # Try to notify user if possible
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ في الاتصال. يرجى المحاولة مرة أخرى."
            )
        except Exception:
            pass


# ─────────────────────────────────────────
#  main
# ─────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN غير موجود!")
        return

    # Increased timeouts for Hugging Face Spaces connectivity
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("admin",      admin_cmd))
    app.add_handler(CommandHandler("addgateway", addgateway_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🚀 البوت يعمل...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
