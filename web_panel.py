import os
import sys
import random
import string
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

sys.path.insert(0, os.path.dirname(__file__))
from database import DatabaseManager
from config import ADMIN_PASSWORD, SUPPORT_USERNAME, BOT_SIGNATURE

app = Flask(__name__)
app.secret_key = ADMIN_PASSWORD + "_web_panel_secret"
db = DatabaseManager()

WEB_PORT = int(os.environ.get("WEB_PORT", 5000))

# ─────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────
#  Base HTML template
# ─────────────────────────────────────────

BASE = """
    ⚡ BuyShazam
    لوحة التحكم
[ لوحة التحكم
    ]({{ url_for('dashboard') }})
[ المستخدمون
    ]({{ url_for('users') }})
[ أكواد التفعيل
    ]({{ url_for('codes') }})
[ البوابات
    ]({{ url_for('gateways') }})
[ البروكسيات
    ]({{ url_for('proxies') }})
[ السجلات
    ]({{ url_for('logs') }})
[ تسجيل الخروج
    ]({{ url_for('logout') }})
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in msgs %}
      
        {{ msg }}
        
    {% endfor %}
  {% endwith %}

  {% block content %}{% endblock %}

"""

# ─────────────────────────────────────────
#  Login
# ─────────────────────────────────────────

LOGIN_HTML = """
⚡
BuyShazam Panel
أدخل كلمة المرور للدخول
  {% if error %}
   ❌ كلمة المرور غير صحيحة 
  {% endif %}
   دخول 
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True  # ✅ تم الإصلاح
            return redirect(url_for('dashboard'))
        return render_template_string(LOGIN_HTML, error=True)
    return render_template_string(LOGIN_HTML, error=False)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))  # ✅ تم الإصلاح

# ─────────────────────────────────────────
#  Dashboard
# ─────────────────────────────────────────

DASHBOARD_HTML = BASE + """
{% block content %}
 📊 لوحة التحكم نظرة عامة على البوت  المستخدمون {{ total_users }} {{ active_users }} نشط  البوابات {{ gateways }}  البروكسيات {{ proxies }}  الفحوصات {{ logs }}  إحصائيات آخر 7 أيام
| التاريخ
|الكل
|✅ موافق
|❌ مرفوض
|⚠️ أخطاء
|
| ---|---|---|---|---|
        {% for s in stats %}
        
| {{ s.date }}
|{{ s.total_checks }}
|{{ s.approved }}
|{{ s.declined }}
|{{ s.errors }}
|
| ---|---|---|---|---|
        {% else %}
        
| لا توجد بيانات بعد
|لا توجد بيانات بعد
|لا توجد بيانات بعد
|لا توجد بيانات بعد
|لا توجد بيانات بعد
|
| ---|---|---|---|---|
        {% endfor %}
      
{% endblock %}
"""

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML,
        active='dashboard',
        total_users=db.count_users(),
        active_users=db.count_active_users(),
        gateways=db.count_active_gateways(),
        proxies=db.count_active_proxies(),
        logs=db.count_logs(),
        stats=db.get_stats()[:7]
    )

# ─────────────────────────────────────────
#  Users
# ─────────────────────────────────────────

USERS_HTML = BASE + """
{% block content %} المستخدمونإدارة مستخدمي البوت
| المستخدم
|المعرّف
|الحالة
|الانتهاء
|فحوصات
|إجراءات
|
| ---|---|---|---|---|---|
        {% for u in users %}
        
| 
            {% if u.username %} @{{ u.username }} {% else %} لا يوجد {% endif %}
            {% if u.first_name %} {{ u.first_name }} {% endif %}
          
|{{ u.user_id }}
|
            {% if u.is_blocked %}
               🚫 محظور 
            {% elif u.subscription_expiry and u.subscription_expiry > now %}
               ✅ نشط 
            {% else %}
               ❌ منتهي 
            {% endif %}
          
|
            {% if u.subscription_expiry %}
               {{ u.subscription_expiry[:16] }} 
            {% else %}—{% endif %}
          
|{{ u.total_checks or 0 }}
|                     
|
| ---|---|---|---|---|---|
        {% endfor %}
      
⏰ تمديد الاشتراك
عدد الساعات24 = يوم | 168 = أسبوع | 720 = شهرإلغاءتمديد
{% endblock %}
"""

@app.route('/users')
@login_required
def users():
    return render_template_string(USERS_HTML,
        active='users',
        users=db.get_all_users(),
        now=datetime.now().isoformat()
    )

@app.route('/users/extend', methods=['POST'])
@login_required
def users_extend():
    uid = int(request.form['user_id'])
    hours = int(request.form['hours'])
    new_exp = db.extend_subscription_hours(uid, hours)
    flash(f'✅ تم تمديد الاشتراك حتى {new_exp.strftime("%Y-%m-%d %H:%M")}', 'success')
    return redirect(url_for('users'))

@app.route('/users/toggle-block', methods=['POST'])
@login_required
def users_toggle_block():
    uid = int(request.form['user_id'])
    block = int(request.form['block'])
    if block:
        db.block_user(uid)
        flash(f'🚫 تم حظر المستخدم {uid}', 'danger')
    else:
        db.unblock_user(uid)
        flash(f'✅ تم رفع الحظر عن {uid}', 'success')
    return redirect(url_for('users'))

# ─────────────────────────────────────────
#  Codes
# ─────────────────────────────────────────

CODES_HTML = BASE + """
{% block content %}
 أكواد التفعيل إنشاء كود
  إدارة أكواد اشتراك المستخدمين
