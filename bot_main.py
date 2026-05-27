import logging
import re
import asyncio
import random
import string
import tempfile
import threading
import os
from datetime import datetime
from typing import Optional

from pydantic import ConfigDict
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, InputMediaPhoto, FSInputFile
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

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

# ══════════════════════════════════════════════════════
#  Built-in Gateways (داخل الكود)
# ══════════════════════════════════════════════════════
# عدّل الـ endpoint و الـ headers/body حسب API الحقيقي
BUILT_IN_GATEWAYS = [
    {
        'id': -1,
        'display_name': 'Stripe API',
        'button_name': 'Stripe',
        'api_endpoint': 'https://api.stripe.com/v1/payment_intents',
        'method': 'POST',
        'headers_json': '{"Authorization": "Bearer YOUR_SECRET_KEY", "Content-Type": "application/x-www-form-urlencoded"}',
        'body_template': 'amount=100&currency=usd&payment_method[card][number]={card}&payment_method[card][exp_month]={month}&payment_method[card][exp_year]={year}&payment_method[card][cvc]={cvv}&confirm=true',
        'success_pattern': 'succeeded',
        'decline_pattern': 'decline',
        'error_pattern': 'error',
        'timeout_seconds': 30,
        'is_active': 1,
    },
    {
        'id': -2,
        'display_name': 'Braintree API',
        'button_name': 'Braintree',
        'api_endpoint': 'https://payments.sandbox.braintree-api.com/graphql',
        'method': 'POST',
        'headers_json': '{"Content-Type": "application/json", "Authorization": "Bearer YOUR_TOKEN"}',
        'body_template': '{"query": "mutation { chargePaymentMethod(input: {paymentMethodId: \\"fake-valid-visa-nonce\\", transaction: {amount: \\"10.00\\"}}) { transaction { id status } } }"}',
        'success_pattern': 'SUBMITTED_FOR_SETTLEMENT',
        'decline_pattern': 'processor_declined',
        'error_pattern': 'error',
        'timeout_seconds': 30,
        'is_active': 1,
    },
]


def get_all_gateways():
    """جمع البوابات من الكود + قاعدة البيانات."""
    db_gws = db.get_active_gateways()
    return BUILT_IN_GATEWAYS + db_gws


def get_gateway_by_id(gid: int):
    """البحث في البوابات المدمجة أولاً ثم قاعدة البيانات."""
    for gw in BUILT_IN_GATEWAYS:
        if gw['id'] == gid:
            return gw
    return db.get_gateway_by_id(gid)


BANNER_PATH = os.path.join(os.path.dirname(__file__), "banner.png")
_banner_id: Optional[str] = None

router = Router()


# ══════════════════════════════════════════════════════
#  StyledButton — زر ملون (style field)
# ══════════════════════════════════════════════════════

class StyledButton(InlineKeyboardButton):
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    style: Optional[str] = None


def _btn(text: str, *,
         callback_data: Optional[str] = None,
         url: Optional[str] = None,
         style: Optional[str] = None,
         **kw) -> StyledButton:
    kwargs: dict = {'text': text}
    if callback_data is not None:
        kwargs['callback_data'] = callback_data
    if url is not None:
        kwargs['url'] = url
    if style is not None:
        kwargs['style'] = style
    kwargs.update(kw)
    return StyledButton(**kwargs)


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def is_allowed(uid: int) -> bool:
    return is_admin(uid) or db.is_subscribed(uid)


def get_lang(uid: int) -> str:
    return db.get_user_language(uid)


def s(uid: int, key: str, **kw):
    lang = get_lang(uid)
    st = STRINGS.get(lang, STRINGS["ar"])
    txt = st.get(key, STRINGS["ar"].get(key, key))
    return txt.format(**kw) if kw else txt


def parse_card(text: str):
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


# ══════════════════════════════════════════════════════
#  BANNER
# ══════════════════════════════════════════════════════

async def get_banner(bot: Bot) -> Optional[str]:
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
            photo=FSInputFile(BANNER_PATH),
            caption="🖼 Banner cached"
        )
        _banner_id = msg.photo[-1].file_id
        db.set_setting('banner_file_id', _banner_id)
        await msg.delete()
        logger.info(f"Banner cached: {_banner_id[:20]}…")
    except Exception as e:
        logger.warning(f"Banner upload failed: {e}")
    return _banner_id


# ══════════════════════════════════════════════════════
#  SEND / EDIT / LOG
# ══════════════════════════════════════════════════════

async def bot_send(bot: Bot, chat_id: int, caption: str, kb, fid=None):
    if fid:
        return await bot.send_photo(
            chat_id=chat_id, photo=fid, caption=caption,
            reply_markup=kb, parse_mode="Markdown"
        )
    return await bot.send_message(
        chat_id=chat_id, text=caption,
        reply_markup=kb, parse_mode="Markdown"
    )


