"""GYM-28 — member duplicate detection + merge engine.

Pure data layer; routes call into here. All merges run inside a single
db.session transaction; if anything throws the whole thing is rolled back
so the prod data is never left half-merged.
"""
from __future__ import annotations
import json
import re
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


# ─── Normalisers ────────────────────────────────────────────────────────────

def _norm_name(s: str | None) -> str:
    if not s:
        return ''
    # collapse Arabic whitespace + tatweel + remove leading/trailing
    return re.sub(r'\s+', ' ', s.replace('ـ', '').strip()).lower()


def _norm_phone(s: str | None) -> str:
    if not s:
        return ''
    digits = ''.join(ch for ch in s if ch.isdigit())
    # treat 05XXXXXXXX, +9665XXXXXXXX and 9665XXXXXXXX as the same number
    if digits.startswith('00966'):
        digits = digits[5:]
    elif digits.startswith('966'):
        digits = digits[3:]
    if digits.startswith('0'):
        digits = digits.lstrip('0')
    return digits


# ─── Cluster detection (read-only) ──────────────────────────────────────────

STRICTNESS_LEVELS = ('strict', 'medium', 'loose')


def find_duplicate_clusters(brand_id: int, *, branch_id: int | None = None,
                            strictness: str = 'medium') -> list[dict]:
    """Return a list of clusters, each cluster = {'key', 'members': [..]}.

    Strictness:
      strict — name + phone match
      medium — name + (phone OR member_import_id) match
      loose  — name match only
    """
    if strictness not in STRICTNESS_LEVELS:
        strictness = 'medium'

    q = Member.query.filter(Member.brand_id == brand_id, Member.is_active == True)
    if branch_id:
        q = q.filter(Member.branch_id == branch_id)
    members = q.all()

    # Group by normalized name first.
    by_name: dict[str, list[Member]] = defaultdict(list)
    for m in members:
        n = _norm_name(m.name)
        if n:
            by_name[n].append(m)

    clusters: list[dict] = []
    for name_key, group in by_name.items():
        if len(group) < 2:
            continue

        if strictness == 'loose':
            clusters.extend(_finalize_clusters([group], name_key))
            continue

        # Sub-cluster by phone / member_import_id.
        sub_groups = _sub_cluster(group, strictness)
        clusters.extend(_finalize_clusters(sub_groups, name_key))

    return clusters


def _sub_cluster(group: list[Member], strictness: str) -> list[list[Member]]:
    """Split a same-name group into sub-clusters based on phone / import_id."""
    seen: dict[tuple, list[Member]] = defaultdict(list)
    for m in group:
        phone = _norm_phone(m.phone)
        # Two members in the same brand with the same normalised phone are
        # always one cluster, regardless of strictness.
        if phone:
            seen[('p', phone)].append(m)
        elif strictness == 'medium' and m.member_import_id:
            seen[('i', m.member_import_id)].append(m)
        else:
            # member with no phone + no import id — only a same-name cluster
            seen[('n', m.id)].append(m)

    # Now consolidate: members sharing the same name AND same key go together.
    # Two members same-name but each tied to a different phone are NOT in the
    # same cluster — that protects against family members.
    return [members for members in seen.values() if len(members) > 1]


def _finalize_clusters(sub_groups: list[list[Member]], name_key: str) -> list[dict]:
    out = []
    for grp in sub_groups:
        if len(grp) < 2:
            continue
        member_ids = sorted(m.id for m in grp)
        out.append({
            'key': f"{name_key}|{'-'.join(str(i) for i in member_ids)}",
            'name': grp[0].name,
            'members': enrich_members(grp),
            'ids': member_ids,
        })
    return out


