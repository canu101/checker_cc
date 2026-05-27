import sqlite3
import json
from datetime import datetime, timedelta
from threading import Lock

DB_PATH = "bot_system.db"
db_lock = Lock()


class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        self._migrate()

    def _cur(self):
        return self.conn.cursor()

    def _create_tables(self):
        cur = self._cur()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'ar',
                subscription_expiry TIMESTAMP,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_blocked INTEGER DEFAULT 0,
                total_checks INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS redeem_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                label TEXT DEFAULT '',
                duration_days INTEGER NOT NULL DEFAULT 0,
                duration_hours INTEGER DEFAULT NULL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS code_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER,
                user_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy_string TEXT UNIQUE NOT NULL,
                protocol TEXT DEFAULT 'http',
                is_active INTEGER DEFAULT 1,
                fail_count INTEGER DEFAULT 0,
                last_used TIMESTAMP,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS gateways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                button_name TEXT NOT NULL,
                api_endpoint TEXT NOT NULL,
                method TEXT DEFAULT 'POST',
                headers_json TEXT DEFAULT '{}',
                body_template TEXT DEFAULT '',
                success_pattern TEXT DEFAULT '',
                decline_pattern TEXT DEFAULT '',
                error_pattern TEXT DEFAULT '',
                timeout_seconds INTEGER DEFAULT 30,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS check_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                gateway_id INTEGER,
                gateway_name TEXT,
                card_last4 TEXT,
                result_status TEXT,
                result_category TEXT,
                raw_response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_checks INTEGER DEFAULT 0,
                approved INTEGER DEFAULT 0,
                declined INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.conn.commit()
        defaults = [
            ('thread_count', '5'),
            ('request_timeout', '30'),
            ('auto_clean_logs', '1'),
            ('bot_token', '')
        ]
        for k, v in defaults:
            cur.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (k, v))
        self.conn.commit()

    def _migrate(self):
        cur = self._cur()
        migrations = [
            "ALTER TABLE redeem_codes ADD COLUMN label TEXT DEFAULT ''",
            "ALTER TABLE redeem_codes ADD COLUMN duration_hours INTEGER DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN total_checks INTEGER DEFAULT 0",
        ]
        for sql in migrations:
            try:
                cur.execute(sql)
            except Exception:
                pass
        self.conn.commit()

    # ── Users ────────────────────────────────────────────────────────────────

    def get_or_create_user(self, user_id, username=None, first_name=None):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                    (user_id, username, first_name)
                )
                self.conn.commit()

    def get_user(self, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def set_user_language(self, user_id, lang):
        with db_lock:
            cur = self._cur()
            cur.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
            self.conn.commit()

    def get_user_language(self, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
            res = cur.fetchone()
            return res[0] if res and res[0] else 'ar'

    def block_user(self, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
            self.conn.commit()

    def unblock_user(self, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
            self.conn.commit()

    def extend_subscription(self, user_id, days):
        return self.extend_subscription_hours(user_id, days * 24)

    def extend_subscription_hours(self, user_id, hours):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT subscription_expiry FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            current = datetime.fromisoformat(row[0]) if row and row[0] else datetime.now()
            if current < datetime.now():
                current = datetime.now()
            new_expiry = current + timedelta(hours=float(hours))
            cur.execute(
                "UPDATE users SET subscription_expiry = ? WHERE user_id = ?",
                (new_expiry.isoformat(), user_id)
            )
            self.conn.commit()
            return new_expiry

    def is_subscribed(self, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT subscription_expiry, is_blocked FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if not row or row[1] == 1:
                return False
            expiry = row[0]
            if expiry:
                return datetime.fromisoformat(expiry) > datetime.now()
            return False

    def get_all_users(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM users ORDER BY joined_date DESC")
            return [dict(row) for row in cur.fetchall()]

    def increment_user_checks(self, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("UPDATE users SET total_checks = total_checks + 1 WHERE user_id = ?", (user_id,))
            self.conn.commit()

    # ── Codes ────────────────────────────────────────────────────────────────

    def create_code(self, code, label, duration_hours, max_uses, created_by):
        with db_lock:
            cur = self._cur()
            cur.execute(
                "INSERT INTO redeem_codes (code, label, duration_hours, duration_days, max_uses, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                (code, label, int(duration_hours), 0, max_uses, created_by)
            )
            self.conn.commit()

    def get_code(self, code_str):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM redeem_codes WHERE code = ? AND is_active = 1", (code_str,))
            row = cur.fetchone()
            return dict(row) if row else None

    def use_code(self, code_id, user_id):
        with db_lock:
            cur = self._cur()
            cur.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE id = ?", (code_id,))
            cur.execute("INSERT INTO code_uses (code_id, user_id) VALUES (?, ?)", (code_id, user_id))
            self.conn.commit()

    def get_all_codes(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM redeem_codes ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def delete_code(self, code_id):
        with db_lock:
            cur = self._cur()
            cur.execute("DELETE FROM redeem_codes WHERE id = ?", (code_id,))
            self.conn.commit()

    # ── Proxies ──────────────────────────────────────────────────────────────

    def add_proxy(self, proxy_string, protocol='http'):
        with db_lock:
            cur = self._cur()
            try:
                if '://' in proxy_string:
                    protocol = proxy_string.split('://')[0]
                    proxy_string = proxy_string.split('://')[1]
                cur.execute(
                    "INSERT INTO proxies (proxy_string, protocol) VALUES (?, ?)",
                    (proxy_string.strip(), protocol)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def add_proxies_bulk(self, proxies_list):
        with db_lock:
            cur = self._cur()
            added = 0
            for p in proxies_list:
                p = p.strip()
                if not p or p.startswith('#'):
                    continue
                try:
                    protocol = 'http'
                    if '://' in p:
                        protocol = p.split('://')[0]
                        p = p.split('://')[1]
                    cur.execute(
                        "INSERT OR IGNORE INTO proxies (proxy_string, protocol) VALUES (?, ?)",
                        (p, protocol)
                    )
                    added += cur.rowcount
                except Exception:
                    pass
            self.conn.commit()
            return added

    def get_active_proxies(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM proxies WHERE is_active = 1 AND fail_count < 5 ORDER BY RANDOM()")
            return [dict(row) for row in cur.fetchall()]

    def get_all_proxies(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM proxies ORDER BY added_date DESC")
            return [dict(row) for row in cur.fetchall()]

    def increment_proxy_fail(self, proxy_id):
        with db_lock:
            cur = self._cur()
            cur.execute("UPDATE proxies SET fail_count = fail_count + 1 WHERE id = ?", (proxy_id,))
            self.conn.commit()

    def delete_proxy(self, proxy_id):
        with db_lock:
            cur = self._cur()
            cur.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
            self.conn.commit()

    def clear_all_proxies(self):
        with db_lock:
            cur = self._cur()
            cur.execute("DELETE FROM proxies")
            self.conn.commit()

    # ── Gateways ─────────────────────────────────────────────────────────────

    def add_gateway(self, data):
        with db_lock:
            cur = self._cur()
            cur.execute("""
                INSERT INTO gateways
                (display_name, button_name, api_endpoint, method, headers_json, body_template,
                 success_pattern, decline_pattern, error_pattern, timeout_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['display_name'], data['button_name'], data['endpoint'], data['method'],
                json.dumps(data['headers']) if isinstance(data['headers'], dict) else data['headers'],
                data['body'], data['success'], data['decline'], data['error'], data['timeout']
            ))
            self.conn.commit()

    def update_gateway(self, gid, data):
        with db_lock:
            cur = self._cur()
            cur.execute("""
                UPDATE gateways SET display_name=?, button_name=?, api_endpoint=?, method=?,
                headers_json=?, body_template=?, success_pattern=?, decline_pattern=?, error_pattern=?, timeout_seconds=?
                WHERE id=?
            """, (
                data['display_name'], data['button_name'], data['endpoint'], data['method'],
                json.dumps(data['headers']) if isinstance(data['headers'], dict) else data['headers'],
                data['body'], data['success'], data['decline'], data['error'], data['timeout'], gid
            ))
            self.conn.commit()

    def get_active_gateways(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM gateways WHERE is_active = 1 ORDER BY display_name")
            return [dict(row) for row in cur.fetchall()]

    def get_all_gateways(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM gateways ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def get_gateway_by_id(self, gid):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM gateways WHERE id = ?", (gid,))
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_gateway(self, gid):
        with db_lock:
            cur = self._cur()
            cur.execute("DELETE FROM gateways WHERE id = ?", (gid,))
            self.conn.commit()

    # ── Logs & Stats ─────────────────────────────────────────────────────────

    def log_check(self, user_id, gateway_id, gateway_name, card_last4, status, category, raw):
        with db_lock:
            cur = self._cur()
            cur.execute("""
                INSERT INTO check_logs (user_id, gateway_id, gateway_name, card_last4, result_status, result_category, raw_response)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, gateway_id, gateway_name, card_last4, status, category, raw))
            today = datetime.now().strftime("%Y-%m-%d")
            cur.execute("""
                INSERT INTO daily_stats (date, total_checks) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET total_checks = total_checks + 1
            """, (today,))
            if category in ('approved_charged', 'approved_auth_only', 'approved_insufficient', 'auth_required'):
                cur.execute("UPDATE daily_stats SET approved = approved + 1 WHERE date = ?", (today,))
            elif category == 'declined':
                cur.execute("UPDATE daily_stats SET declined = declined + 1 WHERE date = ?", (today,))
            elif category == 'error':
                cur.execute("UPDATE daily_stats SET errors = errors + 1 WHERE date = ?", (today,))
            self.conn.commit()

    def get_recent_logs(self, limit=100):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM check_logs ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]

    def get_user_logs(self, user_id, limit=50):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM check_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
            return [dict(row) for row in cur.fetchall()]

    def get_stats(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM daily_stats ORDER BY date DESC LIMIT 30")
            return [dict(row) for row in cur.fetchall()]

    def clean_old_logs(self):
        cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
        with db_lock:
            cur = self._cur()
            cur.execute("DELETE FROM check_logs WHERE created_at < ?", (cutoff,))
            deleted = cur.rowcount
            self.conn.commit()
            return deleted

    # ── Settings ─────────────────────────────────────────────────────────────

    def get_setting(self, key, default=None):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_setting(self, key, value):
        with db_lock:
            cur = self._cur()
            cur.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
            self.conn.commit()

    def get_all_settings(self):
        with db_lock:
            cur = self._cur()
            cur.execute("SELECT * FROM bot_settings")
            return [dict(row) for row in cur.fetchall()]

    # ── Counts ───────────────────────────────────────────────────────────────

    def count_users(self):
        with db_lock:
            return self._cur().execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def count_active_users(self):
        with db_lock:
            return self._cur().execute(
                "SELECT COUNT(*) FROM users WHERE subscription_expiry > datetime('now') AND is_blocked=0"
            ).fetchone()[0]

    def count_active_proxies(self):
        with db_lock:
            return self._cur().execute("SELECT COUNT(*) FROM proxies WHERE is_active=1").fetchone()[0]

    def count_active_gateways(self):
        with db_lock:
            return self._cur().execute("SELECT COUNT(*) FROM gateways WHERE is_active=1").fetchone()[0]

    def count_logs(self):
        with db_lock:
            return self._cur().execute("SELECT COUNT(*) FROM check_logs").fetchone()[0]