async def bot_edit(query: CallbackQuery, caption: str, kb, fid=None):
    msg = query.message
    if not msg:
        return
    has_photo = bool(msg.photo)
    if has_photo:
        try:
            await msg.edit_caption(caption=caption, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception:
            pass
    if fid:
        try:
            await msg.edit_media(
                media=InputMediaPhoto(media=fid, caption=caption, parse_mode="Markdown"),
                reply_markup=kb
            )
            return
        except Exception:
            pass
    try:
        await msg.edit_text(text=caption, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass


async def log_channel(bot: Bot, text: str, fid=None):
    if not LOG_CHANNEL_ID:
        return
    try:
        if fid:
            await bot.send_photo(
                chat_id=LOG_CHANNEL_ID, photo=fid,
                caption=text, parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=LOG_CHANNEL_ID, text=text,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Channel log: {e}")


# ══════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════

def kb_main(uid: int, is_sub: bool, is_adm: bool) -> InlineKeyboardMarkup:
    if is_sub or is_adm:
        return InlineKeyboardMarkup(inline_keyboard=[
            [_btn("📂 رفع كروت", callback_data="menu_upload", style="primary"),
             _btn("💳 فحص كارت",  callback_data="menu_check", style="success")],
            [_btn("👤 حسابي", callback_data="menu_account", style="primary"),
             _btn("📊 السجل", callback_data="menu_history", style="primary")],
            [_btn("🎫 كود تفعيل", callback_data="menu_redeem", style="success")],
            [_btn("⚙️ الإعدادات", callback_data="menu_settings", style="primary"),
             _btn("📞 الدعم",  url=f"https://t.me/{SUPPORT_USERNAME}")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("💎 اشتراك", url=f"https://t.me/{SUPPORT_USERNAME}", style="success")],
        [_btn("🎫 كود تفعيل", callback_data="menu_redeem", style="primary")],
        [_btn("📞 الدعم", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])


def kb_admin(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📊 الإحصائيات",      callback_data="admin_stats", style="primary"),
         _btn("👥 المستخدمين",      callback_data="admin_users", style="primary")],
        [_btn("🎫 أكواد التفعيل",  callback_data="admin_codes", style="success"),
         _btn("⚡ البوابات",        callback_data="admin_gateways", style="primary")],
        [_btn("🔌 البروكسيات",     callback_data="admin_proxies", style="primary"),
         _btn("📋 السجلات",        callback_data="admin_logs", style="primary")],
        [_btn("⚙️ الإعدادات",      callback_data="admin_settings", style="primary"),
         _btn("🌐 لوحة الويب",     url=f"https://{os.environ.get('REPLIT_DEV_DOMAIN','localhost')}:5000")],
        [_btn("🔙 رجوع", callback_data="main_menu", style="danger")],
    ])


def kb_back(uid: int, target="main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(s(uid, "btn_back"), callback_data=target, style="danger")]
    ])


# ══════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    if not user:
        return
    db.get_or_create_user(user.id, user.username, user.first_name)
    uid = user.id
    is_sub = db.is_subscribed(uid)
    is_adm = is_admin(uid)

    if is_adm:
        cap = s(uid, "welcome_admin", name=user.first_name)
    elif is_sub:
        u = db.get_user(uid)
        cap = s(uid, "welcome_sub", name=user.first_name, exp=u.get('subscription_expiry', '---'))
    else:
        cap = s(uid, "welcome_guest", name=user.first_name, support=SUPPORT_USERNAME)

    fid = await get_banner(message.bot)
    kb = kb_main(uid, is_sub, is_adm)
    await bot_send(message.bot, uid, cap, kb, fid)


# ══════════════════════════════════════════════════════
#  /admin
# ══════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    uid = message.from_user.id
    await state.update_data(awaiting_admin_pass=True)
    fid = await get_banner(message.bot)
    await bot_send(message.bot, uid,
                   "🔐 *لوحة الأدمن*\n\nأدخل كلمة المرور:",
                   kb_back(uid), fid)


# ══════════════════════════════════════════════════════
#  /addgateway
# ══════════════════════════════════════════════════════

@router.message(Command("addgateway"))
async def cmd_addgateway(message: Message, state: FSMContext):
    uid = message.from_user.id
    if not is_admin(uid):
        await message.answer("⛔ للأدمن فقط.")
        return
    await state.update_data(gw_step='name', gw_data={})
    fid = await get_banner(message.bot)
    cancel = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("❌ إلغاء", callback_data="main_menu", style="danger")]
    ])
    await bot_send(message.bot, uid,
                   "⚡ *إضافة بوابة جديدة*\nالخطوة 1/7\n\n📌 أرسل *اسم البوابة* (داخلي):",
                   cancel, fid)


# ══════════════════════════════════════════════════════
#  Document handler
# ══════════════════════════════════════════════════════

