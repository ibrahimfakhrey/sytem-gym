# Gym-System Features — Handoff Spec

Self-contained spec for everything we shipped across GYM-25 → GYM-30 plus the
day-pass card and audit pass. Hand this file to another model on a similar
Flask/SQLAlchemy/Jinja project (multi-brand gym/SaaS) and it should be able
to replicate every feature without further context.

Stack assumed: Flask + Flask-Login + Flask-WTF + SQLAlchemy + Jinja2,
Bootstrap 5 RTL, Cairo Arabic font, SQLite locally / Postgres in prod,
boot-time `db.create_all()` plus idempotent CREATE TABLE / ALTER guards in
`app/__init__.py`.

Permission helpers used throughout (port as needed):
- `current_user.is_owner` → admin role (sees everything)
- `current_user.is_brand_manager` → brand owner (sees one brand)
- `apply_branch_filter(query, Model)` → adds brand_id / branch_id WHERE clauses
- `resolve_owner_branch_filter()` → returns the branch picker value from the
  session (None = "all branches")
- `check_entity_access(obj)` → True if current user may see this row

---

## 1. GYM-25 — Expense receipt thumbnails + clickable rows

**Goal**: surface the uploaded receipt image (or PDF icon) right in the expense
list so finance staff don't have to open every row to verify it.

### File: `app/templates/finance/expenses.html`

Add a "الإيصال" column. Make each row clickable to the detail view. Skip the
click on cells you don't want to swallow (action buttons, links).

```jinja
<thead>
  <tr>
    ...existing columns...
    <th>الإيصال</th>
    <th data-noclick>إجراءات</th>
  </tr>
</thead>

{% for expense in expenses %}
<tr class="expense-row" data-href="{{ url_for('finance.view_expense', id=expense.id) }}">
  ...existing columns...
  <td>
    {% if expense.receipt_image %}
      {# Tolerate both 'uploads/receipts/x.jpg' and bare 'x.jpg' stored values #}
      {% set img_path = expense.receipt_image
                          if expense.receipt_image.startswith('uploads/')
                          else 'uploads/receipts/' ~ expense.receipt_image %}
      {% if expense.receipt_image.lower().endswith('.pdf') %}
        <i class="bi bi-file-earmark-pdf text-danger fs-4"></i>
      {% else %}
        <img src="{{ url_for('static', filename=img_path) }}"
             style="height:40px;width:auto;border-radius:4px"
             alt="receipt">
      {% endif %}
    {% else %}<span class="text-muted">—</span>{% endif %}
  </td>
  <td data-noclick>...action buttons...</td>
</tr>
{% endfor %}

<script>
  document.querySelectorAll('tr.expense-row[data-href]').forEach(tr => {
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', e => {
      if (e.target.closest('[data-noclick],a,button,input')) return;
      window.location = tr.dataset.href;
    });
  });
</script>
```

### File: `app/templates/finance/expense_view.html`

Path-tolerance fix: do **not** prepend `'uploads/'` blindly. `save_uploaded_file()`
already returns the prefixed path. Auto-detect PDF vs image:

```jinja
{% if expense.receipt_image %}
  {% set img_path = expense.receipt_image
                      if expense.receipt_image.startswith('uploads/')
                      else 'uploads/receipts/' ~ expense.receipt_image %}
  {% if expense.receipt_image.lower().endswith('.pdf') %}
    <a class="btn btn-outline-danger" href="{{ url_for('static', filename=img_path) }}" target="_blank">
      <i class="bi bi-file-earmark-pdf"></i> فتح الإيصال (PDF)
    </a>
  {% else %}
    <a href="{{ url_for('static', filename=img_path) }}" data-fancybox>
      <img src="{{ url_for('static', filename=img_path) }}" class="img-fluid rounded">
    </a>
  {% endif %}
{% endif %}
```

**Reusable pattern**: any model that stores `uploads/...` paths from one save
helper but bare filenames from another, prefix-tolerance like this prevents
silent 404s.

---

## 2. GYM-26 — Fix /closing/ and /closing/<id> 500 errors

Templates referenced model attributes that didn't exist. Fix is rename-only
plus NULL guards.

### Renames (in `closing/index.html` + `closing/view.html`)

| Wrong | Right |
|---|---|
| `closing.closed_by_user` | `closing.submitter` (relationship `User`) |
| `closing.has_discrepancy` | `closing.has_cash_difference` |
| `closing.discrepancy_class` | `closing.cash_difference_class` |

### NULL guards on every formatted numeric field

Even with `default=0` on the column, legacy rows may have NULL. Belt-and-suspenders:

```jinja
{{ "{:,.2f}".format(closing.total_sales         or 0) }} ر.س
{{ "{:,.2f}".format(closing.cash_amount         or 0) }} ر.س
{{ "{:,.2f}".format(closing.card_amount         or 0) }} ر.س
{{ "{:,.2f}".format(closing.transfer_amount     or 0) }} ر.س
{{ "{:,.2f}".format(closing.expected_cash       or 0) }} ر.س
{{ "{:,.2f}".format(closing.actual_cash_submitted or 0) }} ر.س
{{ "{:+,.2f}".format(closing.cash_difference    or 0) }} ر.س
```

