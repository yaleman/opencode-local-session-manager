import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, url_for

DB_PATH = Path("/Users/yaleman/.local/share/opencode/opencode.db")

app = Flask(__name__)


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def ts_to_iso(ms):
    if ms is None:
        return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def pretty_json(data):
    try:
        return json.dumps(json.loads(data), indent=2, sort_keys=True)
    except Exception:
        return data


def render_part(raw):
    try:
        data = json.loads(raw)
    except Exception:
        return {"kind": "raw", "text": raw}

    ptype = data.get("type", "")

    if ptype == "text":
        text = data.get("text", "")
        text = re.sub(r"<personal-data>.*?</personal-data>", "[redacted]", text, flags=re.DOTALL)
        return {"kind": "text", "text": text}

    if ptype == "tool":
        name = data.get("name", "tool")
        input_text = json.dumps(data.get("input", {}), indent=2) if "input" in data else ""
        return {"kind": "tool", "name": name, "input": input_text, "raw": json.dumps(data, indent=2)}

    if ptype == "step-start" or ptype == "step-finish":
        return {"kind": "step", "name": ptype, "raw": json.dumps(data, indent=2)}

    if ptype == "file" or ptype == "patch":
        return {"kind": "file", "name": ptype, "raw": json.dumps(data, indent=2)}

    return {"kind": "raw", "text": json.dumps(data, indent=2)}


def session_to_view(row):
    d = dict(row)
    d["created"] = ts_to_iso(d.get("time_created"))
    d["archived_at"] = ts_to_iso(d.get("time_archived"))
    return d


@app.route("/")
def index():
    db = get_db()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 50
    offset = (page - 1) * per_page

    search = request.args.get("q", "").strip()
    project_filter = request.args.get("project", "").strip()
    archived_filter = request.args.get("archived", "all")

    base_where = []
    params = []
    if search:
        base_where.append("s.title LIKE ?")
        params.append(f"%{search}%")
    if project_filter:
        base_where.append("s.project_id = ?")
        params.append(project_filter)
    if archived_filter == "active":
        base_where.append("s.time_archived IS NULL")
    elif archived_filter == "archived":
        base_where.append("s.time_archived IS NOT NULL")
    where_clause = f"WHERE {' AND '.join(base_where)}" if base_where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM session s {where_clause}", params
    ).fetchone()[0]

    sessions = db.execute(
        f"""SELECT s.id, s.title, s.directory, s.project_id, s.time_created, s.time_updated,
                   s.time_archived, s.parent_id, s.cost, s.tokens_input, s.tokens_output,
                   COALESCE(NULLIF(p.name, ''), p.worktree, p.id) as project_name
            FROM session s
            LEFT JOIN project p ON p.id = s.project_id
            {where_clause}
            ORDER BY s.time_updated DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    projects = db.execute(
        """SELECT id, COALESCE(NULLIF(name, ''), worktree, id) as display
           FROM project ORDER BY time_updated DESC LIMIT 200"""
    ).fetchall()

    total_pages = max((total + per_page - 1) // per_page, 1)

    archived_counts = {
        "active": db.execute("SELECT COUNT(*) FROM session WHERE time_archived IS NULL").fetchone()[0],
        "archived": db.execute("SELECT COUNT(*) FROM session WHERE time_archived IS NOT NULL").fetchone()[0],
    }

    return render_template(
        "index.html",
        sessions=sessions,
        projects=projects,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        search=search,
        project_filter=project_filter,
        archived_filter=archived_filter,
        archived_counts=archived_counts,
    )


@app.route("/session/<session_id>/unarchive", methods=["POST"])
def unarchive_session(session_id):
    db = get_db()
    db.execute("UPDATE session SET time_archived = NULL WHERE id = ?", (session_id,))
    db.commit()
    return redirect(url_for("session_detail", session_id=session_id))



@app.route("/session/<session_id>")
def session_detail(session_id):
    db = get_db()
    session = db.execute(
        """SELECT s.*, COALESCE(NULLIF(p.name, ''), p.worktree, p.id) as project_name
           FROM session s
           LEFT JOIN project p ON p.id = s.project_id
           WHERE s.id = ?""",
        (session_id,),
    ).fetchone()
    if not session:
        abort(404)

    messages = db.execute(
        """SELECT id, time_created, data
           FROM message
           WHERE session_id = ?
           ORDER BY time_created ASC, id ASC""",
        (session_id,),
    ).fetchall()

    parts = db.execute(
        """SELECT id, message_id, time_created, data
           FROM part
           WHERE session_id = ?
           ORDER BY time_created ASC, id ASC""",
        (session_id,),
    ).fetchall()

    parts_by_message = {}
    for part in parts:
        parts_by_message.setdefault(part["message_id"], []).append(part)

    message_list = []
    for msg in messages:
        role = ""
        try:
            role = (json.loads(msg["data"]) or {}).get("role", "")
        except Exception:
            pass

        rendered_parts = [render_part(p["data"]) for p in parts_by_message.get(msg["id"], [])]
        message_list.append(
            {
                "id": msg["id"],
                "role": role,
                "time": ts_to_iso(msg["time_created"]),
                "parts": rendered_parts,
            }
        )

    return render_template(
        "session.html",
        session=session_to_view(session),
        messages=message_list,
    )


@app.template_filter("ts")
def _ts_filter(value):
    return ts_to_iso(value)


if __name__ == "__main__":
    app.run(debug=True, port=5173)