@router.message(F.document)
async def on_document(message: Message, state: FSMContext):
    uid = message.from_user.id
    doc = message.document
    if not doc:
        return

    data = await state.get_data()

    # Proxy file upload
    if data.get('awaiting_proxy_file'):
        await state.update_data(awaiting_proxy_file=False)
        if not doc.file_name.endswith('.txt'):
            await message.answer("❌ ملفات .txt فقط.")
            return
        file = await message.bot.get_file(doc.file_id)
        bytes_io = await message.bot.download_file(file.file_path)
        lines = bytes_io.read().decode('utf-8', errors='ignore').splitlines()
        added = db.add_proxies_bulk(lines)
        fid = await get_banner(message.bot)
        await bot_send(message.bot, uid,
                       f"✅ *تمت إضافة البروكسيات*\n\n"
                       f"📋 الكل: `{len(lines)}`\n✅ أُضيف: `{added}`",
                       kb_back(uid, "admin_proxies"), fid)
        return

    # Card file upload
    if not is_allowed(uid):
        await message.answer(s(uid, "no_sub"))
        return
    if not doc.file_name.endswith('.txt'):
        await message.answer("❌ ملفات .txt فقط.")
        return
    if data.get('is_checking'):
        await message.answer("⏳ يوجد فحص نشط.")
        return

    file = await message.bot.get_file(doc.file_id)
    bytes_io = await message.bot.download_file(file.file_path)
    text = bytes_io.read().decode('utf-8', errors='ignore')
    cards = [c for line in text.splitlines() if (c := parse_card(line.strip()))]

    if not cards:
        await message.answer("❌ لا توجد كروت صالحة.\nالصيغة: `NUMBER|MM|YYYY|CVV`",
                             parse_mode="Markdown")
        return

    limit = 999999 if is_admin(uid) else MAX_CARDS_REGULAR
    if len(cards) > limit:
        await message.answer(f"❌ الحد {limit} كارت. أرسلت {len(cards)}.")
        return

    await state.update_data(bulk_cards=cards, bulk_total=len(cards))
    gateways = db.get_active_gateways()
    if not gateways:
        await message.answer(s(uid, "no_gateways"))
        return

    rows = [[_btn(f"⚡  {gw['button_name']}", callback_data=f"bulk_gw|{gw['id']}", style="primary")] for gw in gateways]
    rows.append([_btn(s(uid, "btn_cancel"), callback_data="main_menu", style="danger")])
    fid = await get_banner(message.bot)
    await bot_send(message.bot, uid,
                   f"📂 *ملف الكروت*\n\n✅ صالحة: `{len(cards)}`\n\n🌐 اختر البوابة:",
                   InlineKeyboardMarkup(inline_keyboard=rows), fid)


# ══════════════════════════════════════════════════════
#  Text handler
# ══════════════════════════════════════════════════════

@router.message(F.text & ~F.command)
async def on_message(message: Message, state: FSMContext):
    uid = message.from_user.id
    text = message.text.strip()
    data = await state.get_data()

    # ── Admin password ─────────────────────
    if data.get('awaiting_admin_pass'):
        try:
            await message.delete()
        except Exception:
            pass
        await state.update_data(awaiting_admin_pass=False)
        if text == ADMIN_PASSWORD:
            await state.update_data(is_admin_verified=True)
            fid = await get_banner(message.bot)
            await bot_send(message.bot, uid,
                           "✅ *تم الدخول!*\nأهلاً بك في لوحة الأدمن 👑",
                           kb_admin(uid), fid)
        else:
            await message.answer(s(uid, "wrong_pass"))
        return

    # ── Code creation wizard ───────────────
    code_step = data.get('admin_code_step')
    if code_step and is_admin(uid):
        await _handle_code_wizard(message, state, text, code_step)
        return

    # ── Custom extension input (message) ─────────────
    if data.get('awaiting_custom_ext') and is_admin(uid):
        tid = int(data['awaiting_custom_ext'])
        await state.update_data(awaiting_custom_ext=None)
        try:
            hrs = int(text)
            if hrs < 1:
                raise ValueError
        except ValueError:
            await message.answer("❌ أدخل رقم صحيح (ساعات).")
            return
        new_exp = db.extend_subscription_hours(tid, hrs)
        fid = await get_banner(message.bot)
        await bot_send(message.bot, uid,
                       f"✅ *تمت الإضافة!*\n🆔 `{tid}`\n⏰ حتى: `{new_exp.strftime('%Y-%m-%d %H:%M')}`",
                       kb_back(uid, f"admin_user|{tid}"), fid)
        return

    # ── Proxy single input ─────────────────
    if data.get('awaiting_proxy'):
        await state.update_data(awaiting_proxy=False)
        if db.add_proxy(text):
            fid = await get_banner(message.bot)
            total = db.count_active_proxies()
            await bot_send(message.bot, uid,
                           f"✅ *تمت إضافة البروكسي*\n\n`{text}`\n\n📊 المجموع: `{total}`",
                           kb_back(uid, "admin_proxies"), fid)
        else:
            await message.answer("⚠️ البروكسي موجود مسبقاً.")
        return

    # ── Redeem code ────────────────────────
    if data.get('awaiting_redeem'):
        await state.update_data(awaiting_redeem=False)
        code_str = text.upper()
        code = db.get_code(code_str)
        if not code:
            await message.answer(s(uid, "invalid_code"))
        elif code['used_count'] >= code['max_uses']:
            await message.answer(s(uid, "code_maxed"))
        else:
            db.use_code(code['id'], uid)
            hours = code.get('duration_hours') or (code.get('duration_days', 1) * 24)
            new_exp = db.extend_subscription_hours(uid, hours)
            fid = await get_banner(message.bot)
            await bot_send(message.bot, uid,
                           s(uid, "redeemed", exp=new_exp.strftime('%Y-%m-%d %H:%M')),
                           kb_main(uid, True, is_admin(uid)), fid)
        return

    # ── Card input ─────────────────────────
    if data.get('awaiting_card'):
        if not is_allowed(uid):
            await message.answer(s(uid, "no_sub"))
            return
        card = parse_card(text)
        if not card:
            await message.answer(s(uid, "invalid_format"), parse_mode="Markdown")
            return
        await state.update_data(last_card=card, awaiting_card=False)
        gateways = db.get_active_gateways()
        if not gateways:
            await message.answer(s(uid, "no_gateways"))
            return
        rows = [[_btn(f"⚡  {gw['button_name']}", callback_data=f"gw|{gw['id']}", style="primary")] for gw in gateways]
        rows.append([_btn(s(uid, "btn_cancel"), callback_data="main_menu", style="danger")])
        fid = await get_banner(message.bot)
        await bot_send(message.bot, uid,
                       f"💳 `····{card['number'][-4:]}`\n\n🌐 اختر البوابة:",
                       InlineKeyboardMarkup(inline_keyboard=rows), fid)
        return

    # ── Gateway wizard ─────────────────────
    gw_step = data.get('gw_step')
    if gw_step and is_admin(uid):
        await _handle_gw_wizard(message, state, text, gw_step)
        return

    # ── Setting value input ────────────────
    if data.get('awaiting_setting_value') and is_admin(uid):
        setting_key = data['awaiting_setting_value']
        await state.update_data(awaiting_setting_value=None)
        db.set_setting(setting_key, text)
        fid = await get_banner(message.bot)
        await bot_send(message.bot, uid,
                       f"✅ *تم تحديث الإعداد*\n\n📌 `{setting_key}`\n🆔 `{text}`",
                       kb_admin(uid), fid)
        return

    # ── Default ────────────────────────────
    fid = await get_banner(message.bot)
    user = db.get_user(uid)
    name = user.get('first_name', 'User') if user else 'User'
    await bot_send(message.bot, uid,
                   s(uid, "menu_title", name=name),
                   kb_main(uid, db.is_subscribed(uid), is_admin(uid)), fid)


