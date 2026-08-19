from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from .config import config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# Login configuration
login_manager.login_view = 'auth.login'
login_manager.login_message = 'يرجى تسجيل الدخول للوصول لهذه الصفحة'
login_manager.login_message_category = 'warning'


def create_app(config_name=None):
    """Application factory"""
    import os
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # GYM-44 — Jinja filters that render UTC datetimes as Asia/Riyadh +
    # 12-hour with ص/م. Templates use {{ x | local_dt }} etc. instead of
    # {{ x.strftime('...') }} so existing rows look correct without a
    # data migration.
    from app.utils.helpers import local_dt, local_time, local_date
    app.jinja_env.filters['local_dt'] = local_dt
    app.jinja_env.filters['local_time'] = local_time
    app.jinja_env.filters['local_date'] = local_date

    # Create upload folders if they don't exist
    upload_folders = ['logos', 'members', 'receipts', 'subscriptions', 'complaints']
    for folder in upload_folders:
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(folder_path, exist_ok=True)

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.admin import admin_bp
    from .routes.members import members_bp
    from .routes.subscriptions import subscriptions_bp
    from .routes.attendance import attendance_bp
    from .routes.finance import finance_bp
    from .routes.reports import reports_bp
    from .routes.api import api_bp
    from .routes.fingerprint import fingerprint_bp
    from .routes.bridge import bridge_bp
    from .routes.health import health_bp
    from .routes.complaints import complaints_bp
    from .routes.classes import classes_bp
    from .routes.closing import closing_bp
    from .routes.daily_closing import daily_closing_bp
    from .routes.gift_cards import gift_cards_bp
    from .routes.offers import offers_bp
    from .routes.employees import employees_bp
    from .routes.bookings import bookings_bp
    from .routes.invoices import invoices_bp
    from .routes.day_pass import day_pass_bp  # GYM-23
    from .routes.approvals import approvals_bp  # GYM-55 / 58

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(members_bp, url_prefix='/members')
    app.register_blueprint(subscriptions_bp, url_prefix='/subscriptions')
    app.register_blueprint(attendance_bp, url_prefix='/attendance')
    app.register_blueprint(finance_bp, url_prefix='/finance')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(fingerprint_bp)  # url_prefix='/fp' set in blueprint
    app.register_blueprint(bridge_bp, url_prefix='/bridge')
    app.register_blueprint(health_bp)
    app.register_blueprint(complaints_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(closing_bp, url_prefix='/closing')
    app.register_blueprint(daily_closing_bp)
    app.register_blueprint(gift_cards_bp)
    app.register_blueprint(offers_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(bookings_bp, url_prefix='/bookings')
    app.register_blueprint(invoices_bp, url_prefix='/invoices')
    app.register_blueprint(day_pass_bp)  # /day-pass/* — GYM-23
    app.register_blueprint(approvals_bp)  # /admin/freeze-requests + /admin/pending-edits
    csrf.exempt(api_bp)  # API uses API key auth, not CSRF
    csrf.exempt(fingerprint_bp)  # /fp/* is open by design (single-tenant desktop client)

    # Idempotently ensure newly-added tables exist on production.
    # SQLAlchemy create_all() only creates missing tables — existing ones
    # are left untouched. Wrap in app_context + try/except so a transient
    # DB error during boot doesn't crash the whole app.
    with app.app_context():
        try:
            db.create_all()
        except Exception:
            pass
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                # subscriptions.proof_image (proof-of-payment image)
                cols = [r[1] for r in conn.exec_driver_sql(
                    "PRAGMA table_info(subscriptions)"
                ).fetchall()]
                if 'proof_image' not in cols:
                    conn.exec_driver_sql(
                        "ALTER TABLE subscriptions ADD COLUMN proof_image VARCHAR(255)"
                    )
                # invoices.branch_id / branch_name / branch_phone / branch_address  (GYM-15)
                inv_cols = [r[1] for r in conn.exec_driver_sql(
                    "PRAGMA table_info(invoices)"
                ).fetchall()]
                for col, ddl in (
                    ('branch_id',      'INTEGER'),
                    ('branch_name',    'VARCHAR(120)'),
                    ('branch_phone',   'VARCHAR(40)'),
                    ('branch_address', 'VARCHAR(200)'),
                ):
                    if col not in inv_cols:
                        conn.exec_driver_sql(f"ALTER TABLE invoices ADD COLUMN {col} {ddl}")
                # day_passes.discount (GYM-33) + subscriptions/expenses.is_deleted (GYM-32)
                try:
                    dp_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(day_passes)"
                    ).fetchall()]
                    if dp_cols and 'discount' not in dp_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE day_passes ADD COLUMN discount NUMERIC(10,2) DEFAULT 0 NOT NULL"
                        )
                except Exception:
                    pass
                try:
                    sub_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(subscriptions)"
                    ).fetchall()]
                    if sub_cols and 'is_deleted' not in sub_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE subscriptions ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL"
                        )
                    exp_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(expenses)"
                    ).fetchall()]
                    if exp_cols and 'is_deleted' not in exp_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE expenses ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL"
                        )
                    inc_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(income)"
                    ).fetchall()]
                    if inc_cols and 'is_deleted' not in inc_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE income ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL"
                        )
                    # GYM-38 — subscription_payments.is_deleted
                    sp_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(subscription_payments)"
                    ).fetchall()]
                    if sp_cols and 'is_deleted' not in sp_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE subscription_payments ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL"
                        )
                    # GYM-43 — users.is_deleted (soft-delete for staff).
                    u_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(users)"
                    ).fetchall()]
                    if u_cols and 'is_deleted' not in u_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE users ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL"
                        )
                    # GYM-51 — complaints.is_archived + archived_at/by
                    c_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(complaints)"
                    ).fetchall()]
                    if c_cols:
                        if 'is_archived' not in c_cols:
                            conn.exec_driver_sql(
                                "ALTER TABLE complaints ADD COLUMN is_archived BOOLEAN DEFAULT 0 NOT NULL"
                            )
                        if 'archived_at' not in c_cols:
                            conn.exec_driver_sql(
                                "ALTER TABLE complaints ADD COLUMN archived_at DATETIME"
                            )
                        if 'archived_by' not in c_cols:
                            conn.exec_driver_sql(
                                "ALTER TABLE complaints ADD COLUMN archived_by INTEGER"
                            )
                    # GYM-57 — iqama tracking columns on users.
                    u_cols2 = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(users)"
                    ).fetchall()]
                    for col, ddl in (
                        ('iqama_number',     'ALTER TABLE users ADD COLUMN iqama_number VARCHAR(30)'),
                        ('iqama_start_date', 'ALTER TABLE users ADD COLUMN iqama_start_date DATE'),
                        ('iqama_end_date',   'ALTER TABLE users ADD COLUMN iqama_end_date DATE'),
                    ):
                        if u_cols2 and col not in u_cols2:
                            conn.exec_driver_sql(ddl)
                    # GYM-60 — per-branch member display_number.
                    m_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(members)"
                    ).fetchall()]
                    if m_cols and 'display_number' not in m_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE members ADD COLUMN display_number INTEGER"
                        )
                        # Backfill in-place, per branch, ordered by created_at.
                        # (idempotent — only runs when the column doesn't exist)
                        rows = conn.exec_driver_sql(
                            "SELECT id, branch_id FROM members "
                            "ORDER BY branch_id, created_at, id"
                        ).fetchall()
                        counters = {}
                        for mid, bid in rows:
                            counters[bid] = counters.get(bid, 0) + 1
                            conn.exec_driver_sql(
                                "UPDATE members SET display_number = ? WHERE id = ?",
                                (counters[bid], mid),
                            )
                    # GYM-55 / 58 / 61 — approval + audit tables.
                    for ddl in (
                        """CREATE TABLE IF NOT EXISTS subscription_freeze_requests (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             subscription_id INTEGER NOT NULL,
                             freeze_start DATE NOT NULL,
                             freeze_days INTEGER NOT NULL,
                             reason TEXT,
                             status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                             rejection_reason TEXT,
                             requested_by INTEGER,
                             requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                             reviewed_by INTEGER,
                             reviewed_at DATETIME,
                             FOREIGN KEY(subscription_id) REFERENCES subscriptions(id),
                             FOREIGN KEY(requested_by) REFERENCES users(id),
                             FOREIGN KEY(reviewed_by) REFERENCES users(id)
                           )""",
                        """CREATE TABLE IF NOT EXISTS pending_edits (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             entity_type VARCHAR(40) NOT NULL,
                             entity_id INTEGER NOT NULL,
                             action VARCHAR(20) NOT NULL,
                             payload_json TEXT,
                             summary VARCHAR(280),
                             status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                             rejection_reason TEXT,
                             brand_id INTEGER,
                             requested_by INTEGER,
                             requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                             reviewed_by INTEGER,
                             reviewed_at DATETIME,
                             FOREIGN KEY(brand_id) REFERENCES brands(id),
                             FOREIGN KEY(requested_by) REFERENCES users(id),
                             FOREIGN KEY(reviewed_by) REFERENCES users(id)
                           )""",
                        """CREATE TABLE IF NOT EXISTS edit_audit_logs (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             entity_type VARCHAR(40) NOT NULL,
                             entity_id INTEGER NOT NULL,
                             field_name VARCHAR(40) NOT NULL,
                             old_value VARCHAR(200),
                             new_value VARCHAR(200),
                             brand_id INTEGER,
                             changed_by INTEGER,
                             changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                             note VARCHAR(200),
                             FOREIGN KEY(brand_id) REFERENCES brands(id),
                             FOREIGN KEY(changed_by) REFERENCES users(id)
                           )""",
                    ):
                        try:
                            conn.exec_driver_sql(ddl)
                        except Exception:
                            pass
                    # GYM-62 — class course schedule, sessions, enrollments.
                    gc_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(gym_classes)"
                    ).fetchall()]
                    if gc_cols:
                        for col, ddl in (
                            ('start_date',              'ALTER TABLE gym_classes ADD COLUMN start_date DATE'),
                            ('end_date',                'ALTER TABLE gym_classes ADD COLUMN end_date DATE'),
                            ('weekday_mask',            'ALTER TABLE gym_classes ADD COLUMN weekday_mask INTEGER DEFAULT 0'),
                            ('price',                   'ALTER TABLE gym_classes ADD COLUMN price NUMERIC(10,2) DEFAULT 0'),
                            ('trainer_fee_per_session', 'ALTER TABLE gym_classes ADD COLUMN trainer_fee_per_session NUMERIC(10,2) DEFAULT 0'),
                            ('status',                  "ALTER TABLE gym_classes ADD COLUMN status VARCHAR(20) DEFAULT 'active'"),
                        ):
                            if col not in gc_cols:
                                conn.exec_driver_sql(ddl)
                        # Backfill legacy rows so the new UI has something to render.
                        conn.exec_driver_sql(
                            "UPDATE gym_classes SET weekday_mask = (1 << day_of_week) "
                            "WHERE day_of_week IS NOT NULL AND (weekday_mask IS NULL OR weekday_mask = 0)"
                        )
                        conn.exec_driver_sql(
                            "UPDATE gym_classes SET start_date = date(created_at) "
                            "WHERE start_date IS NULL AND created_at IS NOT NULL"
                        )
                        conn.exec_driver_sql(
                            "UPDATE gym_classes SET end_date = date(created_at, '+365 days') "
                            "WHERE end_date IS NULL AND created_at IS NOT NULL"
                        )
                        conn.exec_driver_sql(
                            "UPDATE gym_classes SET status = 'active' WHERE status IS NULL"
                        )
                    cb_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(class_bookings)"
                    ).fetchall()]
                    if cb_cols:
                        for col, ddl in (
                            ('session_id',    'ALTER TABLE class_bookings ADD COLUMN session_id INTEGER'),
                            ('enrollment_id', 'ALTER TABLE class_bookings ADD COLUMN enrollment_id INTEGER'),
                        ):
                            if col not in cb_cols:
                                conn.exec_driver_sql(ddl)
                    for ddl in (
                        """CREATE TABLE IF NOT EXISTS class_sessions (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             class_id INTEGER NOT NULL,
                             session_date DATE NOT NULL,
                             start_time TIME NOT NULL,
                             end_time TIME NOT NULL,
                             status VARCHAR(20) DEFAULT 'scheduled' NOT NULL,
                             created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                             FOREIGN KEY(class_id) REFERENCES gym_classes(id)
                           )""",
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_class_sessions_class_date ON class_sessions(class_id, session_date)",
                        """CREATE TABLE IF NOT EXISTS class_enrollments (
                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                             class_id INTEGER NOT NULL,
                             member_id INTEGER NOT NULL,
                             subscription_id INTEGER,
                             invoice_id INTEGER,
                             start_date DATE NOT NULL,
                             end_date DATE NOT NULL,
                             sessions_total INTEGER DEFAULT 0,
                             total_amount NUMERIC(10,2) DEFAULT 0,
                             paid_amount NUMERIC(10,2) DEFAULT 0,
                             refund_amount NUMERIC(10,2) DEFAULT 0,
                             status VARCHAR(20) DEFAULT 'active' NOT NULL,
                             notes TEXT,
                             created_by INTEGER,
                             created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                             cancelled_at DATETIME,
                             FOREIGN KEY(class_id) REFERENCES gym_classes(id),
                             FOREIGN KEY(member_id) REFERENCES members(id),
                             FOREIGN KEY(subscription_id) REFERENCES subscriptions(id),
                             FOREIGN KEY(invoice_id) REFERENCES invoices(id),
                             FOREIGN KEY(created_by) REFERENCES users(id)
                           )""",
                    ):
                        try:
                            conn.exec_driver_sql(ddl)
                        except Exception:
                            pass
                    # GYM-65 — split-payment link on subscription_payments.
                    sp_cols = [r[1] for r in conn.exec_driver_sql(
                        "PRAGMA table_info(subscription_payments)"
                    ).fetchall()]
                    if sp_cols and 'invoice_id' not in sp_cols:
                        conn.exec_driver_sql(
                            "ALTER TABLE subscription_payments ADD COLUMN invoice_id INTEGER"
                        )
                    # GYM-68 — backfill an initial fp-access log row for every
                    # member with a fingerprint_id who has no log entries yet.
                    # Sharif's desktop client is diff-based: it only writes to
                    # backup.mdb when it sees a changed `last_changed_at` per
                    # member. Members with no log row have last_changed_at=null,
                    # which the diff logic never sees as "changed", so they
                    # were silently skipped and never appeared at the gate.
                    # Idempotent — the NOT EXISTS clause skips members that
                    # already have any log row.
                    try:
                        conn.exec_driver_sql("""
                            INSERT INTO fingerprint_access_logs
                                (brand_id, branch_id, member_id, member_name,
                                 fingerprint_id, member_import_id, action,
                                 source, notes, created_at)
                            SELECT m.brand_id, m.branch_id, m.id, m.name,
                                   m.fingerprint_id, m.member_import_id,
                                   'allow', 'system',
                                   'backfilled initial log row (GYM-68)',
                                   CURRENT_TIMESTAMP
                            FROM members m
                            WHERE m.fingerprint_id IS NOT NULL
                              AND NOT EXISTS (
                                  SELECT 1 FROM fingerprint_access_logs fal
                                  WHERE fal.member_id = m.id
                              )
                        """)
                    except Exception:
                        pass
                    # GYM-67 — NO backfill by design. On prod, brand 10's
                    # service_type "درة الدخل الرياضي" was mistakenly flagged
                    # requires_class_booking=1, cascading to 12 regular gym
                    # plans and blocking 370 members every non-class day.
                    # Backfilling plan.requires_class_booking from the
                    # service_type flag would preserve that damage. Instead,
                    # we simply make plan.requires_class_booking authoritative
                    # in _compute_access (see app/routes/fingerprint.py) and
                    # trust the flag the operator actually set on each plan.
                    # Real class plans (plan.requires_class_booking=1) keep
                    # enforcing the class-window rule.
                except Exception:
                    pass
                # complaint_attachments (GYM-21)
                try:
                    conn.exec_driver_sql(
                        "CREATE TABLE IF NOT EXISTS complaint_attachments ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "complaint_id INTEGER NOT NULL, "
                        "filename VARCHAR(255) NOT NULL, "
                        "original_name VARCHAR(255), "
                        "uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                        "FOREIGN KEY(complaint_id) REFERENCES complaints(id))"
                    )
                except Exception:
                    pass
                conn.commit()
        except Exception:
            pass

    # Register error handlers
    register_error_handlers(app)

    # Register CLI commands
    register_cli_commands(app)

    # Context processors
    @app.context_processor
    def inject_globals():
        try:
            from .models.user import Role
            return {
                'roles': Role.query.all() if Role.query.first() else []
            }
        except Exception:
            return {'roles': []}

    @app.context_processor
    def inject_owner_branch_picker():
        """Expose `owner_branches` (list) + `owner_branch_filter_id` (int|None)
        to every authenticated template so any owner-facing page can render
        the GYM-12 branch picker without each route remembering to pass it in.
        """
        try:
            from flask_login import current_user
            from .models.company import Branch
            from .utils.helpers import resolve_owner_branch_filter
            # Only brand-level owners see this picker. Employees, branch
            # roles, and admins are excluded (admins have their own brand
            # picker on each page; branch roles already scope themselves).
            if (current_user and current_user.is_authenticated
                    and current_user.is_brand_manager
                    and current_user.brand_id
                    and not current_user.branch_id):
                return {
                    'owner_branches': Branch.query.filter_by(
                        brand_id=current_user.brand_id, is_active=True
                    ).order_by(Branch.name).all(),
                    'owner_branch_filter_id': resolve_owner_branch_filter(),
                }
        except Exception:
            pass
        return {'owner_branches': None, 'owner_branch_filter_id': None}

    return app