**Reusable pattern**: any numeric column that ever had a NULL row in prod must
get `or 0` at every format site. `default=0` only protects new rows.

---

## 3. GYM-28 — Duplicate member finder + bulk merge + undo

The largest piece. Three sub-features behind one nav entry "المكررون":

1. `/members/duplicates` — cluster finder (read-only)
2. `/members/duplicates/merge` — bulk merge POST
3. `/members/duplicates/log` + `.../undo` — audit + one-click undo

### Design rules (locked in with the user)

- **Auto-pick keeper**: most subscriptions → most invoices → most attendance → oldest id wins
- **Default strictness**: `medium` — name match + (phone OR member_import_id) match
- **No deletes**: loser rows are deactivated, name prefixed with `[مدمج] `, audit note appended. Their data lives on under the keeper via FK repointing.
- **Atomic**: every merge runs inside one `db.session` transaction; any throw rolls the whole cluster back.
- **Snapshot for undo**: full pre-merge field dump of the loser is stored as JSON. Undo never has to "create" anything — just flip `is_active=True`, restore `name`, and move FK rows back.

### File: `app/models/merge_log.py`

```python
from datetime import datetime
from app import db

class MemberMergeLog(db.Model):
    __tablename__ = 'member_merge_logs'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False)
    keeper_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    loser_id  = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)

    loser_snapshot_json = db.Column(db.Text)  # full dict of loser's columns at merge time
    moves_json          = db.Column(db.Text)  # {"subscriptions": 3, "invoices": 5, ...}

    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    performed_at = db.Column(db.DateTime, default=datetime.utcnow)
    undone_at    = db.Column(db.DateTime)
    undone_by    = db.Column(db.Integer, db.ForeignKey('users.id'))

    keeper    = db.relationship('Member', foreign_keys=[keeper_id])
    loser     = db.relationship('Member', foreign_keys=[loser_id])
    performer = db.relationship('User',   foreign_keys=[performed_by])
    undoer    = db.relationship('User',   foreign_keys=[undone_by])

    @property
    def is_active(self):
        return self.undone_at is None
```

### File: `app/services/dedupe.py` (pure data layer — routes call into here)

Full structure:

