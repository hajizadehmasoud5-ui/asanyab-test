from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify

VERSION = "0.1.0"
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def create_drlinq_referral_short_blueprint(data_root: str | Path) -> Blueprint:
    bp = Blueprint("drlinq_referral_short", __name__, url_prefix="/alanoffer")
    root = Path(data_root) / "alanoffer"
    root.mkdir(parents=True, exist_ok=True)
    db = root / "alanoffer.db"

    def con():
        c = sqlite3.connect(str(db), timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def make_code(seed: str, length: int = 6) -> str:
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        n = int.from_bytes(digest[:8], "big")
        out = []
        for _ in range(length):
            n, r = divmod(n, len(ALPHABET))
            out.append(ALPHABET[r])
        return "".join(out)

    def init():
        with con() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS drlinq_referral_shortlinks(
                    code TEXT PRIMARY KEY,
                    specialist_id TEXT NOT NULL UNIQUE,
                    slug TEXT NOT NULL UNIQUE
                )
                """
            )
            rows = c.execute(
                "SELECT id,slug FROM drlinq_referral_specialists WHERE active=1"
            ).fetchall()
            for row in rows:
                if c.execute(
                    "SELECT 1 FROM drlinq_referral_shortlinks WHERE specialist_id=?",
                    (row["id"],),
                ).fetchone():
                    continue
                code = make_code(row["id"])
                suffix = 0
                while c.execute(
                    "SELECT 1 FROM drlinq_referral_shortlinks WHERE code=?",
                    (code,),
                ).fetchone():
                    suffix += 1
                    code = make_code(f"{row['id']}:{suffix}")
                c.execute(
                    "INSERT INTO drlinq_referral_shortlinks(code,specialist_id,slug) VALUES(?,?,?)",
                    (code, row["id"], row["slug"]),
                )

    init()

    def ensure_slug(slug: str):
        slug = str(slug or "").strip()[:80]
        with con() as c:
            row = c.execute(
                """SELECT s.id,s.slug FROM drlinq_referral_specialists s
                   WHERE s.slug=? AND s.active=1""",
                (slug,),
            ).fetchone()
            if not row:
                return None
            link = c.execute(
                "SELECT code,slug FROM drlinq_referral_shortlinks WHERE specialist_id=?",
                (row["id"],),
            ).fetchone()
            if link:
                if link["slug"] != row["slug"]:
                    c.execute(
                        "UPDATE drlinq_referral_shortlinks SET slug=? WHERE specialist_id=?",
                        (row["slug"], row["id"]),
                    )
                return {"code": link["code"], "slug": row["slug"]}
            code = make_code(row["id"])
            suffix = 0
            while c.execute(
                "SELECT 1 FROM drlinq_referral_shortlinks WHERE code=?",
                (code,),
            ).fetchone():
                suffix += 1
                code = make_code(f"{row['id']}:{suffix}")
            c.execute(
                "INSERT INTO drlinq_referral_shortlinks(code,specialist_id,slug) VALUES(?,?,?)",
                (code, row["id"], row["slug"]),
            )
            return {"code": code, "slug": row["slug"]}

    @bp.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    @bp.get("/api/referral/short/by-slug/<path:slug>")
    def by_slug(slug):
        item = ensure_slug(slug)
        if not item:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True, **item)

    @bp.get("/api/referral/short/<code>")
    def resolve(code):
        code = str(code or "").strip().upper()[:12]
        with con() as c:
            row = c.execute(
                """SELECT l.slug FROM drlinq_referral_shortlinks l
                   JOIN drlinq_referral_specialists s ON s.id=l.specialist_id
                   WHERE l.code=? AND s.active=1""",
                (code,),
            ).fetchone()
        if not row:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True, code=code, slug=row["slug"])

    return bp
