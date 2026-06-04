#!/usr/bin/env python
"""
Migration: Add proof_image column to subscriptions table.

Stores the path (relative to app/static/) of an optional payment-proof image
uploaded when creating a subscription. Saved files live under
  app/static/uploads/subscriptions/<uuid>.<ext>
and the column holds e.g. "uploads/subscriptions/<uuid>.jpg".

Date: 2026-06-04
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _column_exists(conn, table: str, column: str) -> bool:
    """Check whether `column` exists on `table` (SQLite-friendly + portable)."""
    try:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        if rows:
            return any(r[1] == column for r in rows)
    except Exception:
        pass
    # Portable fallback via information_schema (Postgres, MySQL, ...)
    try:
        from sqlalchemy import text
        row = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).first()
        return row is not None
    except Exception:
        return False


def run_migration():
    from app import create_app, db

    app = create_app()
    with app.app_context():
        print("Starting migration: add subscriptions.proof_image ...")

        # Ensure the upload subfolder exists
        upload_folder = os.path.join(
            app.config["UPLOAD_FOLDER"], "subscriptions"
        )
        os.makedirs(upload_folder, exist_ok=True)
        print(f"📁 Ensured upload folder: {upload_folder}")

        with db.engine.connect() as conn:
            if _column_exists(conn, "subscriptions", "proof_image"):
                print("⏭️  Column proof_image already exists on subscriptions, "
                      "skipping ALTER TABLE")
            else:
                conn.exec_driver_sql(
                    "ALTER TABLE subscriptions "
                    "ADD COLUMN proof_image VARCHAR(255)"
                )
                conn.commit()
                print("✅ Added proof_image column to subscriptions")

        print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