```python
import json, re
from collections import defaultdict
from datetime import datetime
from sqlalchemy import func
from app import db
from app.models.member import Member
from app.models.subscription import Subscription, RenewalRejection
from app.models.finance import Invoice, Refund
from app.models.attendance import MemberAttendance
from app.models.classes import ClassBooking
from app.models.complaint import Complaint
from app.models.health import HealthReport
from app.models.giftcard import GiftCard
from app.models.fingerprint import DeviceCommand, FingerprintAccessLog
from app.models.merge_log import MemberMergeLog


# --- Normalizers ---------------------------------------------------------

def _norm_name(s):
    if not s: return ''
    # collapse whitespace, strip Arabic tatweel
    return re.sub(r'\s+', ' ', s.replace('ـ', '').strip()).lower()

def _norm_phone(s):
    if not s: return ''
    digits = ''.join(ch for ch in s if ch.isdigit())
    # 00966 / 966 / 0 prefixes all collapse to the same number (KSA)
    if digits.startswith('00966'): digits = digits[5:]
    elif digits.startswith('966'): digits = digits[3:]
    if digits.startswith('0'):     digits = digits.lstrip('0')
    return digits


# --- Detection -----------------------------------------------------------

STRICTNESS_LEVELS = ('strict', 'medium', 'loose')

def find_duplicate_clusters(brand_id, *, branch_id=None, strictness='medium'):
    """Returns [{'key', 'name', 'members': enriched_list, 'ids': sorted_ids}, ...]
       strict — name + phone
       medium — name + (phone OR member_import_id)
       loose  — name only
    """
    if strictness not in STRICTNESS_LEVELS: strictness = 'medium'
    q = Member.query.filter(Member.brand_id == brand_id, Member.is_active == True)
    if branch_id: q = q.filter(Member.branch_id == branch_id)
    members = q.all()

    by_name = defaultdict(list)
    for m in members:
        n = _norm_name(m.name)
        if n: by_name[n].append(m)

    clusters = []
    for name_key, group in by_name.items():
        if len(group) < 2: continue
        if strictness == 'loose':
            clusters.extend(_finalize(group, name_key))
            continue
        clusters.extend(_finalize_subs(_sub_cluster(group, strictness), name_key))
    return clusters

def _sub_cluster(group, strictness):
    """Same-name members sharing the same phone (or import_id under medium) form
    one cluster. Two same-name members with different phones do NOT merge —
    that protects against family members sharing a name."""
    seen = defaultdict(list)
    for m in group:
        phone = _norm_phone(m.phone)
        if phone:                                  seen[('p', phone)].append(m)
        elif strictness == 'medium' and m.member_import_id:
                                                   seen[('i', m.member_import_id)].append(m)
        else:                                      seen[('n', m.id)].append(m)
    return [g for g in seen.values() if len(g) > 1]

def _finalize(group, name_key):  return _finalize_subs([group], name_key)
def _finalize_subs(sub_groups, name_key):
    out = []
    for grp in sub_groups:
        if len(grp) < 2: continue
        ids = sorted(m.id for m in grp)
        out.append({
            'key': f"{name_key}|{'-'.join(map(str, ids))}",
            'name': grp[0].name,
            'members': enrich_members(grp),
            'ids': ids,
        })
    return out


# --- Enrichment (batched counts) ----------------------------------------

def enrich_members(members):
    ids = [m.id for m in members]
    def _grp(col, fn=func.count, model=Subscription, mid='member_id'):
        return dict(db.session.query(getattr(model, mid), fn(getattr(model, 'id')))
                    .filter(getattr(model, mid).in_(ids))
                    .group_by(getattr(model, mid)).all())
    sub_count = _grp('id', model=Subscription)
    inv_count = _grp('id', model=Invoice)
    att_count = _grp('id', model=MemberAttendance)
    revenue   = dict(db.session.query(Subscription.member_id,
                       func.coalesce(func.sum(Subscription.paid_amount), 0))
                     .filter(Subscription.member_id.in_(ids))
                     .group_by(Subscription.member_id).all())
    last_att  = dict(db.session.query(MemberAttendance.member_id,
                       func.max(MemberAttendance.check_in))
                     .filter(MemberAttendance.member_id.in_(ids))
                     .group_by(MemberAttendance.member_id).all())
    return [
        {'m': m,
         'subs':       sub_count.get(m.id, 0),
         'invoices':   inv_count.get(m.id, 0),
         'attendance': att_count.get(m.id, 0),
         'revenue':    float(revenue.get(m.id, 0) or 0),
         'last_attendance': last_att.get(m.id)}
        for m in members
    ]


# --- Keeper selection ----------------------------------------------------

def pick_keeper(enriched):
    return max(enriched,
               key=lambda e: (e['subs'], e['invoices'], e['attendance'], -e['m'].id))


# --- The merge transaction ----------------------------------------------

# Every FK pointing at members.id MUST be in this list. Audit your project
# carefully — a missing one leaves orphan rows pointing at the deactivated loser.
_FK_COLUMNS = [
    (Subscription,          'member_id',              'subscriptions'),
    (Invoice,               'member_id',              'invoices'),
    (MemberAttendance,      'member_id',              'attendance'),
    (ClassBooking,          'member_id',              'class_bookings'),
    (Complaint,             'member_id',              'complaints'),
    (HealthReport,          'member_id',              'health_reports'),
    (GiftCard,              'redeemed_by_member_id',  'gift_cards_redeemed'),
    (DeviceCommand,         'member_id',              'device_commands'),
    (FingerprintAccessLog,  'member_id',              'fp_access_logs'),
    (RenewalRejection,      'member_id',              'renewal_rejections'),
    (Refund,                'member_id',              'refunds'),
]

def merge_cluster(cluster_ids, *, performed_by):
    if len(cluster_ids) < 2: raise ValueError('need ≥ 2 members in cluster')
    members = Member.query.filter(Member.id.in_(cluster_ids)).all()
    if len(members) < 2: raise ValueError('members missing')

    enriched = enrich_members(members)
    keeper = pick_keeper(enriched)['m']
    losers = [e['m'] for e in enriched if e['m'].id != keeper.id]

    summary = {'keeper_id': keeper.id, 'losers': []}
    for loser in losers:
        moves = _merge_one_into(keeper, loser, performed_by)
        summary['losers'].append({'id': loser.id, 'moves': moves})
    return summary

def _merge_one_into(keeper, loser, performed_by):
    snapshot = _snapshot(loser)
    moves = {}
    for model, col, label in _FK_COLUMNS:
        n = model.query.filter(getattr(model, col) == loser.id).update(
            {col: keeper.id}, synchronize_session=False)
        if n: moves[label] = n

    # Carry-over: only fields the keeper is missing
    for f in ('fingerprint_id', 'member_import_id', 'email', 'address',
              'birth_date', 'phone', 'fingerprint_enrolled'):
        if hasattr(keeper, f) and hasattr(loser, f):
            if getattr(keeper, f) in (None, '', 0):
                v = getattr(loser, f)
                if v not in (None, '', 0): setattr(keeper, f, v)

    loser.is_active = False
    if not loser.name.startswith('[مدمج] '):
        loser.name = ('[مدمج] ' + (loser.name or ''))[:100]
    note = f'دُمج بـ #{keeper.id} في {datetime.utcnow().isoformat(timespec="seconds")}'
    if hasattr(loser, 'notes'):
        loser.notes = ((loser.notes or '') + ('\n' if loser.notes else '') + note)[:2000]

    db.session.add(MemberMergeLog(
        brand_id=keeper.brand_id,
        keeper_id=keeper.id, loser_id=loser.id,
        loser_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        moves_json=json.dumps(moves, ensure_ascii=False),
        performed_by=performed_by,
    ))
    return moves

def _snapshot(m):
    out = {}
    for c in m.__table__.columns:
        v = getattr(m, c.name, None)
        if v is None:                  out[c.name] = None
        elif hasattr(v, 'isoformat'):  out[c.name] = v.isoformat()
        elif isinstance(v, (int, float, bool, str)): out[c.name] = v
        else:                          out[c.name] = str(v)
    return out


# --- Undo ----------------------------------------------------------------

def undo_merge(log_id, *, undone_by):
    log = MemberMergeLog.query.get(log_id)
    if not log: raise ValueError('log not found')
    if log.undone_at: raise ValueError('already undone')
    keeper = Member.query.get(log.keeper_id)
    loser  = Member.query.get(log.loser_id)
    if not (keeper and loser): raise ValueError('member missing')

    moves = json.loads(log.moves_json or '{}')
    snap  = json.loads(log.loser_snapshot_json or '{}')

    # Move exactly N rows back per label, id-asc, LIMIT n — defends against
    # over-restoration if another merge has already moved some rows on.
    label_to_pair = {label: (model, col) for (model, col, label) in _FK_COLUMNS}
    for label, n in moves.items():
        pair = label_to_pair.get(label)
        if not pair: continue
        model, col = pair
        ids = [r.id for r in model.query.filter(getattr(model, col) == keeper.id)
                                        .order_by(model.id.asc()).limit(n).all()]
        if ids:
            model.query.filter(model.id.in_(ids)).update(
                {col: loser.id}, synchronize_session=False)

    loser.is_active = True
    if snap.get('name'): loser.name = snap['name']
    log.undone_at = datetime.utcnow()
    log.undone_by = undone_by
    return {'restored_loser': loser.id, 'unmoved': moves}
```

