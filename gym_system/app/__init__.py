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

    # Create upload folders if they don't exist
    upload_folders = ['logos', 'members', 'receipts']
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

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(members_bp, url_prefix='/members')
    app.register_blueprint(subscriptions_bp, url_prefix='/subscriptions')
    app.register_blueprint(attendance_bp, url_prefix='/attendance')
    app.register_blueprint(finance_bp, url_prefix='/finance')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(api_bp, url_prefix='/api')

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

        # Check if owner already exists
        owner_role = Role.query.filter_by(name_en='owner').first()
        if owner_role and User.query.filter_by(role_id=owner_role.id).first():
            click.echo('Owner already exists!')
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
            ('owner', 'المالك', 'صلاحية كاملة على جميع البراندات', {
                'is_owner': True, 'can_view_all_brands': True, 'can_manage_members': True,
                'can_manage_subscriptions': True, 'can_view_finance': True, 'can_manage_finance': True,
                'can_view_reports': True, 'can_manage_attendance': True
            }),
            ('brand_manager', 'مدير البراند', 'تحكم كامل في براند واحد', {
                'can_manage_members': True, 'can_manage_subscriptions': True, 'can_view_finance': True,
                'can_manage_finance': True, 'can_view_reports': True, 'can_manage_attendance': True
            }),
            ('receptionist', 'موظف استقبال', 'إدارة العملاء والاشتراكات', {
                'can_manage_members': True, 'can_manage_subscriptions': True, 'can_manage_attendance': True
            }),
            ('finance', 'مالية براند', 'إدارة مالية براند واحد', {
                'can_view_finance': True, 'can_manage_finance': True, 'can_view_reports': True
            }),
            ('finance_admin', 'مالية عامة', 'الاطلاع على مالية جميع البراندات', {
                'can_view_all_brands': True, 'can_view_finance': True, 'can_view_reports': True
            }),
            ('coach', 'مدرب', 'الاطلاع على بيانات شخصية فقط', {
                'can_manage_attendance': True
            }),
        ]

        for name_en, name_ar, description, permissions in roles_data:
            if not Role.query.filter_by(name_en=name_en).first():
                role = Role(name=name_ar, name_en=name_en, description=description, **permissions)
                db.session.add(role)
                click.echo(f'Created role: {name_ar}')

        db.session.commit()
        click.echo('Database initialized successfully!')
