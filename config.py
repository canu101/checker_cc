import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "support")
BOT_SIGNATURE = os.environ.get("BOT_SIGNATURE", "Checked by / 𝓙𝓐𝓜𝓐𝓘𝓚𝓐 𝓒𝓗𝓔𝓒𝓚𝓔𝓡")
MAX_CARDS_REGULAR = int(os.environ.get("MAX_CARDS_REGULAR", "500"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "-1003938237452"))
BOT_PHOTO_URL = os.environ.get("BOT_PHOTO_URL", "")

STRINGS = {
    "ar": {
        "welcome_admin": "╔══════════════════╗\n║  👑  ADMIN PANEL  ║\n╚══════════════════╝\n\nمرحباً *{name}* 🎉\nلديك صلاحيات كاملة ✅",
        "welcome_sub": "╔══════════════════╗\n║  ⚡ CARD CHECKER  ║\n╚══════════════════╝\n\nأهلاً *{name}* 👋\n✅ اشتراكك فعّال حتى:\n`{exp}`",
        "welcome_guest": "╔══════════════════╗\n║  💳 CARD CHECKER  ║\n╚══════════════════╝\n\nأهلاً *{name}* 👋\n\n🔒 هذا البوت للمشتركين فقط\n📩 للاشتراك: @{support}",
        "menu_title": "╔══════════════════╗\n║  💳 CARD CHECKER  ║\n╚══════════════════╝\n\nأهلاً *{name}* 👋\nاختر من القائمة 👇",
        "btn_upload": "📂  رفع كروت (.txt)",
        "btn_check": "💳  فحص كارت",
        "btn_account": "👤  حسابي",
        "btn_history": "📊  السجل",
        "btn_redeem": "🎫  كود تفعيل",
        "btn_settings": "⚙️  الإعدادات",
        "btn_support": "📞  الدعم",
        "btn_subscribe": "💎  اشتراك",
        "btn_back": "🔙  رجوع",
        "btn_cancel": "❌  إلغاء",
        "upload_title": "📂 *رفع ملف كروت*\n\nأرسل ملف `.txt` يحتوي على الكروت\n\n📌 الصيغة لكل سطر:\n`NUMBER|MM|YYYY|CVV`\n\nمثال:\n`4111111111111111|09|2026|123`",
        "check_title": "💳 *فحص كارت واحد*\n\nأرسل بيانات الكارت:\n`NUMBER|MM|YYYY|CVV`\n\nمثال:\n`4111111111111111|09|2026|123`",
        "checking": "⏳ *جاري الفحص...*\n\n`لا تغلق النافذة`",
        "no_sub": "❌ الاشتراك مطلوب.",
        "no_gateways": "❌ لا توجد بوابات. تواصل مع الأدمن.",
        "invalid_format": "❌ صيغة خاطئة.\nاستخدم: `NUMBER|MM|YYYY|CVV`",
        "session_expired": "❌ انتهت الجلسة. ابدأ من جديد /start",
        "settings_title": "⚙️ *الإعدادات*\n\nاختر اللغة:",
        "lang_changed": "✅ تم تغيير اللغة.",
        "redeem_title": "🎫 *تفعيل كود*\n\nأرسل الكود:",
        "invalid_code": "❌ الكود غير صحيح.",
        "code_maxed": "❌ تم استخدام الكود بالكامل.",
        "redeemed": "✅ *تم التفعيل!*\n📅 صالح حتى: `{exp}`",
        "wrong_pass": "❌ كلمة مرور خاطئة.",
        "access_granted": "✅ تم الدخول!",
        "use_buttons": "استخدم الأزرار للتنقل 👇",
        "stop_btn": "🛑  إيقاف",
        "confirm_btn": "✅  تأكيد وابدأ",
        "change_gw_btn": "🔄  تغيير البوابة",
        "check_another": "🔍  فحص آخر",
        "try_again": "🔄  حاول مجدداً",
        "main_menu_btn": "🔙  الرئيسية",
    },
    "en": {
        "welcome_admin": "╔══════════════════╗\n║  👑  ADMIN PANEL  ║\n╚══════════════════╝\n\nWelcome *{name}* 🎉\nFull admin access ✅",
        "welcome_sub": "╔══════════════════╗\n║  ⚡ CARD CHECKER  ║\n╚══════════════════╝\n\nHello *{name}* 👋\n✅ Subscription active until:\n`{exp}`",
        "welcome_guest": "╔══════════════════╗\n║  💳 CARD CHECKER  ║\n╚══════════════════╝\n\nHello *{name}* 👋\n\n🔒 This bot is for subscribers only\n📩 Subscribe: @{support}",
        "menu_title": "╔══════════════════╗\n║  💳 CARD CHECKER  ║\n╚══════════════════╝\n\nHello *{name}* 👋\nChoose from the menu 👇",
        "btn_upload": "📂  Upload Cards (.txt)",
        "btn_check": "💳  Check Card",
        "btn_account": "👤  My Account",
        "btn_history": "📊  History",
        "btn_redeem": "🎫  Redeem Code",
        "btn_settings": "⚙️  Settings",
        "btn_support": "📞  Support",
        "btn_subscribe": "💎  Subscribe",
        "btn_back": "🔙  Back",
        "btn_cancel": "❌  Cancel",
        "upload_title": "📂 *Upload Cards File*\n\nSend a `.txt` file with cards\n\n📌 Format per line:\n`NUMBER|MM|YYYY|CVV`\n\nExample:\n`4111111111111111|09|2026|123`",
        "check_title": "💳 *Check Single Card*\n\nSend card data:\n`NUMBER|MM|YYYY|CVV`\n\nExample:\n`4111111111111111|09|2026|123`",
        "checking": "⏳ *Checking...*\n\n`Please wait`",
        "no_sub": "❌ Subscription required.",
        "no_gateways": "❌ No active gateways. Contact admin.",
        "invalid_format": "❌ Invalid format.\nUse: `NUMBER|MM|YYYY|CVV`",
        "session_expired": "❌ Session expired. Start again /start",
        "settings_title": "⚙️ *Settings*\n\nSelect language:",
        "lang_changed": "✅ Language changed.",
        "redeem_title": "🎫 *Redeem Code*\n\nSend your code:",
        "invalid_code": "❌ Invalid code.",
        "code_maxed": "❌ Code has been fully used.",
        "redeemed": "✅ *Activated!*\n📅 Valid until: `{exp}`",
        "wrong_pass": "❌ Wrong password.",
        "access_granted": "✅ Access granted!",
        "use_buttons": "Use the buttons below 👇",
        "stop_btn": "🛑  Stop",
        "confirm_btn": "✅  Confirm & Start",
        "change_gw_btn": "🔄  Change Gateway",
        "check_another": "🔍  Check Another",
        "try_again": "🔄  Try Again",
        "main_menu_btn": "🔙  Main Menu",
    }
}

def t(user_id, key, **kwargs):
    from database import DatabaseManager
    db = DatabaseManager()
    lang = db.get_user_language(user_id)
    strings = STRINGS.get(lang, STRINGS["ar"])
    text = strings.get(key, STRINGS["ar"].get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text