# ══════════════════════════════════════════════════════
#  Code creation wizard
# ══════════════════════════════════════════════════════

async def _handle_code_wizard(message: Message, state: FSMContext, text: str, step: str):
    uid = message.from_user.id
    fid = await get_banner(message.bot)
    cancel = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("❌ إلغاء", callback_data="admin_codes", style="danger")]
    ])

    if step == 'hours':
        try:
            hours = int(text)
            if hours < 1:
                raise ValueError
        except ValueError:
            await message.answer("❌ أدخل رقم صحيح (ساعات).")
            return
        await state.update_data(admin_code_hours=hours, admin_code_step='uses')
        await bot_send(message.bot, uid,
                       f"🎫 *مدة الكود:* `{hours}` ساعة\n\nالخطوة 2/2\n👥 كم مرة استخدام؟",
                       cancel, fid)
        return

    if step == 'uses':
        try:
            uses = int(text)
            if uses < 1:
                raise ValueError
        except ValueError:
            await message.answer("❌ أدخل رقم صحيح.")
            return
        data = await state.get_data()
        hours = data.get('admin_code_hours', 24)
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        db.create_code(code, '', hours, uses, uid)
        await state.update_data(admin_code_step=None)

        days_str = f"{hours//24} يوم" if hours >= 24 else f"{hours} ساعة"
        await bot_send(message.bot, uid,
                       f"✅ *تم إنشاء الكود!*\n\n"
                       f"🔑 `{code}`\n"
                       f"⏰ المدة: `{days_str}` (`{hours}` ساعة)\n"
                       f"👥 الاستخدام: `{uses}` مرة",
                       kb_admin(uid), fid)
        return


# ══════════════════════════════════════════════════════
#  Gateway wizard
# ══════════════════════════════════════════════════════

_GW_STEPS = ['name', 'button', 'endpoint', 'method', 'headers', 'body', 'patterns']
_GW_PROMPTS = {
    'name':     "الخطوة 2/7\n🔘 *اسم الزرار* (للمستخدم):",
    'button':   "الخطوة 3/7\n🔗 *رابط API* (endpoint):",
    'endpoint': "الخطوة 4/7\n📡 *الميثود* (POST أو GET):",
    'method':   "الخطوة 5/7\n📋 *Headers* (JSON):\nمثال: `{\"Content-Type\": \"application/json\"}`",
    'headers':  "الخطوة 6/7\n📝 *Body Template*:\nمتغيرات: `{card}` `{month}` `{year}` `{cvv}`",
    'body':     "الخطوة 7/7\n🎯 *Patterns* (success|decline|error)\nأو `skip` لتخطي:",
}
_GW_FIELDS = ['display_name', 'button_name', 'api_endpoint', 'method', 'headers_json', 'body_template']


async def _handle_gw_wizard(message: Message, state: FSMContext, text: str, step: str):
    import json as _json
    uid = message.from_user.id
    data = await state.get_data()
    gd = data.setdefault('gw_data', {})
    fid = await get_banner(message.bot)
    cancel = InlineKeyboardMarkup(inline_keyboard=[
        [_btn("❌ إلغاء", callback_data="main_menu", style="danger")]
    ])

    if step == 'patterns':
        if text.lower() == 'skip':
            gd['success_pattern'] = gd['decline_pattern'] = gd['error_pattern'] = ''
        else:
            parts = [p.strip() for p in text.split('|')]
            gd['success_pattern'] = parts[0] if len(parts) > 0 else ''
            gd['decline_pattern'] = parts[1] if len(parts) > 1 else ''
            gd['error_pattern'] = parts[2] if len(parts) > 2 else ''
        try:
            hdrs = _json.loads(gd.get('headers_json', '{}'))
        except Exception:
            hdrs = {}
        db.add_gateway({
            'display_name': gd.get('display_name', ''),
            'button_name': gd.get('button_name', gd.get('display_name', '')),
            'endpoint': gd.get('api_endpoint', ''),
            'method': gd.get('method', 'POST').upper(),
            'headers': hdrs, 'body': gd.get('body_template', ''),
            'success': gd.get('success_pattern', ''), 'decline': gd.get('decline_pattern', ''),
            'error': gd.get('error_pattern', ''), 'timeout': 30
        })
        await state.update_data(gw_step=None, gw_data={})
        await bot_send(message.bot, uid,
                       f"✅ *تمت إضافة البوابة!*\n\n"
                       f"📌 `{gd.get('display_name')}`\n"
                       f"🔗 `{gd.get('api_endpoint','')[:60]}`",
                       kb_admin(uid), fid)
        return

    idx = _GW_STEPS.index(step)
    field = _GW_FIELDS[idx]
    gd[field] = text
    next_step = _GW_STEPS[idx + 1]
    await state.update_data(gw_step=next_step, gw_data=gd)
    await bot_send(message.bot, uid, _GW_PROMPTS[step], cancel, fid)


