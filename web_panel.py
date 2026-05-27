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
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BuyShazam — لوحة التحكم</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
<style>
  :root{--bg:#0d1117;--card:#161b22;--border:#30363d;--accent:#58a6ff;--green:#3fb950;--red:#f85149;--yellow:#d29922;--muted:#8b949e}
  *{box-sizing:border-box}
  body{background:var(--bg);color:#e6edf3;font-family:'Segoe UI',Tahoma,sans-serif;min-height:100vh}
  .sidebar{width:220px;min-height:100vh;background:var(--card);border-left:1px solid var(--border);position:fixed;right:0;top:0;padding:0;z-index:100}
  .sidebar .logo{padding:20px 16px;border-bottom:1px solid var(--border);font-size:1.1rem;font-weight:700;color:var(--accent)}
  .sidebar .logo span{font-size:.75rem;color:var(--muted);display:block;font-weight:400}
  .sidebar .nav-link{color:var(--muted);padding:10px 16px;border-radius:0;transition:.2s;display:flex;align-items:center;gap:8px;font-size:.9rem}
  .sidebar .nav-link:hover{color:#e6edf3;background:rgba(88,166,255,.08)}
  .sidebar .nav-link.active{color:var(--accent);background:rgba(88,166,255,.12);border-right:3px solid var(--accent)}
  .sidebar .nav-link i{font-size:1rem;width:18px}
  .main-content{margin-right:220px;padding:24px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:10px}
  .card-header{background:rgba(255,255,255,.03);border-bottom:1px solid var(--border);padding:14px 18px;font-weight:600}
  .stat-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;text-align:center}
  .stat-card .num{font-size:2rem;font-weight:700;margin:4px 0}
  .stat-card .lbl{color:var(--muted);font-size:.85rem}
  .stat-card.blue .num{color:var(--accent)}
  .stat-card.green .num{color:var(--green)}
  .stat-card.red .num{color:var(--red)}
  .stat-card.yellow .num{color:var(--yellow)}
  .badge-active{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.3);padding:3px 8px;border-radius:20px;font-size:.75rem}
  .badge-inactive{background:rgba(248,81,73,.1);color:var(--red);border:1px solid rgba(248,81,73,.25);padding:3px 8px;border-radius:20px;font-size:.75rem}
  .badge-admin{background:rgba(88,166,255,.1);color:var(--accent);border:1px solid rgba(88,166,255,.25);padding:3px 8px;border-radius:20px;font-size:.75rem}
  .table{color:#e6edf3}
  .table thead th{border-bottom:1px solid var(--border);color:var(--muted);font-weight:500;font-size:.85rem}
  .table td,.table th{border-color:var(--border);vertical-align:middle;padding:10px 14px}
  .table tbody tr:hover{background:rgba(255,255,255,.03)}
  .form-control,.form-select,.input-group-text{background:#0d1117;border-color:var(--border);color:#e6edf3}
  .form-control:focus,.form-select:focus{background:#0d1117;border-color:var(--accent);color:#e6edf3;box-shadow:0 0 0 .2rem rgba(88,166,255,.15)}
  .btn-primary{background:var(--accent);border-color:var(--accent);color:#0d1117;font-weight:600}
  .btn-primary:hover{background:#79b8ff;border-color:#79b8ff;color:#0d1117}
  .btn-danger{background:var(--red);border-color:var(--red)}
  .btn-success{background:var(--green);border-color:var(--green);color:#0d1117;font-weight:600}
  .btn-outline-secondary{border-color:var(--border);color:var(--muted)}
  .btn-outline-secondary:hover{background:rgba(255,255,255,.05);color:#e6edf3}
  .alert-success{background:rgba(63,185,80,.1);border:1px solid rgba(63,185,80,.3);color:var(--green)}
  .alert-danger{background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.3);color:var(--red)}
  .alert-info{background:rgba(88,166,255,.1);border:1px solid rgba(88,166,255,.3);color:var(--accent)}
  code{background:#0d1117;border:1px solid var(--border);padding:2px 6px;border-radius:4px;color:#e6edf3;font-size:.85rem}
  .modal-content{background:var(--card);border:1px solid var(--border)}
  .modal-header{border-bottom:1px solid var(--border)}
  .modal-footer{border-top:1px solid var(--border)}
  .page-title{font-size:1.4rem;font-weight:700;margin-bottom:6px}
  .page-sub{color:var(--muted);font-size:.85rem;margin-bottom:20px}
  ::-webkit-scrollbar{width:6px}
  ::-webkit-scrollbar-track{background:var(--bg)}
  ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
  @media(max-width:768px){.sidebar{width:100%;min-height:auto;position:relative}.main-content{margin-right:0}}
</style>
</head>
<body>

<div class="sidebar">
  <div class="logo">
    ⚡ BuyShazam
    <span>لوحة التحكم</span>
  </div>
  <nav class="nav flex-column mt-2">
    <a href="{{ url_for('dashboard') }}" class="nav-link {% if active=='dashboard' %}active{% endif %}">
      <i class="bi bi-speedometer2"></i> لوحة التحكم
    </a>
    <a href="{{ url_for('users') }}" class="nav-link {% if active=='users' %}active{% endif %}">
      <i class="bi bi-people"></i> المستخدمون
    </a>
    <a href="{{ url_for('codes') }}" class="nav-link {% if active=='codes' %}active{% endif %}">
      <i class="bi bi-ticket-perforated"></i> أكواد التفعيل
    </a>
    <a href="{{ url_for('gateways') }}" class="nav-link {% if active=='gateways' %}active{% endif %}">
      <i class="bi bi-lightning-charge"></i> البوابات
    </a>
    <a href="{{ url_for('proxies') }}" class="nav-link {% if active=='proxies' %}active{% endif %}">
      <i class="bi bi-hdd-network"></i> البروكسيات
    </a>
    <a href="{{ url_for('logs') }}" class="nav-link {% if active=='logs' %}active{% endif %}">
      <i class="bi bi-journal-text"></i> السجلات
    </a>
    <hr style="border-color:var(--border);margin:8px 16px">
    <a href="{{ url_for('logout') }}" class="nav-link text-danger">
      <i class="bi bi-box-arrow-left"></i> تسجيل الخروج
    </a>
  </nav>
</div>

<div class="main-content">
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in msgs %}
      <div class="alert alert-{{ cat }} alert-dismissible mb-3" role="alert">
        {{ msg }}
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endwith %}

  {% block content %}{% endblock %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
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
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تسجيل الدخول — BuyShazam</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
<style>
  body{background:#0d1117;color:#e6edf3;display:flex;align-items:center;justify-content:center;min-height:100vh}
  .login-card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:40px;width:100%;max-width:380px}
  .form-control{background:#0d1117;border-color:#30363d;color:#e6edf3}
  .form-control:focus{background:#0d1117;border-color:#58a6ff;color:#e6edf3;box-shadow:0 0 0 .2rem rgba(88,166,255,.15)}
  .btn-primary{background:#58a6ff;border-color:#58a6ff;color:#0d1117;font-weight:700}
  .btn-primary:hover{background:#79b8ff;border-color:#79b8ff}
  .alert-danger{background:rgba(248,81,73,.1);border:1px solid rgba(248,81,73,.3);color:#f85149}
</style>
</head>
<body>
<div class="login-card">
  <div class="text-center mb-4">
    <div style="font-size:2.5rem">⚡</div>
    <h4 style="font-weight:700;margin-top:8px">BuyShazam Panel</h4>
    <p style="color:#8b949e;font-size:.9rem">أدخل كلمة المرور للدخول</p>
  </div>
  {% if error %}
  <div class="alert alert-danger mb-3">❌ كلمة المرور غير صحيحة</div>
  {% endif %}
  <form method="POST">
    <div class="mb-3">
      <input type="password" name="password" class="form-control form-control-lg"
             placeholder="كلمة المرور" autofocus>
    </div>
    <button type="submit" class="btn btn-primary w-100 btn-lg">دخول</button>
  </form>
</div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
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
    return redirect(url_for('dashboard'))

# ─────────────────────────────────────────
#  Dashboard
# ─────────────────────────────────────────

DASHBOARD_HTML = BASE + """
{% block content %}
<div class="page-title">📊 لوحة التحكم</div>
<div class="page-sub">نظرة عامة على البوت</div>

<div class="row g-3 mb-4">
  <div class="col-6 col-md-3">
    <div class="stat-card blue">
      <div class="lbl"><i class="bi bi-people"></i> المستخدمون</div>
      <div class="num">{{ total_users }}</div>
      <div style="color:#8b949e;font-size:.8rem">{{ active_users }} نشط</div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="stat-card green">
      <div class="lbl"><i class="bi bi-lightning-charge"></i> البوابات</div>
      <div class="num">{{ gateways }}</div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="stat-card yellow">
      <div class="lbl"><i class="bi bi-hdd-network"></i> البروكسيات</div>
      <div class="num">{{ proxies }}</div>
    </div>
  </div>
  <div class="col-6 col-md-3">
    <div class="stat-card red">
      <div class="lbl"><i class="bi bi-journal-text"></i> الفحوصات</div>
      <div class="num">{{ logs }}</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-header"><i class="bi bi-bar-chart"></i> إحصائيات آخر 7 أيام</div>
  <div class="card-body p-0">
    <table class="table mb-0">
      <thead><tr><th>التاريخ</th><th>الكل</th><th>✅ موافق</th><th>❌ مرفوض</th><th>⚠️ أخطاء</th></tr></thead>
      <tbody>
        {% for s in stats %}
        <tr>
          <td><code>{{ s.date }}</code></td>
          <td>{{ s.total_checks }}</td>
          <td style="color:#3fb950">{{ s.approved }}</td>
          <td style="color:#f85149">{{ s.declined }}</td>
          <td style="color:#d29922">{{ s.errors }}</td>
        </tr>
        {% else %}
        <tr><td colspan="5" class="text-center" style="color:#8b949e;padding:30px">لا توجد بيانات بعد</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
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
<div class="page-title"><i class="bi bi-people"></i> المستخدمون</div>
<div class="page-sub">إدارة مستخدمي البوت</div>

<div class="card">
  <div class="card-body p-0">
    <table class="table mb-0">
      <thead>
        <tr>
          <th>المستخدم</th><th>المعرّف</th><th>الحالة</th>
          <th>الانتهاء</th><th>فحوصات</th><th>إجراءات</th>
        </tr>
      </thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>
            {% if u.username %}<strong>@{{ u.username }}</strong>{% else %}<span style="color:#8b949e">لا يوجد</span>{% endif %}
            {% if u.first_name %}<br><small style="color:#8b949e">{{ u.first_name }}</small>{% endif %}
          </td>
          <td><code>{{ u.user_id }}</code></td>
          <td>
            {% if u.is_blocked %}
              <span class="badge-inactive">🚫 محظور</span>
            {% elif u.subscription_expiry and u.subscription_expiry > now %}
              <span class="badge-active">✅ نشط</span>
            {% else %}
              <span class="badge-inactive">❌ منتهي</span>
            {% endif %}
          </td>
          <td>
            {% if u.subscription_expiry %}
              <small>{{ u.subscription_expiry[:16] }}</small>
            {% else %}—{% endif %}
          </td>
          <td>{{ u.total_checks or 0 }}</td>
          <td>
            <button class="btn btn-sm btn-primary" onclick="openExtend({{ u.user_id }}, '{{ u.first_name or u.user_id }}')" title="تمديد الاشتراك">
              <i class="bi bi-clock-history"></i>
            </button>
            <form method="POST" action="/users/toggle-block" style="display:inline">
              <input type="hidden" name="user_id" value="{{ u.user_id }}">
              <input type="hidden" name="block" value="{{ 0 if u.is_blocked else 1 }}">
              <button type="submit" class="btn btn-sm {{ 'btn-success' if u.is_blocked else 'btn-danger' }}" title="{{ 'رفع حظر' if u.is_blocked else 'حظر' }}">
                <i class="bi {{ 'bi-unlock' if u.is_blocked else 'bi-slash-circle' }}"></i>
              </button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Extend Modal -->
<div class="modal fade" id="extendModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">⏰ تمديد الاشتراك</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <form method="POST" action="/users/extend">
        <div class="modal-body">
          <input type="hidden" name="user_id" id="extendUserId">
          <p style="color:#8b949e" id="extendUserName"></p>
          <div class="mb-3">
            <label class="form-label">عدد الساعات</label>
            <input type="number" name="hours" class="form-control" placeholder="مثال: 24 = يوم، 168 = أسبوع" min="1" required>
            <div class="form-text text-muted">24 = يوم | 168 = أسبوع | 720 = شهر</div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">إلغاء</button>
          <button type="submit" class="btn btn-primary">تمديد</button>
        </div>
      </form>
    </div>
  </div>
</div>

<script>
function openExtend(uid, name){
  document.getElementById('extendUserId').value = uid;
  document.getElementById('extendUserName').textContent = 'المستخدم: ' + name + ' (' + uid + ')';
  new bootstrap.Modal(document.getElementById('extendModal')).show();
}
</script>
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
<div class="d-flex justify-content-between align-items-center mb-1">
  <div class="page-title"><i class="bi bi-ticket-perforated"></i> أكواد التفعيل</div>
  <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addCodeModal">
    <i class="bi bi-plus-lg"></i> إنشاء كود
  </button>
</div>
<div class="page-sub">إدارة أكواد اشتراك المستخدمين</div>

<div class="card">
  <div class="card-body p-0">
    <table class="table mb-0">
      <thead>
        <tr><th>الكود</th><th>الوصف</th><th>المدة</th><th>الاستخدام</th><th>تاريخ الإنشاء</th><th></th></tr>
      </thead>
      <tbody>
        {% for c in codes %}
        <tr>
          <td><code>{{ c.code }}</code></td>
          <td>{{ c.label or '—' }}</td>
          <td>
            {% set hrs = c.duration_hours if c.duration_hours else c.duration_days * 24 %}
            {% if hrs >= 720 %}<span style="color:#58a6ff">{{ (hrs // 720) }} شهر</span>
            {% elif hrs >= 168 %}<span style="color:#3fb950">{{ (hrs // 168) }} أسبوع</span>
            {% elif hrs >= 24 %}<span style="color:#d29922">{{ (hrs // 24) }} يوم</span>
            {% else %}<span style="color:#8b949e">{{ hrs }} ساعة</span>
            {% endif %}
            <small style="color:#8b949e">({{ hrs }}h)</small>
          </td>
          <td>
            <span class="{{ 'badge-active' if c.used_count < c.max_uses else 'badge-inactive' }}">
              {{ c.used_count }}/{{ c.max_uses }}
            </span>
          </td>
          <td><small>{{ c.created_at[:16] }}</small></td>
          <td>
            <form method="POST" action="/codes/delete" onsubmit="return confirm('حذف الكود؟')">
              <input type="hidden" name="code_id" value="{{ c.id }}">
              <button type="submit" class="btn btn-sm btn-danger"><i class="bi bi-trash"></i></button>
            </form>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="6" class="text-center" style="color:#8b949e;padding:30px">لا توجد أكواد بعد</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Code Modal -->
<div class="modal fade" id="addCodeModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title"><i class="bi bi-plus-lg"></i> إنشاء كود جديد</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <form method="POST" action="/codes/create">
        <div class="modal-body">
          <div class="mb-3">
            <label class="form-label">الوصف / الاسم (اختياري)</label>
            <input type="text" name="label" class="form-control" placeholder="مثال: اشتراك VIP">
          </div>
          <div class="mb-3">
            <label class="form-label">المدة بالساعات <span style="color:#f85149">*</span></label>
            <input type="number" name="hours" class="form-control" min="1" value="24" required>
            <div class="form-text text-muted">1 ساعة | 24 = يوم | 168 = أسبوع | 720 = شهر</div>
          </div>
          <div class="mb-3">
            <label class="form-label">عدد مرات الاستخدام</label>
            <input type="number" name="max_uses" class="form-control" min="1" value="1">
          </div>
          <div class="mb-3">
            <label class="form-label">الكود (فارغ = توليد تلقائي)</label>
            <input type="text" name="custom_code" class="form-control" placeholder="اتركه فارغاً للتوليد التلقائي">
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">إلغاء</button>
          <button type="submit" class="btn btn-primary"><i class="bi bi-plus-lg"></i> إنشاء</button>
        </div>
      </form>
    </div>
  </div>
</div>
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
<div class="d-flex justify-content-between align-items-center mb-1">
  <div class="page-title"><i class="bi bi-lightning-charge"></i> البوابات</div>
  <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addGwModal">
    <i class="bi bi-plus-lg"></i> إضافة بوابة
  </button>
</div>
<div class="page-sub">إدارة بوابات فحص الكروت</div>

<div class="row g-3">
  {% for gw in gateways %}
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span>⚡ {{ gw.display_name }}</span>
        <form method="POST" action="/gateways/delete" onsubmit="return confirm('حذف البوابة؟')">
          <input type="hidden" name="gw_id" value="{{ gw.id }}">
          <button type="submit" class="btn btn-sm btn-danger"><i class="bi bi-trash"></i></button>
        </form>
      </div>
      <div class="card-body" style="font-size:.875rem">
        <div class="mb-1"><span style="color:#8b949e">زرار:</span> <strong>{{ gw.button_name }}</strong></div>
        <div class="mb-1"><span style="color:#8b949e">Endpoint:</span> <code style="word-break:break-all">{{ gw.api_endpoint[:60] }}{% if gw.api_endpoint|length > 60 %}…{% endif %}</code></div>
        <div class="mb-1"><span style="color:#8b949e">Method:</span> <span class="badge-active">{{ gw.method }}</span></div>
        {% if gw.success_pattern %}<div class="mb-1"><span style="color:#8b949e">Success:</span> <code>{{ gw.success_pattern }}</code></div>{% endif %}
        {% if gw.decline_pattern %}<div class="mb-1"><span style="color:#8b949e">Decline:</span> <code>{{ gw.decline_pattern }}</code></div>{% endif %}
      </div>
    </div>
  </div>
  {% else %}
  <div class="col-12">
    <div class="card">
      <div class="card-body text-center" style="color:#8b949e;padding:40px">
        <i class="bi bi-lightning-charge" style="font-size:2rem"></i>
        <p class="mt-2">لا توجد بوابات بعد. أضف أول بوابة!</p>
      </div>
    </div>
  </div>
  {% endfor %}
</div>

<!-- Add Gateway Modal -->
<div class="modal fade" id="addGwModal" tabindex="-1">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title"><i class="bi bi-plus-lg"></i> إضافة بوابة جديدة</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <form method="POST" action="/gateways/add">
        <div class="modal-body">
          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label">اسم البوابة (داخلي)</label>
              <input type="text" name="display_name" class="form-control" placeholder="Stripe Test" required>
            </div>
            <div class="col-md-6">
              <label class="form-label">اسم الزرار (للمستخدم)</label>
              <input type="text" name="button_name" class="form-control" placeholder="Stripe" required>
            </div>
            <div class="col-md-9">
              <label class="form-label">رابط API (Endpoint)</label>
              <input type="text" name="endpoint" class="form-control" placeholder="https://api.example.com/charge" required>
            </div>
            <div class="col-md-3">
              <label class="form-label">الميثود</label>
              <select name="method" class="form-select">
                <option>POST</option>
                <option>GET</option>
              </select>
            </div>
            <div class="col-12">
              <label class="form-label">Headers (JSON)</label>
              <textarea name="headers" class="form-control" rows="2" placeholder='{"Content-Type": "application/json", "Authorization": "Bearer TOKEN"}'>{}</textarea>
            </div>
            <div class="col-12">
              <label class="form-label">Body Template</label>
              <textarea name="body" class="form-control" rows="3" placeholder='{"number":"{card}","exp_month":"{month}","exp_year":"{year}","cvc":"{cvv}"}'></textarea>
              <div class="form-text text-muted">متغيرات: {card} {month} {year} {cvv}</div>
            </div>
            <div class="col-md-4">
              <label class="form-label">Success Pattern (Regex)</label>
              <input type="text" name="success" class="form-control" placeholder="succeeded|approved">
            </div>
            <div class="col-md-4">
              <label class="form-label">Decline Pattern (Regex)</label>
              <input type="text" name="decline" class="form-control" placeholder="declined|failed">
            </div>
            <div class="col-md-4">
              <label class="form-label">Error Pattern (Regex)</label>
              <input type="text" name="error" class="form-control" placeholder="error|invalid">
            </div>
            <div class="col-md-4">
              <label class="form-label">Timeout (ثانية)</label>
              <input type="number" name="timeout" class="form-control" value="30" min="5">
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">إلغاء</button>
          <button type="submit" class="btn btn-primary"><i class="bi bi-plus-lg"></i> إضافة</button>
        </div>
      </form>
    </div>
  </div>
</div>
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

# ─────────────────────────────────────────
#  Proxies
# ─────────────────────────────────────────

PROXIES_HTML = BASE + """
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-1">
  <div class="page-title"><i class="bi bi-hdd-network"></i> البروكسيات</div>
  <div class="d-flex gap-2">
    <button class="btn btn-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addProxyModal">
      <i class="bi bi-plus-lg"></i> إضافة
    </button>
    <form method="POST" action="/proxies/clear" onsubmit="return confirm('حذف كل البروكسيات؟')">
      <button type="submit" class="btn btn-danger btn-sm"><i class="bi bi-trash"></i> حذف الكل</button>
    </form>
  </div>
</div>
<div class="page-sub">{{ proxies|length }} بروكسي — {{ active_count }} نشط</div>

<div class="card">
  <div class="card-body p-0">
    <table class="table mb-0">
      <thead>
        <tr><th>#</th><th>البروكسي</th><th>البروتوكول</th><th>الحالة</th><th>أخطاء</th><th></th></tr>
      </thead>
      <tbody>
        {% for p in proxies %}
        <tr>
          <td style="color:#8b949e">{{ loop.index }}</td>
          <td><code>{{ p.proxy_string }}</code></td>
          <td><span class="badge-active">{{ p.protocol }}</span></td>
          <td>
            {% if p.is_active and p.fail_count < 5 %}
              <span class="badge-active">✅ نشط</span>
            {% else %}
              <span class="badge-inactive">❌ معطّل</span>
            {% endif %}
          </td>
          <td>{{ p.fail_count }}</td>
          <td>
            <form method="POST" action="/proxies/delete">
              <input type="hidden" name="proxy_id" value="{{ p.id }}">
              <button type="submit" class="btn btn-sm btn-danger"><i class="bi bi-trash"></i></button>
            </form>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="6" class="text-center" style="color:#8b949e;padding:30px">لا توجد بروكسيات بعد</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<!-- Add Proxy Modal -->
<div class="modal fade" id="addProxyModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title"><i class="bi bi-hdd-network"></i> إضافة بروكسيات</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="p-3">
        <ul class="nav nav-pills mb-3" id="proxyTabs">
          <li class="nav-item">
            <button class="nav-link active" data-bs-toggle="pill" data-bs-target="#singleTab">بروكسي واحد</button>
          </li>
          <li class="nav-item">
            <button class="nav-link" data-bs-toggle="pill" data-bs-target="#bulkTab">إضافة متعددة</button>
          </li>
        </ul>
        <div class="tab-content">
          <div class="tab-pane fade show active" id="singleTab">
            <form method="POST" action="/proxies/add">
              <div class="mb-3">
                <label class="form-label">البروكسي</label>
                <input type="text" name="proxy" class="form-control" placeholder="host:port أو http://user:pass@host:port" required>
              </div>
              <button type="submit" class="btn btn-primary w-100">إضافة</button>
            </form>
          </div>
          <div class="tab-pane fade" id="bulkTab">
            <form method="POST" action="/proxies/bulk">
              <div class="mb-3">
                <label class="form-label">البروكسيات (سطر لكل بروكسي)</label>
                <textarea name="proxies" class="form-control" rows="8"
                  placeholder="host:port&#10;http://user:pass@host:port&#10;socks5://host:port" required></textarea>
              </div>
              <button type="submit" class="btn btn-primary w-100">إضافة الكل</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
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
<div class="page-title"><i class="bi bi-journal-text"></i> سجل الفحوصات</div>
<div class="page-sub">آخر 100 عملية فحص</div>
<div class="card">
  <div class="card-body p-0">
    <table class="table mb-0">
      <thead>
        <tr><th>الوقت</th><th>المستخدم</th><th>الكارت</th><th>البوابة</th><th>النتيجة</th></tr>
      </thead>
      <tbody>
        {% for l in logs %}
        <tr>
          <td><small>{{ l.created_at[:16] }}</small></td>
          <td><code>{{ l.user_id }}</code></td>
          <td>****{{ l.card_last4 }}</td>
          <td>{{ l.gateway_name }}</td>
          <td>
            {% if 'APPROVED' in l.result_status %}
              <span class="badge-active">✅ {{ l.result_status }}</span>
            {% else %}
              <span class="badge-inactive">❌ {{ l.result_status }}</span>
            {% endif %}
          </td>
        </tr>
        {% else %}
        <tr><td colspan="5" class="text-center" style="color:#8b949e;padding:30px">لا توجد سجلات</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
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