def register_error_handlers(app):
    """Register error handlers"""
    from flask import render_template

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500


def register_cli_commands(app):
    """Register CLI commands"""
    import click

    @app.cli.command('create-admin')
    @click.option('--email', prompt='Email', help='Admin email')
    @click.option('--password', prompt='Password', hide_input=True, help='Admin password')
    @click.option('--name', prompt='Name', help='Admin name')
    def create_admin(email, password, name):
        """Create the first admin (Owner) user"""
        from .models.user import User, Role
        from .models.company import Company

        # Check if admin already exists
        owner_role = Role.query.filter_by(name_en='admin').first()
        if owner_role and User.query.filter_by(role_id=owner_role.id).first():
            click.echo('Admin already exists!')
            return

        # Create default company if not exists
        company = Company.query.first()
        if not company:
            company = Company(name='الشركة الرئيسية')
            db.session.add(company)
            db.session.commit()
            click.echo(f'Created company: {company.name}')

        # Create owner
        if not owner_role:
            click.echo('Please run db upgrade first to create roles')
            return

        user = User(
            name=name,
            email=email,
            role_id=owner_role.id,
            brand_id=None  # Owner has no brand restriction
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        click.echo(f'Created admin user: {email}')

    @app.cli.command('init-db')
    def init_db():
        """Initialize database with default data"""
        from .models.user import Role

        # Create roles if not exist
        # Format: (name_en, name_ar, description, permissions_dict)
        roles_data = [
            ('admin', 'أدمن', 'مدير النظام - صلاحية كاملة على جميع البراندات', {
                'is_owner': True, 'can_view_all_brands': True,
                'can_manage_members': True, 'can_manage_subscriptions': True,
                'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True, 'can_manage_attendance': True,
                'can_view_complaints': True, 'can_manage_complaints': True,
                'can_view_daily_closing': True, 'can_manage_daily_closing': True,
                'can_manage_classes': True, 'can_approve_expenses': True,
                'can_manage_offers': True, 'can_manage_gift_cards': True,
            }),
            ('owner', 'المالك', 'مالك البراند - تحكم كامل في براند واحد', {
                'can_manage_members': True, 'can_manage_subscriptions': True,
                'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True, 'can_manage_attendance': True,
                'can_view_complaints': True, 'can_manage_complaints': True,
                'can_view_daily_closing': True, 'can_manage_daily_closing': True,
                'can_manage_classes': True, 'can_approve_expenses': True,
                'can_manage_offers': True, 'can_manage_gift_cards': True,
            }),
            ('branch_manager', 'مدير الفرع', 'مدير فرع - تحكم كامل في فرع واحد', {
                'can_manage_members': True, 'can_manage_subscriptions': True,
                'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True, 'can_manage_attendance': True,
                'can_view_complaints': True, 'can_manage_complaints': True,
                'can_view_daily_closing': True, 'can_manage_daily_closing': True,
                'can_manage_classes': True, 'can_approve_expenses': True,
                'can_manage_offers': True, 'can_manage_gift_cards': True,
            }),
            ('branch_receptionist', 'استقبال فرع', 'موظف استقبال على مستوى الفرع', {
                'can_manage_members': True, 'can_manage_subscriptions': True,
                'can_manage_attendance': True, 'can_view_complaints': True,
                'can_manage_classes': True,
            }),
            ('brand_finance', 'مالية براند', 'مالية على مستوى البراند بكل فروعه', {
                'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True,
                'can_view_daily_closing': True, 'can_manage_daily_closing': True,
            }),
            ('branch_finance', 'مالية فرع', 'مالية على مستوى فرع واحد', {
                'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True,
                'can_view_daily_closing': True, 'can_manage_daily_closing': True,
            }),
            ('finance_admin', 'مالية عامة', 'الاطلاع على مالية جميع البراندات - مخفي', {
                'can_view_all_brands': True, 'can_view_finance': True,
                'can_view_reports': True, 'can_view_daily_closing': True,
            }),
            ('employee', 'موظف', 'موظف على مستوى الفرع', {
                'can_manage_attendance': True,
            }),
        ]

        for name_en, name_ar, description, permissions in roles_data:
            if not Role.query.filter_by(name_en=name_en).first():
                role = Role(name=name_ar, name_en=name_en, description=description, **permissions)
                db.session.add(role)
                click.echo(f'Created role: {name_ar}')

        db.session.commit()
        click.echo('Database initialized successfully!')

    @app.cli.command('seed-data')
    @click.option('--brand-id', type=int, help='Brand ID to seed data for')
    def seed_data(brand_id):
        """Seed default service types and complaint categories"""
        from .models.service import ServiceType
        from .models.complaint import ComplaintCategory
        from .models.company import Brand

        # Seed complaint categories (global)
        click.echo('Seeding complaint categories...')
        ComplaintCategory.seed_defaults()
        click.echo('Done!')

        # Seed service types for a brand
        if brand_id:
            brand = Brand.query.get(brand_id)
            if not brand:
                click.echo(f'Brand {brand_id} not found!')
                return

            click.echo(f'Seeding service types for {brand.name}...')
            default_services = [
                {'name': 'جيم', 'name_en': 'gym', 'category': 'gym'},
                {'name': 'سباحة تعليم', 'name_en': 'swimming_teaching', 'category': 'swimming', 'requires_class_booking': True},
                {'name': 'سباحة ترفيه', 'name_en': 'swimming_recreation', 'category': 'swimming'},
                {'name': 'كاراتيه', 'name_en': 'karate', 'category': 'karate', 'requires_class_booking': True},
                {'name': 'صالون', 'name_en': 'salon', 'category': 'salon', 'requires_class_booking': True},
            ]

            for service_data in default_services:
                existing = ServiceType.query.filter_by(
                    brand_id=brand_id,
                    name_en=service_data.get('name_en')
                ).first()
                if not existing:
                    service = ServiceType(
                        brand_id=brand_id,
                        name=service_data['name'],
                        name_en=service_data.get('name_en'),
                        category=service_data['category'],
                        requires_class_booking=service_data.get('requires_class_booking', False)
                    )
                    db.session.add(service)
                    click.echo(f'  Created: {service_data["name"]}')

            db.session.commit()
            click.echo('Done!')

    @app.cli.command('close-class-sessions')
    def close_class_sessions():
        """GYM-62 — flip past scheduled ClassSessions to 'held', and any
        remaining 'booked' ClassBookings on those dates to 'no_show'. Run
        daily via cron (or manually). Idempotent."""
        from datetime import date
        from .models.classes import ClassSession, ClassBooking
        today = date.today()
        stale = ClassSession.query.filter(
            ClassSession.session_date < today,
            ClassSession.status == 'scheduled',
        ).all()
        n_sessions = 0
        n_no_shows = 0
        for s in stale:
            open_bookings = ClassBooking.query.filter_by(
                session_id=s.id, status='booked'
            ).all()
            for b in open_bookings:
                b.status = 'no_show'
                n_no_shows += 1
            s.status = 'held'
            n_sessions += 1
        db.session.commit()
        click.echo(f'{n_sessions} sessions closed, {n_no_shows} bookings marked no-show')

    @app.cli.command('auto-unfreeze-expired')
    def auto_unfreeze_expired():
        """GYM-71 — flip subscriptions from 'frozen' back to 'active' when
        the latest SubscriptionFreeze.freeze_end < today (Asia/Riyadh).

        Runs the same code path as the manual /unfreeze route but for
        every eligible subscription in one pass. Idempotent — subsequent
        runs no-op. Meant to be scheduled daily on PythonAnywhere:

            0 3 * * *  cd ~/sytem-gym/gym_system && FLASK_APP=run.py flask auto-unfreeze-expired

        (3 AM KSA = 00:00 UTC — first minute of the new KSA day.)
        """
        import json as _json
        from .routes.fingerprint import ksa_today
        from .models.subscription import Subscription, SubscriptionFreeze
        from .models.fingerprint import DeviceCommand

        today = ksa_today()  # KSA date, not UTC. Matches _compute_access.
        frozen_subs = Subscription.query.filter_by(status='frozen').all()

        n_unfrozen = 0
        n_skipped = 0
        for sub in frozen_subs:
            latest = SubscriptionFreeze.query.filter_by(
                subscription_id=sub.id
            ).order_by(SubscriptionFreeze.freeze_end.desc()).first()
            if not latest or latest.freeze_end is None:
                n_skipped += 1
                continue
            if latest.freeze_end >= today:
                # Still inside the freeze window
                n_skipped += 1
                continue

            sub.status = 'active'
            n_unfrozen += 1

            # Dispatch unblock — same shape as /subscriptions/<id>/unfreeze
            member = sub.member
            if (member and member.fingerprint_id and member.branch
                    and getattr(member.branch, 'uses_fingerprint', False)):
                db.session.add(DeviceCommand(
                    brand_id=sub.brand_id,
                    command_type='unblock_member',
                    target_emp_id=member.fingerprint_id,
                    member_id=member.id,
                    command_data=_json.dumps({'end_date': sub.end_date.isoformat()}),
                    status='pending',
                ))

        db.session.commit()
        click.echo(
            f'auto-unfreeze: {n_unfrozen} unfrozen, {n_skipped} still frozen '
            f'(KSA today = {today.isoformat()})'
        )