# ══════════════════════════════════════════════════════
#  Callback queries
# ══════════════════════════════════════════════════════

@router.callback_query()
async def on_callback(query: CallbackQuery, state: FSMContext):
    await query.answer()
    data = query.data
    uid = query.from_user.id
    is_sub = db.is_subscribed(uid)
    is_adm = is_admin(uid)
    data_state = await state.get_data()
    is_adm_v = data_state.get('is_admin_verified', False) or is_adm
    fid = await get_banner(query.bot)

    async def edit(cap, kb):
        await bot_edit(query, cap, kb, fid)

    # ── Main menu ──────────────────────────
    if data == "main_menu":
        await state.update_data(is_checking=False, bulk_cancel=True, gw_step=None,
                                admin_code_step=None, awaiting_proxy=False,
                                awaiting_proxy_file=False)
        user = db.get_user(uid)
        name = user.get('first_name', 'User') if user else 'User'
        await edit(s(uid, "menu_title", name=name), kb_main(uid, is_sub, is_adm))
        return

    if data == "menu_upload":
        await edit(s(uid, "upload_title"), kb_back(uid))
        return

    if data == "menu_check":
        await state.update_data(awaiting_card=True)
        await edit(s(uid, "check_title"), kb_back(uid))
        return

    if data == "menu_account":
        u = db.get_user(uid)
        exp = u.get('subscription_expiry', '---') if not is_adm else '♾️'
        chk = u.get('total_checks', 0) if u else 0
        st = "👑 أدمن" if is_adm else ("✅ نشط" if is_sub else "❌ منتهي")
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
            icon = "✅" if "APPROVED" in l.get('result_status', '') else "❌"
            msg += f"{icon} `····{l['card_last4']}` — {l['gateway_name']}\n"
        await edit(msg, kb_main(uid, is_sub, is_adm))
        return

    if data == "menu_redeem":
        await state.update_data(awaiting_redeem=True)
        await edit(s(uid, "redeem_title"), kb_back(uid))
        return

    if data == "menu_settings":
        await edit(s(uid, "settings_title"), InlineKeyboardMarkup(inline_keyboard=[
            [_btn("🇸🇦  العربية", callback_data="set_lang_ar", style="primary"),
             _btn("🇬🇧  English",  callback_data="set_lang_en", style="primary")],
            [_btn(s(uid, "btn_back"), callback_data="main_menu", style="danger")],
        ]))
        return

    if data in ("set_lang_ar", "set_lang_en"):
        db.set_user_language(uid, data.split("_")[-1])
        await edit(s(uid, "lang_changed"), kb_main(uid, is_sub, is_adm))
        return

    # ── Gateway select (single) ────────────
    if data.startswith("gw|"):
        card = data_state.get('last_card')
        if not card:
            await edit(s(uid, "session_expired"), kb_back(uid))
            return
        await _run_single(query, state, int(data.split("|")[1]), card, fid)
        return

    # ── Gateway select (bulk) ──────────────
    if data.startswith("bulk_gw|"):
        gw_id = int(data.split("|")[1])
        await state.update_data(bulk_gw=gw_id)
        gw = db.get_gateway_by_id(gw_id)
        total = data_state.get('bulk_total', 0)
        await edit(
            f"⚡ *البوابة:* `{gw['display_name']}`\n💳 الكروت: `{total}`\n\nاضغط تأكيد للبدء:",
            InlineKeyboardMarkup(inline_keyboard=[
                [_btn(s(uid, "confirm_btn"), callback_data="bulk_confirm", style="success")],
                [_btn(s(uid, "change_gw_btn"), callback_data="bulk_back", style="primary"),
                 _btn(s(uid, "btn_cancel"), callback_data="main_menu", style="danger")],
            ])
        )
        return

    if data == "bulk_back":
        gateways = db.get_active_gateways()
        rows = [[_btn(f"⚡  {gw['button_name']}", callback_data=f"bulk_gw|{gw['id']}", style="primary")] for gw in gateways]
        rows.append([_btn(s(uid, "btn_cancel"), callback_data="main_menu", style="danger")])
        await edit(f"🌐 اختر البوابة ({data_state.get('bulk_total', 0)} كارت):",
                   InlineKeyboardMarkup(inline_keyboard=rows))
        return

    if data == "bulk_confirm":
        await _run_bulk(query, state, fid)
        return

    if data == "bulk_cancel":
        await state.update_data(bulk_cancel=True)
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
        stats = db.get_stats()[:7]
        tu, au = db.count_users(), db.count_active_users()
        gw_c = db.count_active_gateways()
        px_c = db.count_active_proxies()
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
        u = db.get_user(tid)
        if not u:
            return
        blk = u['is_blocked']
        kb_ = InlineKeyboardMarkup(inline_keyboard=[
            [_btn("➕ +24 ساعة", callback_data=f"admin_ext|{tid}|24", style="success"),
             _btn("➕ +7 أيام",  callback_data=f"admin_ext|{tid}|168", style="success")],
            [_btn("➕ +30 يوم",  callback_data=f"admin_ext|{tid}|720", style="success"),
             _btn("✏️ مخصص",    callback_data=f"admin_ext_custom|{tid}", style="primary")],
            [_btn("🚫 حظر" if not blk else "✅ رفع الحظر",
                  callback_data=f"admin_blk|{tid}|{1-blk}", style="danger" if not blk else "success")],
            [_btn("🔙 رجوع", callback_data="admin_users", style="danger")],
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

    if data.startswith("admin_ext_custom|"):
        tid = int(data.split("|")[1])
        await state.update_data(awaiting_custom_ext=tid)
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
        await state.update_data(admin_code_step='hours')
        await edit(
            "🎫 *إنشاء كود تفعيل*\n\nالخطوة 1/2\n⏰ كم ساعة مدة الكود؟\n\n`24` = يوم\n`168` = أسبوع\n`720` = شهر",
            InlineKeyboardMarkup(inline_keyboard=[
                [_btn("❌ إلغاء", callback_data="admin_codes", style="danger")]
            ])
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
        await state.update_data(awaiting_proxy=True)
        await edit(
            "🔌 *إضافة بروكسي*\n\nأرسل البروكسي:\n`host:port`\n`http://user:pass@host:port`\n`socks5://host:port`",
            kb_back(uid, "admin_proxies")
        )
        return

    if data == "admin_proxy_file":
        await state.update_data(awaiting_proxy_file=True)
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
        await state.update_data(awaiting_setting_value=setting_key)
        await edit(f"⚙️ *تعديل الإعداد*\n\n📌 `{setting_key}`\n\nأرسل القيمة الجديدة:", kb_back(uid, "admin_settings"))
        return


# ══════════════════════════════════════════════════════
#  Admin panel helpers
# ══════════════════════════════════════════════════════

async def _show_codes(edit_fn, uid: int):
    codes = db.get_all_codes()
    rows = [[_btn("➕  إنشاء كود جديد", callback_data="admin_gencode", style="success")]]
    for c in codes:
        hrs = c.get('duration_hours') or c.get('duration_days', 1) * 24
        used = f"{c['used_count']}/{c['max_uses']}"
        lbl = c.get('label') or c['code']
        tag = f"{hrs}h" if hrs < 24 else f"{hrs//24}d"
        rows.append([_btn(f"🎫 {lbl} | ⏰{tag} | [{used}]", callback_data=f"admin_delcode|{c['id']}")])
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel", style="danger")])
    await edit_fn("🎫 *أكواد التفعيل:*\n_(اضغط على كود لحذفه)_", InlineKeyboardMarkup(inline_keyboard=rows))


async def _show_gateways(edit_fn, uid: int):
    gateways = db.get_active_gateways()
    rows = [[_btn("➕  إضافة بوابة", callback_data="admin_gw_hint", style="success")]]
    for gw in gateways:
        rows.append([_btn(f"⚡ {gw['button_name']} — {gw['display_name']}",
                          callback_data=f"admin_delgw|{gw['id']}")])
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel", style="danger")])
    await edit_fn(
        "⚡ *البوابات النشطة:*\n_(اضغط للحذف)_\n\nلإضافة بوابة: /addgateway",
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


async def _show_proxies(edit_fn, uid: int):
    proxies = db.get_active_proxies()
    count = len(proxies)
    rows = [
        [_btn("➕  بروكسي واحد",    callback_data="admin_proxy_add", style="success"),
         _btn("📁  رفع ملف (.txt)", callback_data="admin_proxy_file", style="primary")],
    ]
    for p in proxies[:10]:
        label = f"{'✅' if p['fail_count'] < 3 else '⚠️'} {p['proxy_string'][:35]}"
        rows.append([_btn(label, callback_data=f"admin_delproxy|{p['id']}")])
    if count > 10:
        rows.append([_btn(f"… و{count-10} أخرى (من لوحة الويب)", callback_data="admin_proxies", style="primary")])
    rows.append([_btn("🗑  حذف الكل", callback_data="admin_proxy_clear", style="danger"),
                 _btn("🔙 رجوع",       callback_data="admin_panel", style="danger")])
    await edit_fn(
        f"🔌 *البروكسيات*\n\n✅ نشط: `{count}`\n_(اضغط للحذف)_",
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


async def _show_logs(edit_fn, uid: int, page=0):
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
            nav_row.append(_btn("◀️", callback_data=f"admin_logs_page|{page-1}", style="primary"))
        nav_row.append(_btn(f"{page+1}/{total_pages}", callback_data="admin_logs", style="primary"))
        if page < total_pages - 1:
            nav_row.append(_btn("▶️", callback_data=f"admin_logs_page|{page+1}", style="primary"))
        rows.append(nav_row)
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel", style="danger")])
    await edit_fn(msg, InlineKeyboardMarkup(inline_keyboard=rows))


async def _show_settings(edit_fn, uid: int):
    settings = db.get_all_settings() if hasattr(db, 'get_all_settings') else []
    if not settings:
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
        rows.append([_btn(f"✏️ تعديل {key}", callback_data=f"admin_set_setting|{key}", style="primary")])

    rows.append([_btn("🔙 رجوع", callback_data="admin_panel", style="danger")])
    await edit_fn(msg, InlineKeyboardMarkup(inline_keyboard=rows))


async def _show_users(edit_fn, uid: int, page=0):
    per_page = 10
    users_ = db.get_all_users()
    total_pages = (len(users_) + per_page - 1) // per_page
    page = min(page, total_pages - 1) if total_pages > 0 else 0
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_users = users_[start_idx:end_idx]

    rows = []
    for u in page_users:
        st = "🟢" if u.get('subscription_expiry') and u['subscription_expiry'] > datetime.now().isoformat() else "🔴"
        name = u['first_name'] or f"User {u['user_id']}"
        rows.append([_btn(f"{st} {name} ({u['user_id']})", callback_data=f"admin_user|{u['user_id']}")])

    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(_btn("◀️", callback_data=f"admin_users_page|{page-1}", style="primary"))
        nav_row.append(_btn(f"{page+1}/{total_pages}", callback_data="admin_users", style="primary"))
        if page < total_pages - 1:
            nav_row.append(_btn("▶️", callback_data=f"admin_users_page|{page+1}", style="primary"))
        rows.append(nav_row)
    rows.append([_btn("🔙 رجوع", callback_data="admin_panel", style="danger")])
    await edit_fn(f"👥 *المستخدمون*\n\nالصفحة `{page + 1}/{total_pages or 1}`", InlineKeyboardMarkup(inline_keyboard=rows))


# ══════════════════════════════════════════════════════
#  Single check
# ══════════════════════════════════════════════════════

async def _run_single(query: CallbackQuery, state: FSMContext, gw_id: int, card: dict, fid=None):
    uid = query.from_user.id
    bot = query.bot

    await bot_edit(query, s(uid, "checking"), InlineKeyboardMarkup(inline_keyboard=[]), fid)

    proxies = db.get_active_proxies()
    proxy = random.choice(proxies) if proxies else None
    result = await engine.check_single(gw_id, card, proxy)

    db.log_check(uid, gw_id, "Single", card['number'][-4:],
                 result.get('status_text', ''), result.get('category', ''), result.get('raw', ''))
    db.increment_user_checks(uid)

    gw = db.get_gateway_by_id(gw_id)
    gw_name = gw['display_name'] if gw else "Unknown"

    if result.get('category') in ('approved_charged', 'approved_auth_only', 'approved_insufficient', 'auth_required'):
        bi = bin_service.lookup(card['number'])
        amt = f"\n💰 `{result['amount']}`" if result.get('amount') else ""
        tds = "\n🔐 `3DS Required`" if result.get('requires_3ds') else ""
        msg = (
            "╔══════════════════════╗\n║    ✅  APPROVED ✅    ║\n╚══════════════════════╝\n\n"
            f"💳 `{card['number']}|{card['month']}|{card['year']}|{card['cvv']}`\n"
            f"📌 `{result['reason']}`{amt}{tds}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🏦 `{bi['bank']}`\n💎 `{bi['scheme']} — {bi['type']}`\n🌍 `{bi['country']} {bi['flag']}`\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`\n🔖 {BOT_SIGNATURE}"
        )
        await bot_edit(query, msg, InlineKeyboardMarkup(inline_keyboard=[
            [_btn(s(uid, "check_another"), callback_data="menu_check", style="primary"),
             _btn(s(uid, "main_menu_btn"), callback_data="main_menu", style="danger")],
        ]), fid)
        await log_channel(bot, msg, fid)
    else:
        msg = (
            "╔══════════════════════╗\n║    ❌  DECLINED ❌    ║\n╚══════════════════════╝\n\n"
            f"💳 `····{card['number'][-4:]}`\n📌 `{result.get('reason','Unknown')}`\n\n"
            f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`"
        )
        await bot_edit(query, msg, InlineKeyboardMarkup(inline_keyboard=[
            [_btn(s(uid, "try_again"), callback_data="menu_check", style="primary"),
             _btn(s(uid, "main_menu_btn"), callback_data="main_menu", style="danger")],
        ]), fid)


# ══════════════════════════════════════════════════════
#  Bulk check — نتيجة كارت كارت
# ══════════════════════════════════════════════════════

async def _run_bulk(query: CallbackQuery, state: FSMContext, fid=None):
    uid = query.from_user.id
    bot = query.bot
    data = await state.get_data()
    cards = data.get('bulk_cards', [])
    gw_id = data.get('bulk_gw')
    total = len(cards)

    if not cards or not gw_id:
        await bot_edit(query, s(uid, "session_expired"), kb_back(uid), fid)
        return

    gw = db.get_gateway_by_id(gw_id)
    gw_name = gw['display_name'] if gw else "Unknown"
    await state.update_data(is_checking=True, bulk_cancel=False)
    approved_list, errors, checked = [], 0, 0

    stop_kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn(s(uid, "stop_btn"), callback_data="bulk_cancel", style="danger")]
    ])
    await bot_edit(query, f"⚡ *بدء الفحص...*\n\n`{progress_bar(0,total)}`\n📊 `0/{total}`  ✅`0`  ⚠️`0`",
                   stop_kb, fid)
    prog_msg = query.message
    last_update = asyncio.get_running_loop().time()

    for i, card in enumerate(cards, 1):
        state_data = await state.get_data()
        if state_data.get('bulk_cancel'):
            break

        proxies = db.get_active_proxies()
        proxy = random.choice(proxies) if proxies else None
        result = await engine.check_single(gw_id, card, proxy)
        checked = i

        # ── عرض نتيجة كل كارت على حده ──
        if result.get('category') in ('approved_charged', 'approved_auth_only', 'approved_insufficient', 'auth_required'):
            approved_list.append({'card': card, 'result': result})
            bi = bin_service.lookup(card['number'])
            amt = f"\n💰 `{result['amount']}`" if result.get('amount') else ""
            msg = (
                "╔══════════════════════╗\n║    ✅  APPROVED ✅    ║\n╚══════════════════════╝\n\n"
                f"💳 `{card['number']}|{card['month']}|{card['year']}|{card['cvv']}`\n"
                f"📌 `{result['reason']}`{amt}\n\n"
                f"🏦 `{bi['bank']}`\n💎 `{bi['scheme']} — {bi['type']}`\n🌍 `{bi['country']} {bi['flag']}`\n\n"
                f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`\n🔖 {BOT_SIGNATURE}"
            )
            try:
                await bot_send(bot, uid, msg, InlineKeyboardMarkup(inline_keyboard=[]), fid)
                await log_channel(bot, msg, fid)
            except Exception as e:
                logger.error(f"Bulk send approved: {e}")
        elif result.get('category') == 'error' or not result.get('success'):
            errors += 1
            msg = (
                f"❌ *DECLINED* | `····{card['number'][-4:]}`\n"
                f"📌 `{result.get('reason','Error')}`\n"
                f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`"
            )
            try:
                await bot_send(bot, uid, msg, InlineKeyboardMarkup(inline_keyboard=[]), fid)
            except Exception as e:
                logger.error(f"Bulk send declined: {e}")
        else:
            msg = (
                f"❌ *DECLINED* | `····{card['number'][-4:]}`\n"
                f"📌 `{result.get('reason','Declined')}`\n"
                f"⚡ `{gw_name}` | ⏱ `{result.get('elapsed','N/A')}`"
            )
            try:
                await bot_send(bot, uid, msg, InlineKeyboardMarkup(inline_keyboard=[]), fid)
            except Exception as e:
                logger.error(f"Bulk send declined: {e}")

        now = asyncio.get_running_loop().time()
        if now - last_update >= 2 or i == total or i % 5 == 0:
            try:
                status = '🛑 جاري الإيقاف...' if state_data.get('bulk_cancel') else '⏳ يرجى الانتظار...'
                cap = (f"⚡ *جاري الفحص...*\n\n`{progress_bar(i,total)}`\n"
                       f"📊 `{i}/{total}`  ✅`{len(approved_list)}`  ⚠️`{errors}`\n\n{status}")
                if prog_msg.photo:
                    await prog_msg.edit_caption(caption=cap, reply_markup=stop_kb, parse_mode="Markdown")
                else:
                    await prog_msg.edit_text(text=cap, reply_markup=stop_kb, parse_mode="Markdown")
                last_update = now
            except Exception:
                pass

        await asyncio.sleep(0.2)

    await state.update_data(is_checking=False)

    if approved_list:
        content = "\n".join(
            f"{i['card']['number']}|{i['card']['month']}|{i['card']['year']}|{i['card']['cvv']}"
            for i in approved_list
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(content)
            tmp = f.name
        try:
            await bot.send_document(
                chat_id=uid,
                document=FSInputFile(tmp),
                caption=f"✅ Approved: {len(approved_list)} / {checked}",
                filename=f"approved_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
        except Exception as e:
            logger.error(f"File send: {e}")
        finally:
            os.remove(tmp)

    icon = "🛑 توقّف" if (await state.get_data()).get('bulk_cancel') else "✅ اكتمل"
    final = (f"╔══════════════════════╗\n║   {icon}   ║\n╚══════════════════════╝\n\n"
             f"📊 `{checked}/{total}`  ✅`{len(approved_list)}`  ⚠️`{errors}`")
    final_kb = InlineKeyboardMarkup(inline_keyboard=[
        [_btn(s(uid, "main_menu_btn"), callback_data="main_menu", style="primary")]
    ])
    try:
        if prog_msg.photo:
            await prog_msg.edit_caption(caption=final, reply_markup=final_kb, parse_mode="Markdown")
        else:
            await prog_msg.edit_text(text=final, reply_markup=final_kb, parse_mode="Markdown")
    except Exception:
        pass


# ══════════════════════════════════════════════════════
#  Web panel & startup
# ══════════════════════════════════════════════════════

def _start_web_panel():
    try:
        from web_panel import app as flask_app
        port = int(os.environ.get("WEB_PORT", 5000))
        logger.info(f"🌐 Web panel starting on port {port}")
        flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Web panel error: {e}")


async def on_startup(bot: Bot):
    await get_banner(bot)
    t = threading.Thread(target=_start_web_panel, daemon=True, name="WebPanel")
    t.start()
    logger.info("Bot initialized. Banner cached. Web panel thread started.")


# ══════════════════════════════════════════════════════
#  ERROR HANDLER
# ══════════════════════════════════════════════════════

@router.errors()
async def error_handler(event):
    """Log errors and prevent bot hanging"""
    exception = event.exception
    update = event.update
    logger.error(f"Exception while handling update: {exception}", exc_info=exception)

    if update and hasattr(update, 'message') and update.message:
        try:
            await update.message.answer("⚠️ حدث خطأ في الاتصال. يرجى المحاولة مرة أخرى.")
        except Exception:
            pass


# ══════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN غير موجود!")
        return

    bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.startup.register(on_startup)
    dp.include_router(router)

    print("🚀 البوت يعمل...")
    dp.run_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