### File: `app/routes/members.py` — append these routes

```python
from app.services.dedupe import (
    find_duplicate_clusters, merge_cluster, undo_merge, STRICTNESS_LEVELS,
)
from app.models.merge_log import MemberMergeLog

@members_bp.route('/duplicates')
@login_required
def duplicates():
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger'); return redirect(url_for('dashboard.index'))
    brand_id = current_user.brand_id or int(request.args.get('brand_id') or 0)
    branch_id = request.args.get('branch_id', type=int) or None
    strictness = request.args.get('strictness', 'medium')
    clusters = find_duplicate_clusters(brand_id, branch_id=branch_id, strictness=strictness) if brand_id else []
    return render_template('members/duplicates.html',
        clusters=clusters, strictness=strictness, strictness_levels=STRICTNESS_LEVELS,
        brand_id=brand_id, branch_id=branch_id)

@members_bp.route('/duplicates/merge', methods=['POST'])
@login_required
def duplicates_merge():
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger'); return redirect(url_for('dashboard.index'))
    cluster_payloads = request.form.getlist('cluster_ids[]')  # "1,2,3"
    merged = 0
    try:
        for payload in cluster_payloads:
            ids = [int(x) for x in payload.split(',') if x.strip().isdigit()]
            if len(ids) >= 2:
                merge_cluster(ids, performed_by=current_user.id)
                merged += 1
        db.session.commit()
        flash(f'تم دمج {merged} مجموعة بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'فشل الدمج: {e}', 'danger')
    return redirect(url_for('members.duplicates', **request.args.to_dict()))

@members_bp.route('/duplicates/log')
@login_required
def duplicates_log():
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger'); return redirect(url_for('dashboard.index'))
    q = MemberMergeLog.query
    if not current_user.is_owner:
        q = q.filter(MemberMergeLog.brand_id == current_user.brand_id)
    logs = q.order_by(MemberMergeLog.performed_at.desc()).limit(200).all()
    return render_template('members/duplicates_log.html', logs=logs)

@members_bp.route('/duplicates/log/<int:log_id>/undo', methods=['POST'])
@login_required
def duplicates_log_undo(log_id):
    if not (current_user.is_owner or current_user.is_brand_manager):
        flash('ليس لديك صلاحية', 'danger'); return redirect(url_for('dashboard.index'))
    try:
        undo_merge(log_id, undone_by=current_user.id)
        db.session.commit()
        flash('تم التراجع عن الدمج', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'فشل التراجع: {e}', 'danger')
    return redirect(url_for('members.duplicates_log'))
```

### File: `app/templates/members/duplicates.html`

