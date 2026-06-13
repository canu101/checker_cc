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
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ BuyShazam Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .nav {
            background: #f8f9fa;
            padding: 15px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            border-bottom: 2px solid #e9ecef;
        }
        .nav a {
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            transition: all 0.3s;
        }
        .nav a:hover { background: #764ba2; transform: translateY(-2px); }
        .nav a.active { background: #764ba2; }
        .content { padding: 30px; }
        .flash {
            padding: 15px;
            margin: 15px 0;
            border-radius: 8px;
            font-weight: bold;
        }
        .flash.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash.danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .flash.info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        th, td {
            padding: 15px;
            text-align: right;
            border-bottom: 1px solid #e9ecef;
        }
        th { background: #667eea; color: white; font-weight: 600; }
        tr:hover { background: #f8f9fa; }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-primary:hover { background: #764ba2; }
        .btn-success { background: #28a745; color: white; }
        .btn-success:hover { background: #218838; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-danger:hover { background: #c82333; }
        .form-group { margin: 20px 0; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-card h3 { font-size: 2.5em; margin-bottom: 10px; }
        .stat-card p { font-size: 1.1em; opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ BuyShazam Panel</h1>
            <p>لوحة التحكم</p>
        </div>
        
        <div class="nav">
            <a href="{{ url_for('dashboard') }}" {% if active == 'dashboard' %}class="active"{% endif %}>📊 لوحة التحكم</a>
            <a href="{{ url_for('users') }}" {% if active == 'users' %}class="active"{% endif %}>👥 المستخدمون</a>
            <a href="{{ url_for('codes') }}" {% if active == 'codes' %}class="active"{% endif %}>🎫 أكواد التفعيل</a>
            <a href="{{ url_for('gateways') }}" {% if active == 'gateways' %}class="active"{% endif %}>⚡ البوابات</a>
            <a href="{{ url_for('proxies') }}" {% if active == 'proxies' %}class="active"{% endif %}>🔌 البروكسيات</a>
            <a href="{{ url_for('logs') }}" {% if active == 'logs' %}class="active"{% endif %}>📋 السجلات</a>
            <a href="{{ url_for('logout') }}">🚪 تسجيل الخروج</a>
        </div>
        
        <div class="content">
            {% with msgs = get_flashed_messages(with_categories=true) %}
                {% for cat,msg in msgs %}
                    <div class="flash {{ cat }}">{{ msg }}</div>
                {% endfor %}
            {% endwith %}
            
            {% block content %}{% endblock %}
        </div>
    </div>
</body>
</html>
"""

# ─────────────────────────────────────────
#  Login
# ─────────────────────────────────────────

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ BuyShazam - تسجيل الدخول</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .login-box h1 {
            text-align: center;
            color: #667eea;
            margin-bottom: 30px;
            font-size: 2em;
        }
        .form-group { margin: 20px 0; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
        .form-group input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
            transition: all 0.3s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>⚡ BuyShazam Panel</h1>
        {% if error %}
            <div class="error">❌ كلمة المرور غير صحيحة</div>
        {% endif %}
        <form method="POST" action="{{ url_for('login') }}">
            <div class="form-group">
                <label>🔐 كلمة المرور</label>
                <input type="password" name="password" placeholder="أدخل كلمة المرور" required autofocus>
            </div>
            <button type="submit" class="btn">دخول</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True  # ✅ تم الإصلاح
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
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
<h2 style="margin-bottom: 20px;">📊 لوحة التحكم</h2>
<p style="margin-bottom: 30px; color: #666;">نظرة عامة على البوت</p>

<div class="stats-grid">
    <div class="stat-card">
        <h3>{{ total_users }}</h3>
        <p>👥 المستخدمون</p>
    </div>
    <div class="stat-card">
        <h3>{{ active_users }}</h3>
        <p>✅ نشط</p>
    </div>
    <div class="stat-card">
        <h3>{{ gateways }}</h3>
        <p>⚡ البوابات</p>
    </div>
    <div class="stat-card">
        <h3>{{ proxies }}</h3>
        <p>🔌 البروكسيات</p>
    </div>
    <div class="stat-card">
        <h3>{{ logs }}</h3>
        <p>📋 الفحوصات</p>
    </div>
</div>

<div class="card">
    <h3 style="margin-bottom: 20px;">📈 إحصائيات آخر 7 أيام</h3>
    <table>
        <thead>
            <tr>
                <th>التاريخ</th>
                <th>الكل</th>
                <th>✅ موافق</th>
                <th>❌ مرفوض</th>
                <th>⚠️ أخطاء</th>
            </tr>
        </thead>
        <tbody>
            {% for s in stats %}
            <tr>
                <td>{{ s.date }}</td>
                <td>{{ s.total_checks }}</td>
                <td style="color: green;">{{ s.approved }}</td>
                <td style="color: red;">{{ s.declined }}</td>
                <td style="color: orange;">{{ s.errors }}</td>
            </tr>
            {% else %}
            <tr>
                <td colspan="5" style="text-align: center; color: #999;">لا توجد بيانات بعد</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
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
{% block content %}
<h2 style="margin-bottom: 20px;">👥 المستخدمون</h2>
<p style="margin-bottom: 30px; color: #666;">إدارة مستخدمي البوت</p>

<table>
    <thead>
        <tr>
            <th>المستخدم</th>
            <th>المعرّف</th>
            <th>الحالة</th>
            <th>الانتهاء</th>
            <th>فحوصات</th>
            <th>إجراءات</th>
        </tr>
    </thead>
    <tbody>
        {% for u in users %}
        <tr>
            <td>
                {% if u.username %}@{{ u.username }}{% else %}لا يوجد{% endif %}
                {% if u.first_name %}<br><small>{{ u.first_name }}</small>{% endif %}
            </td>
            <td><code>{{ u.user_id }}</code></td>
            <td>
                {% if u.is_blocked %}
                    <span style="color: red;">🚫 محظور</span>
                {% elif u.subscription_expiry and u.subscription_expiry > now %}
                    <span style="color: green;">✅ نشط</span>
                {% else %}
                    <span style="color: gray;">❌ منتهي</span>
                {% endif %}
            </td>
            <td>
                {% if u.subscription_expiry %}
                    {{ u.subscription_expiry[:16] }}
                {% else %}—{% endif %}
            </td>
            <td>{{ u.total_checks or 0 }}</td>
            <td>
                <form method="POST" action="{{ url_for('users_extend') }}" style="display: inline;">
                    <input type="hidden" name="user_id" value="{{ u.user_id }}">
                    <input type="number" name="hours" value="24" min="1" style="width: 80px; padding: 5px;">
                    <button type="submit" class="btn btn-success" style="padding: 5px 10px; font-size: 12px;">تمديد</button>
                </form>
                <form method="POST" action="{{ url_for('users_toggle_block') }}" style="display: inline;">
                    <input type="hidden" name="user_id" value="{{ u.user_id }}">
                    <input type="hidden" name="block" value="{{ 0 if u.is_blocked else 1 }}">
                    <button type="submit" class="btn btn-danger" style="padding: 5px 10px; font-size: 12px;">
                        {{ "رفع الحظر" if u.is_blocked else "حظر" }}
                    </button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
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
<h2 style="margin-bottom: 20px;">🎫 أكواد التفعيل</h2>

<div class="card">
    <h3 style="margin-bottom: 20px;">➕ إنشاء كود جديد</h3>
    <form method="POST" action="{{ url_for('codes_create') }}">
        <div class="form-group">
            <label>الوصف / الاسم (اختياري)</label>
            <input type="text" name="label" placeholder="مثال: كود تجريبي">
        </div>
        <div class="form-group">
            <label>المدة بالساعات</label>
            <input type="number" name="hours" value="24" min="1" required>
            <small style="color: #666;">* 1 ساعة | 24 = يوم | 168 = أسبوع | 720 = شهر</small>
        </div>
        <div class="form-group">
            <label>عدد مرات الاستخدام</label>
            <input type="number" name="max_uses" value="1" min="1" required>
        </div>
        <div class="form-group">
            <label>الكود (فارغ = توليد تلقائي)</label>
            <input type="text" name="custom_code" placeholder="اتركه فارغاً للتوليد التلقائي">
        </div>
        <button type="submit" class="btn btn-success">إنشاء الكود</button>
    </form>
</div>

<div class="card">
    <h3 style="margin-bottom: 20px;">📋 إدارة الأكواد</h3>
    <table>
        <thead>
            <tr>
                <th>الكود</th>
                <th>الوصف</th>
                <th>المدة</th>
                <th>الاستخدام</th>
                <th>تاريخ الإنشاء</th>
                <th>إجراء</th>
            </tr>
        </thead>
        <tbody>
            {% for c in codes %}
            <tr>
                <td><code>{{ c.code }}</code></td>
                <td>{{ c.label or '—' }}</td>
                <td>
                    {% set hrs = c.duration_hours if c.duration_hours else c.duration_days * 24 %}
                    {% if hrs >= 720 %}{{ (hrs // 720) }} شهر
                    {% elif hrs >= 168 %}{{ (hrs // 168) }} أسبوع
                    {% elif hrs >= 24 %}{{ (hrs // 24) }} يوم
                    {% else %}{{ hrs }} ساعة{% endif %}
                </td>
                <td>{{ c.used_count }}/{{ c.max_uses }}</td>
                <td>{{ c.created_at[:16] }}</td>
                <td>
                    <form method="POST" action="{{ url_for('codes_delete') }}" style="display: inline;">
                        <input type="hidden" name="code_id" value="{{ c.id }}">
                        <button type="submit" class="btn btn-danger" style="padding: 5px 10px; font-size: 12px;">حذف</button>
                    </form>
                </td>
            </tr>
            {% else %}
            <tr>
                <td colspan="6" style="text-align: center; color: #999;">لا توجد أكواد بعد</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

@app.route('/codes')
@login_required
def codes():
    return render_template_string(CODES_HTML, active='codes', codes=db.get_all_codes())

@app.route('/codes/create', methods=['POST'])  # ✅ تم الإصلاح
@login_required
def codes_create():
    label = request.form.get('label', '').strip()
    hours = int(request.form.get('hours', 24))
    max_uses = int(request.form.get('max_uses', 1))  # ✅ تم الإصلاح
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
<h2 style="margin-bottom: 20px;">⚡ البوابات</h2>

<div class="card">
    <h3 style="margin-bottom: 20px;">➕ إضافة بوابة جديدة</h3>
    <form method="POST" action="{{ url_for('gateways_add') }}">
        <div class="form-group">
            <label>اسم البوابة (داخلي)</label>
            <input type="text" name="display_name" required>
        </div>
        <div class="form-group">
            <label>اسم الزرار (للمستخدم)</label>
            <input type="text" name="button_name" required>
        </div>
        <div class="form-group">
            <label>رابط API (Endpoint)</label>
            <input type="text" name="endpoint" required placeholder="https://api.example.com/charge">
        </div>
        <div class="form-group">
            <label>الميثود</label>
            <select name="method">
                <option value="POST">POST</option>
                <option value="GET">GET</option>
            </select>
        </div>
        <div class="form-group">
            <label>Headers (JSON)</label>
            <textarea name="headers" rows="3" placeholder='{"Content-Type": "application/json"}'>{}</textarea>
        </div>
        <div class="form-group">
            <label>Body Template</label>
            <textarea name="body" rows="3" placeholder="amount=100&card={card}&month={month}&year={year}&cvv={cvv}"></textarea>
            <small style="color: #666;">متغيرات: {card} {month} {year} {cvv}</small>
        </div>
        <div class="form-group">
            <label>Success Pattern (Regex)</label>
            <input type="text" name="success" placeholder="succeeded|approved">
        </div>
        <div class="form-group">
            <label>Decline Pattern (Regex)</label>
            <input type="text" name="decline" placeholder="declined|rejected">
        </div>
        <div class="form-group">
            <label>Error Pattern (Regex)</label>
            <input type="text" name="error" placeholder="error|failed">
        </div>
        <div class="form-group">
            <label>Timeout (ثانية)</label>
            <input type="number" name="timeout" value="30" min="5" max="120">
        </div>
        <button type="submit" class="btn btn-success">إضافة البوابة</button>
    </form>
</div>

<div class="card">
    <h3 style="margin-bottom: 20px;">📋 البوابات النشطة</h3>
    {% for gw in gateways %}
    <div style="border: 1px solid #e9ecef; padding: 15px; margin: 10px 0; border-radius: 8px;">
        <h4>⚡ {{ gw.display_name }}</h4>
        <p><strong>زرار:</strong> {{ gw.button_name }}</p>
        <p><strong>Endpoint:</strong> <code>{{ gw.api_endpoint[:60] }}{% if gw.api_endpoint|length > 60 %}…{% endif %}</code></p>
        <p><strong>Method:</strong> {{ gw.method }}</p>
        {% if gw.success_pattern %}<p><strong>Success:</strong> <code>{{ gw.success_pattern }}</code></p>{% endif %}
        {% if gw.decline_pattern %}<p><strong>Decline:</strong> <code>{{ gw.decline_pattern }}</code></p>{% endif %}
        {% if gw.id > 0 %}
        <form method="POST" action="{{ url_for('gateways_delete') }}" style="margin-top: 10px;">
            <input type="hidden" name="gw_id" value="{{ gw.id }}">
            <button type="submit" class="btn btn-danger" style="padding: 5px 15px; font-size: 12px;">حذف</button>
        </form>
        {% else %}
        <p style="color: #999; font-size: 12px;">🔒 بوابة مدمجة (لا يمكن حذفها)</p>
        {% endif %}
    </div>
    {% else %}
    <p style="text-align: center; color: #999;">لا توجد بوابات بعد. أضف أول بوابة!</p>
    {% endfor %}
</div>
{% endblock %}
"""

@app.route('/gateways')
@login_required
def gateways():
    return render_template_string(GATEWAYS_HTML, active='gateways', gateways=db.get_all_gateways())

@app.route('/gateways/add', methods=['POST'])  # ✅ تم الإصلاح
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
            'button_name': request.form['button_name'],
            'endpoint': request.form['endpoint'],
            'method': request.form.get('method', 'POST'),
            'headers': headers,
            'body': request.form.get('body', ''),
            'success': request.form.get('success', ''),
            'decline': request.form.get('decline', ''),
            'error': request.form.get('error', ''),
            'timeout': int(request.form.get('timeout', 30)),
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

# ─────────────────────────────────────────
#  Proxies
# ─────────────────────────────────────────

PROXIES_HTML = BASE + """
{% block content %}
<h2 style="margin-bottom: 20px;">🔌 البروكسيات</h2>
<p style="margin-bottom: 30px; color: #666;">{{ proxies|length }} بروكسي — {{ active_count }} نشط</p>

<div class="card">
    <h3 style="margin-bottom: 20px;">➕ إضافة بروكسي</h3>
    <form method="POST" action="{{ url_for('proxies_add') }}">
        <div class="form-group">
            <label>البروكسي</label>
            <input type="text" name="proxy" placeholder="host:port أو http://user:pass@host:port" required>
        </div>
        <button type="submit" class="btn btn-success">إضافة</button>
    </form>
</div>

<div class="card">
    <h3 style="margin-bottom: 20px;">📁 إضافة متعددة</h3>
    <form method="POST" action="{{ url_for('proxies_bulk') }}">
        <div class="form-group">
            <label>البروكسيات (سطر لكل بروكسي)</label>
            <textarea name="proxies" rows="5" placeholder="host1:port1&#10;host2:port2&#10;http://user:pass@host3:port3"></textarea>
        </div>
        <button type="submit" class="btn btn-primary">إضافة الكل</button>
    </form>
</div>

<div class="card">
    <h3 style="margin-bottom: 20px;">📋 البروكسيات النشطة</h3>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>البروكسي</th>
                <th>البروتوكول</th>
                <th>الحالة</th>
                <th>أخطاء</th>
                <th>إجراء</th>
            </tr>
        </thead>
        <tbody>
            {% for p in proxies %}
            <tr>
                <td>{{ loop.index }}</td>
                <td><code>{{ p.proxy_string }}</code></td>
                <td>{{ p.protocol }}</td>
                <td>
                    {% if p.is_active and p.fail_count < 5 %}
                        <span style="color: green;">✅ نشط</span>
                    {% else %}
                        <span style="color: red;">❌ معطّل</span>
                    {% endif %}
                </td>
                <td>{{ p.fail_count }}</td>
                <td>
                    <form method="POST" action="{{ url_for('proxies_delete') }}" style="display: inline;">
                        <input type="hidden" name="proxy_id" value="{{ p.id }}">
                        <button type="submit" class="btn btn-danger" style="padding: 5px 10px; font-size: 12px;">حذف</button>
                    </form>
                </td>
            </tr>
            {% else %}
            <tr>
                <td colspan="6" style="text-align: center; color: #999;">لا توجد بروكسيات بعد</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <form method="POST" action="{{ url_for('proxies_clear') }}" style="margin-top: 20px;">
        <button type="submit" class="btn btn-danger">🗑 حذف الكل</button>
    </form>
</div>
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
<h2 style="margin-bottom: 20px;">📋 سجل الفحوصات</h2>
<p style="margin-bottom: 30px; color: #666;">آخر 100 عملية فحص</p>

<div class="card">
    <table>
        <thead>
            <tr>
                <th>الوقت</th>
                <th>المستخدم</th>
                <th>الكارت</th>
                <th>البوابة</th>
                <th>النتيجة</th>
            </tr>
        </thead>
        <tbody>
            {% for l in logs %}
            <tr>
                <td>{{ l.created_at[:16] }}</td>
                <td><code>{{ l.user_id }}</code></td>
                <td><code>****{{ l.card_last4 }}</code></td>
                <td>{{ l.gateway_name }}</td>
                <td>
                    {% if 'APPROVED' in l.result_status %}
                        <span style="color: green;">✅ {{ l.result_status }}</span>
                    {% else %}
                        <span style="color: red;">❌ {{ l.result_status }}</span>
                    {% endif %}
                </td>
            </tr>
            {% else %}
            <tr>
                <td colspan="5" style="text-align: center; color: #999;">لا توجد سجلات</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
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
