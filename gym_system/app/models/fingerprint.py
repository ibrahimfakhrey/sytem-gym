from datetime import datetime
from app import db


class FingerprintSyncLog(db.Model):
    """Fingerprint sync log records"""
    __tablename__ = 'fingerprint_sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)

    # Type: 'attendance', 'enrollment', 'full'
    sync_type = db.Column(db.String(20), nullable=False)

    records_synced = db.Column(db.Integer, default=0)
    last_sync_id = db.Column(db.Integer)

    # Status: 'success', 'failed', 'partial'
    status = db.Column(db.String(20), default='success')
    error_message = db.Column(db.Text)

    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<FingerprintSyncLog {self.sync_type} - {self.synced_at}>'

    @property
    def status_text(self):
        """Status in Arabic"""
        status_map = {
            'success': 'نجح',
            'failed': 'فشل',
            'partial': 'جزئي'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS class for status"""
        class_map = {
            'success': 'success',
            'failed': 'danger',
            'partial': 'warning'
        }
        return class_map.get(self.status, 'secondary')

    @classmethod
    def get_last_sync(cls, brand_id):
        """Get last sync for brand"""
        return cls.query.filter_by(brand_id=brand_id).order_by(
            cls.synced_at.desc()
        ).first()

    @classmethod
    def get_sync_status(cls, brand_id):
        """Get sync status info"""
        last_sync = cls.get_last_sync(brand_id)
        if not last_sync:
            return {
                'status': 'never',
                'message': 'لم تتم المزامنة بعد',
                'class': 'secondary'
            }

        from datetime import datetime, timedelta
        time_diff = datetime.utcnow() - last_sync.synced_at
        minutes = time_diff.seconds // 60

        if time_diff > timedelta(minutes=5):
            return {
                'status': 'warning',
                'message': f'آخر مزامنة منذ {minutes} دقيقة',
                'class': 'warning'
            }

        return {
            'status': 'ok',
            'message': f'آخر مزامنة منذ {minutes} دقيقة',
            'class': 'success'
        }