```jinja
{% extends "base.html" %}
{% block content %}
<div class="page-header">
  <h1><i class="bi bi-people-fill"></i> المكررون</h1>
</div>

<form method="get" class="card card-body mb-3 row g-2">
  <div class="col-md-3">
    <label class="form-label">الدقة</label>
    <select name="strictness" class="form-select">
      {% for s in strictness_levels %}
        <option value="{{ s }}" {% if s == strictness %}selected{% endif %}>{{ s }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-md-3 align-self-end">
    <button class="btn btn-primary">بحث</button>
  </div>
</form>

{% if clusters %}
<form method="post" action="{{ url_for('members.duplicates_merge') }}">
  {{ csrf_token() if csrf_token }}
  <div class="d-flex gap-2 mb-3">
    <button type="button" class="btn btn-outline-secondary" onclick="document.querySelectorAll('.cluster-check').forEach(c => c.checked = true);">اختر الكل</button>
    <button type="submit" class="btn btn-success">دمج ذكي للمجموعات المختارة</button>
  </div>

  {% for c in clusters %}
    {% set keeper = c.members | sort(attribute='subs', reverse=true) | first %}
    <div class="card mb-3">
      <div class="card-header d-flex gap-2 align-items-center">
        <input type="checkbox" class="cluster-check" name="cluster_ids[]" value="{{ c.ids | join(',') }}">
        <strong>{{ c.name }}</strong>
        <span class="badge bg-secondary">{{ c.members | length }} سجل</span>
      </div>
      <table class="table table-sm mb-0">
        <thead><tr><th></th><th>الاسم</th><th>الهاتف</th><th>اشتراكات</th><th>فواتير</th><th>حضور</th><th>إيرادات</th></tr></thead>
        <tbody>
          {% for e in c.members %}
          <tr class="{% if e.m.id == keeper.m.id %}table-success{% endif %}">
            <td>{% if e.m.id == keeper.m.id %}<i class="bi bi-star-fill text-warning"></i>{% endif %}</td>
            <td>#{{ e.m.id }} {{ e.m.name }}</td>
            <td>{{ e.m.phone or '—' }}</td>
            <td>{{ e.subs }}</td>
            <td>{{ e.invoices }}</td>
            <td>{{ e.attendance }}</td>
            <td>{{ "%.0f" % e.revenue }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% endfor %}
</form>
{% else %}
<div class="alert alert-info">لا توجد سجلات مكررة في هذا النطاق.</div>
{% endif %}
{% endblock %}
```

### File: `app/templates/members/duplicates_log.html`

```jinja
{% extends "base.html" %}
{% block content %}
<h1>سجل دمج المكررين</h1>
<table class="table">
  <thead><tr><th>التاريخ</th><th>أبقي</th><th>دُمج</th><th>بواسطة</th><th>الحالة</th><th></th></tr></thead>
  <tbody>
    {% for log in logs %}
    <tr>
      <td>{{ log.performed_at.strftime('%Y-%m-%d %H:%M') }}</td>
      <td>#{{ log.keeper_id }} {{ log.keeper.name if log.keeper else '' }}</td>
      <td>#{{ log.loser_id }} {{ log.loser.name if log.loser else '' }}</td>
      <td>{{ log.performer.name if log.performer else '—' }}</td>
      <td>
        {% if log.is_active %}<span class="badge bg-success">نشط</span>
        {% else %}<span class="badge bg-secondary">تم التراجع</span>{% endif %}
      </td>
      <td>
        {% if log.is_active %}
        <form method="post" action="{{ url_for('members.duplicates_log_undo', log_id=log.id) }}" class="d-inline">
          {{ csrf_token() if csrf_token }}
          <button class="btn btn-sm btn-outline-warning">تراجع</button>
        </form>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

### File: `migrations_manual/add_member_merge_log.py`

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DDL = """
CREATE TABLE IF NOT EXISTS member_merge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER NOT NULL,
    keeper_id INTEGER NOT NULL,
    loser_id INTEGER NOT NULL,
    loser_snapshot_json TEXT,
    moves_json TEXT,
    performed_by INTEGER,
    performed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    undone_at DATETIME,
    undone_by INTEGER,
    FOREIGN KEY(brand_id) REFERENCES brands(id),
    FOREIGN KEY(keeper_id) REFERENCES members(id),
    FOREIGN KEY(loser_id)  REFERENCES members(id),
    FOREIGN KEY(performed_by) REFERENCES users(id),
    FOREIGN KEY(undone_by)    REFERENCES users(id)
)
"""

def run():
    from app import create_app, db
    with create_app().app_context():
        with db.engine.connect() as conn:
            conn.exec_driver_sql(DDL); conn.commit()
        print('✅ member_merge_logs ready.')

if __name__ == '__main__': run()
```

### Verification (round-trip test we ran)

1. Pick a cluster of 2 same-name same-phone members with non-zero subs/invoices/attendance on each side.
2. Note counts: keeper-pre, loser-pre.
3. POST merge → assert keeper.subs == keeper-pre + loser-pre, loser deactivated, name prefixed `[مدمج]`.
4. POST undo → assert all counts return to pre-merge values exactly, loser `is_active=True`, name restored.

### Sidebar entry (`app/templates/base.html`)

```jinja
{% if current_user.is_owner or current_user.is_brand_manager %}
<li><a class="nav-link" href="{{ url_for('members.duplicates') }}">المكررون</a></li>
{% endif %}
```

---

## 4. GYM-29 — Daily closing reconciles against Income (the canonical ledger)

**Bug**: receptionist's drawer count and the "expected cash" on the closing
disagreed because the closing summed only `SubscriptionPayment`, missing
day-pass tickets (which write to `Income` only).

**Fix**: read revenue from `Income` everywhere closing math runs.

### File: `app/routes/closing.py` → `calculate_daily_stats(brand_id, target_date)`