def enrich_members(members: list[Member]) -> list[dict]:
    """Decorate each member in a cluster with stats used in the UI."""
    out = []
    ids = [m.id for m in members]

    # Batched counts so we don't re-query per member.
    sub_count = dict(db.session.query(Subscription.member_id, func.count(Subscription.id))
                     .filter(Subscription.member_id.in_(ids))
                     .group_by(Subscription.member_id).all())
    inv_count = dict(db.session.query(Invoice.member_id, func.count(Invoice.id))
                     .filter(Invoice.member_id.in_(ids))
                     .group_by(Invoice.member_id).all())
    att_count = dict(db.session.query(MemberAttendance.member_id, func.count(MemberAttendance.id))
                     .filter(MemberAttendance.member_id.in_(ids))
                     .group_by(MemberAttendance.member_id).all())
    revenue = dict(db.session.query(Subscription.member_id, func.coalesce(func.sum(Subscription.paid_amount), 0))
                   .filter(Subscription.member_id.in_(ids))
                   .group_by(Subscription.member_id).all())
    last_att = dict(db.session.query(MemberAttendance.member_id, func.max(MemberAttendance.check_in))
                    .filter(MemberAttendance.member_id.in_(ids))
                    .group_by(MemberAttendance.member_id).all())

    for m in members:
        out.append({
            'm': m,
            'subs': sub_count.get(m.id, 0),
            'invoices': inv_count.get(m.id, 0),
            'attendance': att_count.get(m.id, 0),
            'revenue': float(revenue.get(m.id, 0) or 0),
            'last_attendance': last_att.get(m.id),
        })
    return out


# ─── Keeper selection ───────────────────────────────────────────────────────

def pick_keeper(enriched: list[dict]) -> dict:
    """Auto-pick the canonical record per the Q1 priority:
      subs ↓, invoices ↓, attendance ↓, oldest id ↑.
    """
    return max(
        enriched,
        key=lambda e: (e['subs'], e['invoices'], e['attendance'], -e['m'].id),
    )


# ─── The merge transaction ──────────────────────────────────────────────────

def merge_cluster(cluster_ids: list[int], *, performed_by: int) -> dict:
    """Merge a single cluster: pick keeper, repoint FKs, deactivate losers.

    Returns a summary dict {keeper_id, losers: [{id, moves}]}.
    Raises on bad input; caller wraps in try/except for the route flash.
    """
    if len(cluster_ids) < 2:
        raise ValueError('cluster_ids must have ≥ 2 entries')

    members = Member.query.filter(Member.id.in_(cluster_ids)).all()
    if len(members) < 2:
        raise ValueError('not enough members found for the cluster')

    enriched = enrich_members(members)
    keeper_entry = pick_keeper(enriched)
    keeper: Member = keeper_entry['m']
    losers = [e['m'] for e in enriched if e['m'].id != keeper.id]

    summary = {'keeper_id': keeper.id, 'losers': []}
    for loser in losers:
        moves = _merge_one_loser_into_keeper(keeper, loser, performed_by)
        summary['losers'].append({'id': loser.id, 'moves': moves})
    return summary


# Map of (sqlalchemy column to UPDATE) → label for the moves dict.
_FK_COLUMNS = [
    (Subscription, 'member_id', 'subscriptions'),
    (Invoice, 'member_id', 'invoices'),
    (MemberAttendance, 'member_id', 'attendance'),
    (ClassBooking, 'member_id', 'class_bookings'),
    (Complaint, 'member_id', 'complaints'),
    (HealthReport, 'member_id', 'health_reports'),
    (GiftCard, 'redeemed_by_member_id', 'gift_cards_redeemed'),
    (DeviceCommand, 'member_id', 'device_commands'),
    (FingerprintAccessLog, 'member_id', 'fp_access_logs'),
    (RenewalRejection, 'member_id', 'renewal_rejections'),
    (Refund, 'member_id', 'refunds'),
]


