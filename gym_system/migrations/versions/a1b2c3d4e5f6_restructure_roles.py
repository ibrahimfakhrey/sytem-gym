"""Restructure roles: owner→admin, brand_manager→owner, add branch_manager

Revision ID: a1b2c3d4e5f6
Revises: f787e45c0ad3
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = 'f787e45c0ad3'
branch_labels = None
depends_on = None


def upgrade():
    # ── Step 1: Rename existing roles ──
    # Order matters because name_en has UNIQUE constraint
    # Rename owner→admin FIRST (frees up 'owner' name_en)
    op.execute("UPDATE roles SET name_en = 'admin', name = 'أدمن', description = 'مدير النظام - صلاحية كاملة على جميع البراندات' WHERE name_en = 'owner'")

    # Now rename brand_manager→owner
    op.execute("UPDATE roles SET name_en = 'owner', name = 'المالك', description = 'مالك البراند - تحكم كامل في براند واحد' WHERE name_en = 'brand_manager'")

    # Rename receptionist→branch_receptionist
    op.execute("UPDATE roles SET name_en = 'branch_receptionist', name = 'استقبال فرع', description = 'موظف استقبال على مستوى الفرع' WHERE name_en = 'receptionist'")

    # Rename finance→branch_finance
    op.execute("UPDATE roles SET name_en = 'branch_finance', name = 'مالية فرع', description = 'مالية على مستوى فرع واحد' WHERE name_en = 'finance'")

    # Rename coach/employee→employee
    op.execute("UPDATE roles SET name_en = 'employee', name = 'موظف', description = 'موظف على مستوى الفرع' WHERE name_en IN ('coach', 'employee')")

    # Update finance_admin Arabic name
    op.execute("UPDATE roles SET name = 'مالية عامة', description = 'الاطلاع على مالية جميع البراندات' WHERE name_en = 'finance_admin'")

    # ── Step 2: Insert new branch_manager role ──
    op.execute("""
        INSERT INTO roles (name, name_en, description,
            is_owner, can_view_all_brands,
            can_manage_members, can_manage_subscriptions,
            can_view_finance, can_manage_finance,
            can_view_reports, can_manage_attendance,
            can_view_complaints, can_manage_complaints,
            can_view_daily_closing, can_manage_daily_closing,
            can_manage_classes, can_approve_expenses,
            can_manage_offers, can_manage_gift_cards)
        VALUES ('مدير الفرع', 'branch_manager', 'مدير فرع - تحكم كامل في فرع واحد',
            0, 0,
            1, 1,
            1, 1,
            1, 1,
            1, 1,
            1, 1,
            1, 1,
            1, 1)
    """)

    # ── Step 3: Update permissions on renamed roles ──

    # admin: ensure ALL permissions are on
    op.execute("""
        UPDATE roles SET
            is_owner = 1, can_view_all_brands = 1,
            can_manage_members = 1, can_manage_subscriptions = 1,
            can_view_finance = 1, can_manage_finance = 1,
            can_view_reports = 1, can_manage_attendance = 1,
            can_view_complaints = 1, can_manage_complaints = 1,
            can_view_daily_closing = 1, can_manage_daily_closing = 1,
            can_manage_classes = 1, can_approve_expenses = 1,
            can_manage_offers = 1, can_manage_gift_cards = 1
        WHERE name_en = 'admin'
    """)

    # owner (brand): full brand control, NOT is_owner
    op.execute("""
        UPDATE roles SET
            is_owner = 0, can_view_all_brands = 0,
            can_manage_members = 1, can_manage_subscriptions = 1,
            can_view_finance = 1, can_manage_finance = 1,
            can_view_reports = 1, can_manage_attendance = 1,
            can_view_complaints = 1, can_manage_complaints = 1,
            can_view_daily_closing = 1, can_manage_daily_closing = 1,
            can_manage_classes = 1, can_approve_expenses = 1,
            can_manage_offers = 1, can_manage_gift_cards = 1
        WHERE name_en = 'owner'
    """)

    # branch_receptionist: add complaints view + classes
    op.execute("""
        UPDATE roles SET
            can_view_complaints = 1, can_manage_complaints = 0,
            can_manage_classes = 1
        WHERE name_en = 'branch_receptionist'
    """)

    # branch_finance: add daily closing
    op.execute("""
        UPDATE roles SET
            can_view_daily_closing = 1, can_manage_daily_closing = 1
        WHERE name_en = 'branch_finance'
    """)

    # finance_admin: add daily closing view
    op.execute("""
        UPDATE roles SET
            can_view_daily_closing = 1
        WHERE name_en = 'finance_admin'
    """)


def downgrade():
    # Reverse renames (order matters again)
    op.execute("UPDATE roles SET name_en = 'brand_manager', name = 'مدير البراند' WHERE name_en = 'owner'")
    op.execute("UPDATE roles SET name_en = 'owner', name = 'المالك' WHERE name_en = 'admin'")
    op.execute("UPDATE roles SET name_en = 'receptionist', name = 'موظف استقبال' WHERE name_en = 'branch_receptionist'")
    op.execute("UPDATE roles SET name_en = 'finance', name = 'مالية براند' WHERE name_en = 'branch_finance'")
    op.execute("UPDATE roles SET name_en = 'coach', name = 'مدرب' WHERE name_en = 'employee'")
    op.execute("DELETE FROM roles WHERE name_en = 'branch_manager'")