| الكود
|الوصف
|المدة
|الاستخدام
|تاريخ الإنشاء
|
| ---|---|---|---|---|
        {% for c in codes %}
        
| {{ c.code }}
|{{ c.label or '—' }}
|
            {% set hrs = c.duration_hours if c.duration_hours else c.duration_days * 24 %}
            {% if hrs >= 720 %} {{ (hrs // 720) }} شهر 
            {% elif hrs >= 168 %} {{ (hrs // 168) }} أسبوع 
            {% elif hrs >= 24 %} {{ (hrs // 24) }} يوم 
            {% else %} {{ hrs }} ساعة 
            {% endif %}
             ({{ hrs }}h)  
|  
              {{ c.used_count }}/{{ c.max_uses }}
              
|{{ c.created_at[:16] }}
|         
|
| ---|---|---|---|---|---|
        {% else %}
        
| لا توجد أكواد بعد
|لا توجد أكواد بعد
|لا توجد أكواد بعد
|لا توجد أكواد بعد
|لا توجد أكواد بعد
|لا توجد أكواد بعد
|
| ---|---|---|---|---|---|
        {% endfor %}
      
 إنشاء كود جديد
الوصف / الاسم (اختياري) المدة بالساعات  * 1 ساعة | 24 = يوم | 168 = أسبوع | 720 = شهر عدد مرات الاستخدام الكود (فارغ = توليد تلقائي) إلغاء  إنشاء 
{% endblock %}
"""

@app.route('/codes')
@login_required
def codes():
    return render_template_string(CODES_HTML, active='codes', codes=db.get_all_codes())

@app.route('/codes/create', methods=['POST'])
@login_required
def codes_create():
    label = request.form.get('label', '').strip()
    hours = int(request.form.get('hours', 24))
    max_uses = int(request.form.get('max_uses', 1))
    custom_code = request.form.get('custom_code', '').strip().upper()
    code = custom_code or ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    try:
        db.create_code(code, label, hours, max_uses, 0)
        flash(f'✅ تم إنشاء الكود: {code} — {hours} ساعة — {max_uses} استخدام', 'success')
    except Exception as e:
        flash(f'❌ خطأ: {e}', 'danger')
    return redirect(url_for('codes'))

@app.route('/codes/delete', methods=['POST'])
@login_required
def codes_delete():
    db.delete_code(int(request.form['code_id']))
    flash('🗑 تم حذف الكود', 'info')
    return redirect(url_for('codes'))

# ─────────────────────────────────────────
#  Gateways
# ─────────────────────────────────────────

GATEWAYS_HTML = BASE + """
{% block content %}
  البوابات  إضافة بوابة
   إدارة بوابات فحص الكروت 
  {% for gw in gateways %}
   ⚡ {{ gw.display_name }} زرار: {{ gw.button_name }} Endpoint:
{{ gw.api_endpoint[:60] }}{% if gw.api_endpoint|length > 60 %}…{% endif %}
Method:{{ gw.method }}
        {% if gw.success_pattern %}Success:
{{ gw.success_pattern }}
{% endif %}
        {% if gw.decline_pattern %}Decline:
{{ gw.decline_pattern }}
{% endif %}
      
  {% else %}
  
لا توجد بوابات بعد. أضف أول بوابة!
  {% endfor %}
 إضافة بوابة جديدة
اسم البوابة (داخلي) اسم الزرار (للمستخدم) رابط API (Endpoint) الميثود POST GET Headers (JSON) {} Body Template متغيرات: {card} {month} {year} {cvv} Success Pattern (Regex) Decline Pattern (Regex) Error Pattern (Regex) Timeout (ثانية) إلغاء  إضافة 
{% endblock %}
"""

@app.route('/gateways')
@login_required
def gateways():
    return render_template_string(GATEWAYS_HTML, active='gateways', gateways=db.get_all_gateways())

@app.route('/gateways/add', methods=['POST'])
@login_required
def gateways_add():
    try:
        headers = request.form.get('headers', '{}')
        try:
            json.loads(headers)
        except Exception:
            headers = '{}'
        db.add_gateway({
            'display_name': request.form['display_name'],
            'button_name':  request.form['button_name'],
            'endpoint':     request.form['endpoint'],
            'method':       request.form.get('method', 'POST'),
            'headers':      headers,
            'body':         request.form.get('body', ''),
            'success':      request.form.get('success', ''),
            'decline':      request.form.get('decline', ''),
            'error':        request.form.get('error', ''),
            'timeout':      int(request.form.get('timeout', 30)),
        })
        flash(f'✅ تمت إضافة البوابة: {request.form["display_name"]}', 'success')
    except Exception as e:
        flash(f'❌ خطأ: {e}', 'danger')
    return redirect(url_for('gateways'))

@app.route('/gateways/delete', methods=['POST'])
@login_required
def gateways_delete():
    db.delete_gateway(int(request.form['gw_id']))
    flash('🗑 تم حذف البوابة', 'info')
    return redirect(url_for('gateways'))

#  ─────────────────────────────────────────
#  Proxies
# ─────────────────────────────────────────

PROXIES_HTML = BASE + """
{% block content %}
  البروكسيات  إضافة
      حذف الكل {{ proxies|length }} بروكسي — {{ active_count }} نشط
| #
|البروكسي
|البروتوكول
|الحالة
|أخطاء
|
| ---|---|---|---|---|
        {% for p in proxies %}
        
| {{ loop.index }}
|{{ p.proxy_string }}
|{{ p.protocol }}
|
            {% if p.is_active and p.fail_count  < 5 %}
               ✅ نشط 
            {% else %}
               ❌ معطّل 
            {% endif %}
          
|{{ p.fail_count }}
|         
|
| ---|---|---|---|---|---|
        {% else %}
        
| لا توجد بروكسيات بعد
|لا توجد بروكسيات بعد
|لا توجد بروكسيات بعد
|لا توجد بروكسيات بعد
|لا توجد بروكسيات بعد
|لا توجد بروكسيات بعد
|
| ---|---|---|---|---|---|
        {% endfor %}
      
 إضافة بروكسيات
بروكسي واحد
إضافة متعددة
البروكسيإضافةالبروكسيات (سطر لكل بروكسي)إضافة الكل
{% endblock %}
"""

@app.route('/proxies')
@login_required
def proxies():
    all_p = db.get_all_proxies()
    return render_template_string(PROXIES_HTML,
        active='proxies',
        proxies=all_p,
        active_count=sum(1 for p in all_p if p['is_active'] and p['fail_count'] < 5)
    )

@app.route('/proxies/add', methods=['POST'])
@login_required
def proxies_add():
    proxy = request.form['proxy'].strip()
    if db.add_proxy(proxy):
        flash(f'✅ تمت إضافة البروكسي', 'success')
    else:
        flash('⚠️ البروكسي موجود مسبقاً', 'info')
    return redirect(url_for('proxies'))

@app.route('/proxies/bulk', methods=['POST'])
@login_required
def proxies_bulk():
    lines = request.form['proxies'].strip().splitlines()
    added = db.add_proxies_bulk(lines)
    flash(f'✅ تمت إضافة {added} بروكسي من أصل {len(lines)}', 'success')
    return redirect(url_for('proxies'))

@app.route('/proxies/delete', methods=['POST'])
@login_required
def proxies_delete():
    db.delete_proxy(int(request.form['proxy_id']))
    return redirect(url_for('proxies'))

@app.route('/proxies/clear', methods=['POST'])
@login_required
def proxies_clear():
    db.clear_all_proxies()
    flash('🗑 تم حذف جميع البروكسيات', 'info')
    return redirect(url_for('proxies'))

# ─────────────────────────────────────────
#  Logs
# ─────────────────────────────────────────

LOGS_HTML = BASE + """
{% block content %}
 سجل الفحوصاتآخر 100 عملية فحص
| الوقت
|المستخدم
|الكارت
|البوابة
|النتيجة
|
| ---|---|---|---|---|
        {% for l in logs %}
        
| {{ l.created_at[:16] }}
|{{ l.user_id }}
|****{{ l.card_last4 }}
|{{ l.gateway_name }}
|
            {% if 'APPROVED' in l.result_status %}
               ✅ {{ l.result_status }} 
            {% else %}
               ❌ {{ l.result_status }} 
            {% endif %}
          
|
| ---|---|---|---|---|
        {% else %}
        
| لا توجد سجلات
|لا توجد سجلات
|لا توجد سجلات
|لا توجد سجلات
|لا توجد سجلات
|
| ---|---|---|---|---|
        {% endfor %}
      
{% endblock %}
"""

@app.route('/logs')
@login_required
def logs():
    return render_template_string(LOGS_HTML, active='logs', logs=db.get_recent_logs(100))

# ─────────────────────────────────────────
#  Run
# ─────────────────────────────────────────

if __name__ == '__main__':
    print(f"🌐 Web Panel running on port {WEB_PORT}")
    app.run(host='0.0.0.0', port=WEB_PORT, debug=False, use_reloader=False)