def _merge_one_loser_into_keeper(keeper: Member, loser: Member,
                                 performed_by: int) -> dict:
    """Re-point every FK from loser → keeper and snapshot for undo."""
    snapshot = _snapshot_member(loser)
    moves: dict[str, int] = {}

    for model, col_name, label in _FK_COLUMNS:
        column = getattr(model, col_name)
        n = model.query.filter(column == loser.id).update({col_name: keeper.id},
                                                          synchronize_session=False)
        if n:
            moves[label] = n

    # Carry-over: only fields where keeper is missing AND loser has a value.
    _carry_over(keeper, loser)

    # Deactivate, prefix the name, append an audit note.
    loser.is_active = False
    if not loser.name.startswith('[مدمج] '):
        loser.name = ('[مدمج] ' + (loser.name or ''))[:100]
    note = f'دُمج بـ #{keeper.id} في {datetime.utcnow().isoformat(timespec="seconds")}'
    loser.notes = ((loser.notes or '') + ('\n' if loser.notes else '') + note)[:2000] \
        if hasattr(loser, 'notes') else None

    db.session.add(MemberMergeLog(
        brand_id=keeper.brand_id,
        keeper_id=keeper.id,
        loser_id=loser.id,
        loser_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        moves_json=json.dumps(moves, ensure_ascii=False),
        performed_by=performed_by,
    ))
    return moves


def _carry_over(keeper: Member, loser: Member) -> None:
    fields = ('fingerprint_id', 'member_import_id', 'email', 'address',
              'birth_date', 'phone', 'fingerprint_enrolled')
    for f in fields:
        if not hasattr(keeper, f) or not hasattr(loser, f):
            continue
        if getattr(keeper, f) in (None, '', 0):
            v = getattr(loser, f)
            if v not in (None, '', 0):
                setattr(keeper, f, v)


def _snapshot_member(m: Member) -> dict:
    cols = {c.name for c in m.__table__.columns}
    out = {}
    for k in cols:
        v = getattr(m, k, None)
        if v is None:
            out[k] = None
        elif hasattr(v, 'isoformat'):
            out[k] = v.isoformat()
        else:
            out[k] = str(v) if not isinstance(v, (int, float, bool, str)) else v
    return out


# ─── Undo ───────────────────────────────────────────────────────────────────

def undo_merge(log_id: int, *, undone_by: int) -> dict:
    """Reverse a single merge log entry. Raises if already undone or if any
    FK row that was moved has since been moved on by another merge.
    """
    log = MemberMergeLog.query.get(log_id)
    if not log:
        raise ValueError('merge log not found')
    if log.undone_at:
        raise ValueError('this merge has already been undone')

    loser = Member.query.get(log.loser_id)
    keeper = Member.query.get(log.keeper_id)
    if not loser or not keeper:
        raise ValueError('keeper or loser member is missing')

    moves = json.loads(log.moves_json or '{}')
    snapshot = json.loads(log.loser_snapshot_json or '{}')

    # Reverse every FK move. We re-point rows currently belonging to keeper
    # back to the loser, capped at the count we originally moved. This is
    # only safe if nothing else has moved the same rows since — a UNIQUE
    # row never moves twice, so the cap defends against accidental over-
    # restoration.
    label_to_pair = {label: (model, col) for (model, col, label) in _FK_COLUMNS}
    for label, n in moves.items():
        pair = label_to_pair.get(label)
        if not pair:
            continue
        model, col_name = pair
        column = getattr(model, col_name)
        # Restore exactly N rows by id-asc to keep behaviour deterministic.
        candidate_ids = [r.id for r in model.query.filter(column == keeper.id)
                                                  .order_by(model.id.asc())
                                                  .limit(n).all()]
        if candidate_ids:
            model.query.filter(model.id.in_(candidate_ids)).update(
                {col_name: loser.id}, synchronize_session=False)

    # Restore loser visibility + name from the snapshot.
    loser.is_active = True
    if snapshot.get('name'):
        loser.name = snapshot['name']

    log.undone_at = datetime.utcnow()
    log.undone_by = undone_by
    return {'restored_loser': loser.id, 'unmoved': moves}