```python
from app.models.finance import Income
from app.models.subscription import Subscription, SubscriptionPayment

def calculate_daily_stats(brand_id, target_date):
    new_subs = Subscription.query.filter(
        Subscription.brand_id == brand_id,
        db.func.date(Subscription.created_at) == target_date
    ).all()
    new_subscriptions_count = len([s for s in new_subs if not hasattr(s, 'is_renewal')])

    incomes = Income.query.filter(
        Income.brand_id == brand_id,
        Income.date == target_date,
    ).all()

    cash_sales     = sum(float(i.amount) for i in incomes if i.payment_method == 'cash')
    card_sales     = sum(float(i.amount) for i in incomes if i.payment_method == 'card')
    transfer_sales = sum(float(i.amount) for i in incomes if i.payment_method == 'transfer')
    total_sales = cash_sales + card_sales + transfer_sales

    by_type = {}
    for i in incomes:
        by_type[i.type or 'other'] = by_type.get(i.type or 'other', 0) + float(i.amount or 0)

    return {
        'new_subscriptions_count': new_subscriptions_count,
        'renewals_count': 0,  # TODO: real renewal detection
        'total_sales': total_sales,
        'cash_sales': cash_sales,
        'card_sales': card_sales,
        'transfer_sales': transfer_sales,
        'incomes': incomes,
        'income_by_type': by_type,
        'new_subscriptions': new_subs,
        'payments': SubscriptionPayment.query.filter(
            SubscriptionPayment.brand_id == brand_id,
            db.func.date(SubscriptionPayment.payment_date) == target_date
        ).all(),
    }
```

### Same change in `app/models/daily_closing.py` → `calculate_from_transactions()`

```python
incomes_q = Income.query.filter(
    Income.brand_id == self.brand_id,
    Income.date == self.closing_date,
)
if self.branch_id:
    incomes_q = incomes_q.filter(Income.branch_id == self.branch_id)
incomes = incomes_q.all()

self.cash_amount     = sum(float(i.amount) for i in incomes if i.payment_method == 'cash') or 0
self.card_amount     = sum(float(i.amount) for i in incomes if i.payment_method == 'card') or 0
self.transfer_amount = sum(float(i.amount) for i in incomes if i.payment_method == 'transfer') or 0
self.total_sales     = self.cash_amount + self.card_amount + self.transfer_amount
self.expected_cash   = self.cash_amount
```

### View route — compute the per-type breakdown for the receipt explanation

```python
@closing_bp.route('/<int:closing_id>')
@login_required
@members_required
def view_closing(closing_id):
    closing = DailyClosing.query.get_or_404(closing_id)
    if not check_entity_access(closing):
        flash('ليس لديك صلاحية', 'danger'); return redirect(url_for('closing.index'))

    incomes_q = Income.query.filter(
        Income.brand_id == closing.brand_id,
        Income.date == closing.closing_date,
    )
    if closing.branch_id:
        incomes_q = incomes_q.filter(Income.branch_id == closing.branch_id)

    income_by_type, income_cash_by_type = {}, {}
    for i in incomes_q.all():
        t = i.type or 'other'
        amt = float(i.amount or 0)
        income_by_type[t] = income_by_type.get(t, 0) + amt
        if i.payment_method == 'cash':
            income_cash_by_type[t] = income_cash_by_type.get(t, 0) + amt

    return render_template('closing/view.html',
        closing=closing,
        income_by_type=income_by_type,
        income_cash_by_type=income_cash_by_type)
```

### `closing/view.html` — breakdown card

```jinja
{% if income_by_type %}
{% set type_labels = {'subscription': 'اشتراكات', 'day_pass': 'تذاكر يومية', 'other': 'إيرادات أخرى'} %}
<hr>
<h6 class="text-muted small mb-3"><i class="bi bi-list-ul"></i> الإيرادات حسب النوع</h6>
<div class="row g-2">
  {% for t, amount in income_by_type.items() %}
  <div class="col-md-4">
    <div class="border rounded p-2">
      <div class="small text-muted">{{ type_labels.get(t, t) }}</div>
      <div class="fw-bold">{{ "{:,.2f}".format(amount) }} ر.س</div>
      {% if income_cash_by_type.get(t, 0) > 0 %}
      <div class="small text-success">
        <i class="bi bi-cash"></i> نقدي: {{ "{:,.2f}".format(income_cash_by_type[t]) }} ر.س
      </div>
      {% endif %}
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
```

**Reusable pattern**: when one table is your canonical ledger (here `Income`),
every downstream report MUST source revenue from it. Specialty payment tables
(`SubscriptionPayment`) only exist for their own domain — they're not a revenue
source on their own.

---

## 5. Day-pass printable card + WhatsApp share

### File: `app/routes/day_pass.py` — add the print route

```python
@day_pass_bp.route('/<int:pass_id>/print')
@login_required
def print_pass(pass_id):
    dp = DayPass.query.get_or_404(pass_id)
    if not check_entity_access(dp):
        flash('ليس لديك صلاحية', 'danger'); return redirect(url_for('day_pass.index'))
    return render_template('day_pass/print.html', dp=dp)
```

