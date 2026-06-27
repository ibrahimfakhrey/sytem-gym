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
