"""Seed abandoned leads for the abandon-tab filter probe, and restore them afterwards.

Usage:
    .venv/Scripts/python.exe .workbuddy-seed-abandon.py seed
    .venv/Scripts/python.exe .workbuddy-seed-abandon.py restore
"""
import json
import sys
import urllib.error
import urllib.request

import pymysql

DB = dict(host="127.0.0.1", port=3306, user="root", password="051019", database="xuanshiai")
LEADS = [1, 2]


def api(method, path, body=None, token=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login() -> str:
    status, body = api("POST", "admin/matchmaker/auth/login", {"username": "localtest", "password": "Localtest@123"})
    if status != 200:
        raise SystemExit(f"login failed: {status} {body}")
    return body["access_token"]


def show(label: str) -> None:
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, source, status, matchmaker_id FROM customer_lead ORDER BY id")
            for row in cur.fetchall():
                print(f"  {label} lead", row)
            cur.execute(
                "SELECT id, lead_id, abandoned_at, restored_at FROM customer_lead_abandonment ORDER BY id"
            )
            print(f"  {label} abandonments:", cur.fetchall())
    finally:
        conn.close()


mode = sys.argv[1] if len(sys.argv) > 1 else "status"
print("=== before ===")
show(mode)

if mode == "seed":
    token = login()
    for lead_id in LEADS:
        status, body = api("POST", f"admin/customer-leads/{lead_id}/abandon", {"reason": "筛选联调临时弃海"}, token)
        print(f"abandon lead {lead_id}: HTTP {status}", "" if status < 300 else body)
elif mode == "restore":
    token = login()
    for lead_id in LEADS:
        status, body = api("POST", f"admin/customer-leads/{lead_id}/restore", {"reason": "筛选联调结束还原"}, token)
        print(f"restore lead {lead_id}: HTTP {status}", "" if status < 300 else body)

print("=== after ===")
show(mode)