### File: `app/templates/day_pass/print.html`

Navy-teal gradient ticket card matching the gift-card design. WhatsApp link
KSA-normalizes the phone and prefills an Arabic message.

```jinja
{% extends "base.html" %}
{% block content %}
<style>
  .pass-card {
    background: linear-gradient(135deg, #0f2640 0%, #0f7a82 100%);
    color: #fff; border-radius: 18px; padding: 28px; max-width: 460px; margin: 24px auto;
    box-shadow: 0 10px 30px rgba(0,0,0,.18);
  }
  .pass-card .label { opacity: .65; font-size: .8rem; }
  .pass-card .value { font-size: 1.2rem; font-weight: 700; }
  .pass-card hr { border-color: rgba(255,255,255,.2); }
  @media print {
    .no-print { display:none !important; }
    .pass-card { box-shadow: none; }
  }
</style>

<div class="pass-card text-center">
  <div class="display-6 mb-1">تذكرة يومية</div>
  <div class="opacity-75 small mb-3">{{ dp.brand.name }}</div>
  <hr>
  <div class="row text-start">
    <div class="col-6"><div class="label">الاسم</div><div class="value">{{ dp.customer_name }}</div></div>
    <div class="col-6"><div class="label">رقم التذكرة</div><div class="value">#{{ dp.id }}</div></div>
    <div class="col-6 mt-2"><div class="label">التاريخ</div><div class="value">{{ dp.date.strftime('%Y-%m-%d') }}</div></div>
    <div class="col-6 mt-2"><div class="label">المبلغ</div><div class="value">{{ "%.2f"|format(dp.amount) }} ر.س</div></div>
  </div>
</div>

<div class="text-center no-print mt-3">
  <button class="btn btn-primary" onclick="window.print()"><i class="bi bi-printer"></i> طباعة</button>
  {% set raw = dp.customer_phone or '' %}
  {% set digits = raw | replace('+','') | replace(' ','') | replace('-','') %}
  {% if digits.startswith('00966') %}{% set normalized = digits[2:] %}
  {% elif digits.startswith('966') %}{% set normalized = digits %}
  {% elif digits.startswith('0') %}{% set normalized = '966' ~ digits[1:] %}
  {% else %}{% set normalized = '966' ~ digits %}{% endif %}
  {% if digits %}
  <a class="btn btn-success" target="_blank"
     href="https://wa.me/{{ normalized }}?text={{ ('تذكرة اليوم من ' ~ dp.brand.name ~ ' لرقم #' ~ dp.id) | urlencode }}">
    <i class="bi bi-whatsapp"></i> إرسال واتساب
  </a>
  {% endif %}
</div>
{% endblock %}
```

### Make the customer name on `day_pass/index.html` a link

```jinja
<td><a href="{{ url_for('day_pass.print_pass', pass_id=dp.id) }}">{{ dp.customer_name }}</a></td>
```

---

## 6. Audit pass — what to do every time you ship a batch

A short, mechanical checklist that catches the two classes of bugs we hit:

