from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def normalize_text(value: str | None) -> str:
    value = (value or '').translate(PERSIAN_DIGITS)
    value = value.replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    value = re.sub(r'\s+', ' ', value).strip().lower()
    return value


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r'\D+', '', (value or '').translate(PERSIAN_DIGITS))
    if digits.startswith('98') and len(digits) >= 12:
        digits = '0' + digits[2:]
    return digits


@dataclass
class RawRecord:
    insurer_name: str
    provider_name: str
    provider_type: str
    province: str = ''
    city: str = ''
    district: str = ''
    address: str = ''
    phone: str = ''
    services: tuple[str, ...] = ()
    source_name: str = ''
    source_url: str = ''
    source_type: str = 'official'
    source_record_key: str = ''
    evidence_text: str = ''


class SourceAdapter(Protocol):
    name: str

    def collect(self) -> Iterable[RawRecord]: ...


class DrLinqStore:
    def __init__(self, db_path: str | Path, schema_path: str | Path | None = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        if schema_path:
            self.conn.executescript(Path(schema_path).read_text(encoding='utf-8'))

    def close(self):
        self.conn.close()

    def _one_id(self, sql: str, params: tuple) -> int:
        row = self.conn.execute(sql, params).fetchone()
        if not row:
            raise RuntimeError('Expected row was not created')
        return int(row['id'])

    def upsert_insurer(self, name: str) -> int:
        norm = normalize_text(name)
        slug = hashlib.sha1(norm.encode()).hexdigest()[:16]
        self.conn.execute(
            'INSERT INTO insurers(slug,name,normalized_name) VALUES(?,?,?) '
            'ON CONFLICT(slug) DO UPDATE SET name=excluded.name, normalized_name=excluded.normalized_name, updated_at=CURRENT_TIMESTAMP',
            (slug, name.strip(), norm),
        )
        return self._one_id('SELECT id FROM insurers WHERE slug=?', (slug,))

    def upsert_source(self, r: RawRecord, insurer_id: int) -> int:
        self.conn.execute(
            'INSERT INTO sources(source_type,name,url,insurer_id,authority_rank,last_checked_at) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP) '
            'ON CONFLICT(url) DO UPDATE SET name=excluded.name, source_type=excluded.source_type, insurer_id=excluded.insurer_id, last_checked_at=CURRENT_TIMESTAMP',
            (r.source_type or 'official', r.source_name or r.insurer_name, r.source_url, insurer_id, 100 if r.source_type == 'official' else 60),
        )
        return self._one_id('SELECT id FROM sources WHERE url=?', (r.source_url,))

    def store_raw(self, r: RawRecord, source_id: int):
        payload = json.dumps(asdict(r), ensure_ascii=False, sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        self.conn.execute(
            'INSERT OR IGNORE INTO raw_records(source_id,source_record_key,payload_json,payload_hash) VALUES(?,?,?,?)',
            (source_id, r.source_record_key or None, payload, h),
        )

    def upsert_provider(self, r: RawRecord) -> int:
        norm_name = normalize_text(r.provider_name)
        phone = normalize_phone(r.phone)
        row = self.conn.execute(
            'SELECT id FROM providers WHERE normalized_name=? AND provider_type=? AND (phone=? OR ?="") ORDER BY id LIMIT 1',
            (norm_name, r.provider_type, phone, phone),
        ).fetchone()
        if row:
            pid = int(row['id'])
            self.conn.execute('UPDATE providers SET name=?, phone=COALESCE(NULLIF(?,""),phone), updated_at=CURRENT_TIMESTAMP WHERE id=?', (r.provider_name.strip(), phone, pid))
            return pid
        cur = self.conn.execute(
            'INSERT INTO providers(provider_type,name,normalized_name,phone) VALUES(?,?,?,?)',
            (r.provider_type or 'unknown', r.provider_name.strip(), norm_name, phone),
        )
        return int(cur.lastrowid)

    def upsert_location(self, r: RawRecord) -> int:
        norm_addr = normalize_text(r.address)
        phone = normalize_phone(r.phone)
        row = self.conn.execute(
            'SELECT id FROM locations WHERE province=? AND city=? AND district=? AND normalized_address=? ORDER BY id LIMIT 1',
            (r.province.strip(), r.city.strip(), r.district.strip(), norm_addr),
        ).fetchone()
        if row:
            return int(row['id'])
        cur = self.conn.execute(
            'INSERT INTO locations(province,city,district,address,normalized_address,phone) VALUES(?,?,?,?,?,?)',
            (r.province.strip(), r.city.strip(), r.district.strip(), r.address.strip(), norm_addr, phone),
        )
        return int(cur.lastrowid)

    def upsert_service(self, service_name: str) -> int:
        norm = normalize_text(service_name)
        slug = hashlib.sha1(norm.encode()).hexdigest()[:16]
        self.conn.execute(
            'INSERT INTO services(slug,name,normalized_name) VALUES(?,?,?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name, normalized_name=excluded.normalized_name',
            (slug, service_name.strip(), norm),
        )
        return self._one_id('SELECT id FROM services WHERE slug=?', (slug,))

    def ingest_record(self, r: RawRecord) -> None:
        if not r.insurer_name or not r.provider_name or not r.source_url:
            raise ValueError('insurer_name, provider_name and source_url are required')
        insurer_id = self.upsert_insurer(r.insurer_name)
        source_id = self.upsert_source(r, insurer_id)
        self.store_raw(r, source_id)
        provider_id = self.upsert_provider(r)
        location_id = self.upsert_location(r)
        self.conn.execute('INSERT OR IGNORE INTO provider_locations(provider_id,location_id,is_primary) VALUES(?,?,1)', (provider_id, location_id))
        for service in r.services:
            sid = self.upsert_service(service)
            self.conn.execute('INSERT OR IGNORE INTO provider_services(provider_id,service_id,confidence,source_id) VALUES(?,?,?,?)', (provider_id, sid, 'source_claimed', source_id))
        self.conn.execute(
            'INSERT INTO contracts(provider_id,location_id,insurer_id,status,confidence,source_id,source_record_key,last_seen_at,last_verified_at) '
            'VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) '
            'ON CONFLICT(provider_id,location_id,insurer_id,source_id,source_record_key) DO UPDATE SET status=excluded.status, confidence=excluded.confidence, last_seen_at=CURRENT_TIMESTAMP, last_verified_at=CURRENT_TIMESTAMP',
            (provider_id, location_id, insurer_id, 'active', 'official' if r.source_type == 'official' else 'secondary', source_id, r.source_record_key or ''),
        )
        self.conn.commit()


def ingest(adapter: SourceAdapter, db_path: str | Path, schema_path: str | Path) -> dict[str, int | str]:
    store = DrLinqStore(db_path, schema_path)
    total = ok = rejected = 0
    try:
        for record in adapter.collect():
            total += 1
            try:
                store.ingest_record(record)
                ok += 1
            except Exception:
                rejected += 1
        return {'adapter': adapter.name, 'fetched': total, 'accepted': ok, 'rejected': rejected}
    finally:
        store.close()
