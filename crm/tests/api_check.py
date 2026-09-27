"""API check of every CRM endpoint, including the review fixes, against a freshly
seeded demo database. Standard library only.

Usage (from the repo root, with the server running on a fresh demo DB):
    python crm/tests/api_check.py
"""
import json, os, sys, urllib.request, urllib.error
PORT = os.environ.get("CRM_PORT", "8090")
B = f"http://127.0.0.1:{PORT}"; O = {"Origin": f"http://127.0.0.1:{PORT}", "Content-Type": "application/json"}
fails = []
def call(method, path, body=None, headers=O, expect=None):
    req = urllib.request.Request(B + path, method=method, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        r = urllib.request.urlopen(req); code = r.status; raw = r.read()
    except urllib.error.HTTPError as e:
        code = e.code; raw = e.read()
    try: data = json.loads(raw) if raw else None
    except ValueError: data = raw.decode(errors="replace")
    ok = expect is None or code == expect
    print(f"{'ok ' if ok else 'FAIL'} {method:6s} {path:48s} {code}")
    if not ok: fails.append((method, path, code, raw[:200]))
    return data
# reads
for p in ["/api/dashboard", "/api/reports", "/api/search?q=to", "/api/contacts", "/api/companies", "/api/pipelines", "/api/opportunities", "/api/activities", "/api/tasks", "/api/saved-views"]:
    call("GET", p, expect=200)
pl = call("GET", "/api/pipelines")[0]; st = {s["name"]: s["id"] for s in pl["stages"]}
# company CRUD + rename propagation
co = call("POST", "/api/companies", {"name": "Test Co"}, expect=201)
ct = call("POST", "/api/contacts", {"first_name": "Ada", "last_name": "Test", "company_id": co["id"]}, expect=201)
op = call("POST", "/api/opportunities", {"name": "Test deal", "contact_id": ct["id"], "company_id": co["id"], "pipeline_id": pl["id"], "stage_id": st["New Lead"], "monetary_value": 100}, expect=201)
call("PUT", f"/api/companies/{co['id']}", {"name": "Renamed Co"}, expect=200)
print("   company rename reached opportunity:", call("GET", f"/api/opportunities/{op['id']}")["company_name"] == "Renamed Co")
call("PUT", f"/api/contacts/{ct['id']}", {"first_name": "Ava"}, expect=200)
print("   contact rename reached opportunity:", call("GET", f"/api/opportunities/{op['id']}")["contact_name"])
# stage/status coupling (the fix)
d0 = call("GET", "/api/dashboard")
o = call("PATCH", f"/api/opportunities/{op['id']}/stage", {"stage_id": st["Won"]}, expect=200); print("   drag to Won -> status:", o["status"])
d1 = call("GET", "/api/dashboard"); print("   won_count", d0["won_count"], "->", d1["won_count"], "| open value", d0["pipeline_value"], "->", d1["pipeline_value"])
o = call("PATCH", f"/api/opportunities/{op['id']}/stage", {"stage_id": st["Qualified"]}, expect=200); print("   drag back to Qualified -> status:", o["status"])
o = call("PUT", f"/api/opportunities/{op['id']}", {"stage_id": st["Lost"]}, expect=200); print("   edit stage to Lost -> status:", o["status"])
o = call("PUT", f"/api/opportunities/{op['id']}", {"monetary_value": 250}, expect=200); print("   edit value only -> status stays:", o["status"], o["monetary_value"])
# tasks / activities / views
t = call("POST", "/api/tasks", {"title": "T", "contact_id": ct["id"], "opportunity_id": op["id"], "due_date": "2026-10-01"}, expect=201)
call("PATCH", f"/api/tasks/{t['id']}/complete", expect=200); call("PUT", f"/api/tasks/{t['id']}", {"title": "T2"}, expect=200)
a = call("POST", "/api/activities", {"type": "call", "body": "hi", "contact_id": ct["id"]}, expect=201)
v = call("POST", "/api/saved-views", {"name": "V", "entity": "contacts", "filters": {"status": "active"}}, expect=201)
# pipelines & stages
np = call("POST", "/api/pipelines", {"name": "P2"}, expect=201)
np = call("POST", f"/api/pipelines/{np['id']}/stages", {"name": "S1"}, expect=201)
sid = np["stages"][0]["id"]
call("PUT", f"/api/pipelines/{np['id']}/stages/{sid}", {"name": "S1b"}, expect=200)
call("POST", f"/api/pipelines/{np['id']}/stages/reorder", [{"id": sid, "position": 0}], expect=200)
call("DELETE", f"/api/pipelines/{np['id']}/stages/{sid}", expect=204); call("DELETE", f"/api/pipelines/{np['id']}", expect=204)
call("DELETE", f"/api/pipelines/{pl['id']}", expect=409)
# deletes
for path in [f"/api/tasks/{t['id']}", f"/api/activities/{a['id']}", f"/api/saved-views/{v['id']}", f"/api/opportunities/{op['id']}", f"/api/contacts/{ct['id']}", f"/api/companies/{co['id']}"]:
    call("DELETE", path, expect=204)
# 404s and bad input
call("GET", "/api/contacts/nope", expect=404); call("POST", "/api/companies", {}, expect=422)
call("POST", "/api/contacts", {"first_name": "X", "company_id": "does-not-exist"}, expect=400)
call("POST", "/api/opportunities", {"name": "X", "pipeline_id": pl["id"], "stage_id": st["New Lead"], "contact_id": "ghost"}, expect=400)
# guards
call("POST", "/api/companies", {"name": "evil"}, headers={"Origin": "https://evil.example", "Content-Type": "application/json"}, expect=403)
call("GET", "/api/contacts", headers={"Host": "attacker.example"}, expect=400)
print("\nFAILURES:", fails or "none")
# rename propagation, contact and deal
co = call("POST", "/api/companies", {"name": "R Co"}, expect=201)
ct = call("POST", "/api/contacts", {"first_name": "Ada", "last_name": "Test"}, expect=201)
op = call("POST", "/api/opportunities", {"name": "Old deal", "contact_id": ct["id"], "pipeline_id": pl["id"], "stage_id": st["New Lead"]}, expect=201)
t = call("POST", "/api/tasks", {"title": "T", "contact_id": ct["id"], "opportunity_id": op["id"]}, expect=201)
a = call("POST", "/api/activities", {"type": "note", "contact_id": ct["id"], "opportunity_id": op["id"]}, expect=201)
call("PUT", f"/api/contacts/{ct['id']}", {"first_name": "Ava"}, expect=200)
call("PUT", f"/api/opportunities/{op['id']}", {"name": "New deal"}, expect=200)
o = call("GET", f"/api/opportunities/{op['id']}"); tk = call("GET", f"/api/tasks/{t['id']}")
acts = [x for x in call("GET", f"/api/activities?opportunity_id={op['id']}") if x["id"] == a["id"]][0]
print("   deal contact_name:", o["contact_name"], "| task:", tk["contact_name"], "/", tk["opportunity_name"], "| activity:", acts["contact_name"], "/", acts["opportunity_name"])
for path in [f"/api/tasks/{t['id']}", f"/api/activities/{a['id']}", f"/api/opportunities/{op['id']}", f"/api/contacts/{ct['id']}", f"/api/companies/{co['id']}"]:
    call("DELETE", path, expect=204)
print("FAILURES (final):", fails or "none")
# unlink semantics: blank = clear, absent = keep
co = call("POST", "/api/companies", {"name": "U Co"}, expect=201)
ct = call("POST", "/api/contacts", {"first_name": "Uma", "company_id": co["id"]}, expect=201)
c1 = call("PUT", f"/api/contacts/{ct['id']}", {"first_name": "Uma"}, expect=200); print("   absent company_id keeps link:", c1["company_id"] == co["id"], c1["company_name"])
c2 = call("PUT", f"/api/contacts/{ct['id']}", {"company_id": ""}, expect=200); print("   blank company_id unlinks:", c2["company_id"], c2["company_name"])
op = call("POST", "/api/opportunities", {"name": "U deal", "contact_id": ct["id"], "company_id": co["id"], "pipeline_id": pl["id"], "stage_id": st["New Lead"], "close_date": "2026-12-01"}, expect=201)
o = call("PUT", f"/api/opportunities/{op['id']}", {"contact_id": "", "close_date": ""}, expect=200); print("   opp unlink contact/clear date:", o["contact_id"], o["contact_name"], o["close_date"], "| company kept:", o["company_id"] == co["id"])
t = call("POST", "/api/tasks", {"title": "U task", "due_date": "2026-10-10", "contact_id": ct["id"]}, expect=201)
t2 = call("PUT", f"/api/tasks/{t['id']}", {"due_date": ""}, expect=200); print("   task clear due date:", t2["due_date"], "| contact kept:", t2["contact_id"] == ct["id"])
for path in [f"/api/tasks/{t['id']}", f"/api/opportunities/{op['id']}", f"/api/contacts/{ct['id']}", f"/api/companies/{co['id']}"]:
    call("DELETE", path, expect=204)
print("FAILURES (unlink):", fails or "none")
# closed value sets: markup or unknown values in status/type fields are refused, not stored
pl = call("GET", "/api/pipelines")[0]; st = {x["name"]: x["id"] for x in pl["stages"]}
call("POST", "/api/opportunities", {"name": "X", "pipeline_id": pl["id"], "stage_id": st["New Lead"], "status": "<img src=x onerror=alert(1)>"}, expect=422)
call("POST", "/api/activities", {"type": "<script>", "body": "x"}, expect=422)
call("POST", "/api/saved-views", {"name": "V", "entity": "nonsense", "filters": {}}, expect=422)
ok = call("POST", "/api/opportunities", {"name": "Status ok", "pipeline_id": pl["id"], "stage_id": st["New Lead"], "status": "won"}, expect=201)
call("DELETE", f"/api/opportunities/{ok['id']}", expect=204)
# deleting a record clears its name from the records that pointed at it
co = call("POST", "/api/companies", {"name": "Gone Co"}, expect=201)
ct = call("POST", "/api/contacts", {"first_name": "Gone", "company_id": co["id"]}, expect=201)
op = call("POST", "/api/opportunities", {"name": "Orphan", "contact_id": ct["id"], "company_id": co["id"], "pipeline_id": pl["id"], "stage_id": st["New Lead"]}, expect=201)
tk = call("POST", "/api/tasks", {"title": "Orphan task", "contact_id": ct["id"], "opportunity_id": op["id"]}, expect=201)
call("DELETE", f"/api/contacts/{ct['id']}", expect=204); call("DELETE", f"/api/companies/{co['id']}", expect=204)
o = call("GET", f"/api/opportunities/{op['id']}")
if o["contact_name"] or o["company_name"]: fails.append(("stale names on deal", o["contact_name"], o["company_name"]))
call("DELETE", f"/api/opportunities/{op['id']}", expect=204)
t = call("GET", f"/api/tasks/{tk['id']}")
if t["opportunity_name"] or t["contact_name"]: fails.append(("stale names on task", t["opportunity_name"], t["contact_name"]))
call("DELETE", f"/api/tasks/{tk['id']}", expect=204)
print("FAILURES (validation):", fails or "none")
sys.exit(1 if fails else 0)