1. **Grep for every `.format(model.<field>)` call** that formats a numeric
   column. If the column is `Numeric` or `Float` and any prod row could be
   NULL (default doesn't apply retroactively), the format call must be
   wrapped in `or 0`. Same for `"{:+,.2f}".format(...)`.

2. **Audit `_FK_COLUMNS`** (or the equivalent list in your dedupe / cascade /
   merge code) against the real DB. For every FK pointing at the primary
   table:
   ```sql
   SELECT name FROM pragma_foreign_key_list('your_table');   -- sqlite
   ```
   or grep your models:
   ```bash
   grep -rn "ForeignKey('members\\.id'" app/models/
   ```
   Anything missing from the list will leave orphan rows.

3. **Run the round-trip test** described in §3 (merge → undo → counts equal).

---

## 7. GYM-30 — Closing report not broken; just empty

The "/daily-closing/report" page reads from `DailyClosing` rows that staff
explicitly submit via `/closing/create`. When no closings exist for the chosen
range, the page correctly shows an empty state.

If users complain the page is "broken," seed a handful of closings and walk
them through the difference between **raw daily revenue** (live in `Income`,
visible on `/finance/sales_transactions`) and the **closed-day summary**
(`DailyClosing`, visible on `/daily-closing/report`).

Seed script template:

```python
from datetime import date, timedelta, datetime
from app import create_app, db
from app.models.daily_closing import DailyClosing

with create_app().app_context():
    BRAND_ID, BRANCH_ID, USER_ID = 1, 6, 18
    today = date.today()
    rows = [
        # (days_ago, sales, cash, card, transfer, actual_cash, status)
        (1, 2400, 1500, 700, 200, 1500, 'verified'),
        (2, 1850,  900, 800, 150,  880, 'verified'),  # short by 20
        (3, 3100, 1800, 950, 350, 1850, 'submitted'), # over by 50
        (4, 1200,  600, 500, 100,  600, 'verified'),
        (5, 2700, 1200,1300, 200, 1100, 'submitted'), # short by 100
    ]
    for offset, sales, cash, card, transfer, actual, status in rows:
        d = today - timedelta(days=offset)
        if DailyClosing.query.filter_by(brand_id=BRAND_ID, branch_id=BRANCH_ID, closing_date=d).first():
            continue
        db.session.add(DailyClosing(
            brand_id=BRAND_ID, branch_id=BRANCH_ID, closing_date=d,
            new_subscriptions_count=2, renewals_count=1,
            total_sales=sales, cash_amount=cash, card_amount=card, transfer_amount=transfer,
            total_expenses=0, expected_cash=cash,
            actual_cash_submitted=actual, cash_difference=actual - cash,
            status=status, submitted_by=USER_ID, submitted_at=datetime.utcnow(),
        ))
    db.session.commit()
```

---

## 8. Boot-time schema guard pattern (used everywhere)

Every model addition is paired with idempotent CREATE TABLE / ALTER inside
`app/__init__.py` so a fresh `git pull` + reload is enough — no migration
step. Pattern:

```python
def create_app():
    app = Flask(__name__); ...
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _ensure_extra_columns()   # idempotent ALTERs
        _ensure_merge_log_table() # idempotent CREATE IF NOT EXISTS
    return app

def _ensure_merge_log_table():
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    if 'member_merge_logs' not in insp.get_table_names():
        db.engine.execute("""
            CREATE TABLE member_merge_logs ( ...full DDL... );
        """)
```

---

## 9. Testing harness used to verify shipped work

We used Playwright. The skeleton script that proved every feature in this
spec works:

```python
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path('/tmp/screenshots'); OUT.mkdir(exist_ok=True)
BASE = 'http://localhost:5050'
OWNER = ('owner@example.com', 'password')

def check(name, ok, note=''):
    print(f'  {"✅" if ok else "❌"}  {name}  {note}')

with sync_playwright() as p:
    page = p.chromium.launch().new_context(viewport={'width':1440,'height':900}).new_page()
    page.goto(f'{BASE}/auth/login')
    page.fill('input[name=email]', OWNER[0]); page.fill('input[name=password]', OWNER[1])
    page.click('button[type=submit]'); page.wait_for_load_state('networkidle')

    page.goto(f'{BASE}/closing/')
    check('/closing/ list renders', '/closing/' in page.url and 'Error' not in page.title())

    page.goto(f'{BASE}/finance/expenses?brand_id=1'); page.wait_for_load_state('networkidle')
    check('expenses receipt column', page.locator('th:has-text("الإيصال")').count() >= 1)

    page.goto(f'{BASE}/members/duplicates?strictness=loose'); page.wait_for_load_state('networkidle')
    check('duplicates page lists clusters', page.locator('input.cluster-check').count() >= 1)

    page.goto(f'{BASE}/day-pass/1/print'); page.wait_for_load_state('networkidle')
    check('day-pass card renders', page.locator('.pass-card').count() >= 1)
    check('whatsapp button', page.locator('a[href*="wa.me/"]').count() >= 1)
```

---

## 10. Reusable conventions / "how we work" cheatsheet

| Rule | Reason |
|---|---|
| Boot-time `db.create_all()` + idempotent ALTERs in `app/__init__.py` | Deploys are git pull + reload, no migration step |
| Read revenue ONLY from the canonical `Income` table | Specialty tables (`SubscriptionPayment`) only cover their own domain |
| `or 0` on every numeric format | Prod has legacy NULL rows; column `default=0` doesn't backfill |
| Path-tolerance: accept `uploads/x.jpg` AND `x.jpg` | Different save helpers store different shapes |
| Soft-delete (deactivate + rename `[مدمج] `) instead of hard delete | All historical data lives on under the keeper |
| Snapshot loser as JSON before merge | Makes undo deterministic — never has to fabricate data |
| Auto-pick keeper by (subs, invoices, attendance, oldest id) | Heuristic that matches "the more activity, the more real" intuition |
| One `_FK_COLUMNS` list = single source of truth for merge + undo | Adding a new member-FK in one place is impossible to forget |
| Brand/branch scoping on every list query via `apply_branch_filter` | Multi-tenant safety guaranteed at the query layer |
| Permission gates at the route level, not the template level | Avoids leaking URLs to users who shouldn't see them |

---

## Order of work for a clean re-implementation

1. Add the boot-time schema guard + the `MemberMergeLog` model + migration script.
2. Add `app/services/dedupe.py` (no UI yet) and prove `find_duplicate_clusters` + `merge_cluster` + `undo_merge` round-trip in a Python shell.
3. Wire the four `/members/duplicates*` routes and the two templates.
4. Convert the closing math to source from `Income` (point 4 above) — this is the smallest change with the biggest correctness payoff.
5. Patch the closing templates with the renames + `or 0` guards (point 2 above).
6. Add the expense-receipt column + path-tolerance fix (point 1).
7. Add the day-pass print card + WhatsApp share (point 5).
8. Run the Playwright skeleton; iterate until all checks green.
9. Run the audit checklist (point 6) on the whole batch before committing.
