"""Browser check of the CRM UI against a freshly seeded demo database.

Every request to a host other than localhost is blocked, so it also proves the page
works offline. Needs: pip install playwright && playwright install chromium

Usage (from the repo root, with the server running on a fresh demo DB):
    python crm/tests/ui_check.py
"""
import json, os, re, sys, urllib.request
from playwright.sync_api import sync_playwright

PORT = os.environ.get("CRM_PORT", "8090")
B = f"http://localhost:{PORT}"
issues, external, cur, results, dialogs = [], [], ["load"], [], []
answer = [""]


def api(path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}" + path).read())


def put(path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}" + path, method="PUT", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT}"})
    return json.loads(urllib.request.urlopen(req).read())


def deal(name):
    return [d for d in api("/api/opportunities?limit=999") if d["name"] == name][0]


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})

    def route(r):
        if re.match(r"https?://(localhost|127\.0\.0\.1)", r.request.url):
            r.continue_()
        else:
            external.append(r.request.url)
            r.abort()
    ctx.route("**/*", route)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: issues.append(f"PAGEERROR [{cur[0]}] {e.message}"))
    pg.on("console", lambda m: issues.append(f"CONSOLE [{cur[0]}] {m.text[:150]}") if m.type == "error" else None)
    pg.on("response", lambda r: issues.append(f"HTTP {r.status} {r.request.method} {r.url} [{cur[0]}]") if r.status >= 400 else None)

    def on_dialog(d):
        dialogs.append((d.type, d.message))
        d.accept(answer[0]) if d.type == "prompt" else d.accept()
    pg.on("dialog", on_dialog)

    def step(name, fn):
        cur[0] = name
        try:
            fn()
            results.append(("ok  ", name))
        except Exception as e:
            results.append(("FAIL", f"{name}: {((str(e) or type(e).__name__).splitlines() or [type(e).__name__])[0][:170]}"))
            pg.keyboard.press("Escape")

    def side(label):
        pg.locator("aside").get_by_text(label, exact=True).first.click()
        pg.wait_for_timeout(500)

    def open_row(text):
        row = pg.locator("tr.row", has_text=text).first
        row.hover()
        row.locator(".open").click()
        pg.wait_for_timeout(400)

    pg.goto(B)
    pg.wait_for_timeout(1200)

    def t_load():
        foot = pg.locator("tfoot").inner_text()
        assert "$4,579" in foot, foot
    step("deals table loads with open pipeline sum $4,579", t_load)

    for v in ["People", "Companies", "Tasks", "Activity", "Reports", "Pipelines", "Going cold", "Deals"]:
        step(f"nav {v}", lambda v=v: side(v))

    def t_inline_value():
        cell = pg.locator("[data-edit$=':monetary_value']").first
        cell.click()
        pg.keyboard.press("Control+a")
        pg.keyboard.type("1500")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(800)
        assert "1,500" in pg.locator("tbody").inner_text()
    step("inline edit a deal value", t_inline_value)

    def t_stage_select():
        sel = pg.locator("select[data-change=stage]").first
        did = sel.get_attribute("data-id")
        sel.select_option(label="Qualified")
        pg.wait_for_timeout(800)
        assert [d for d in api("/api/opportunities?limit=999") if d["id"] == did][0]["stage_name"] == "Qualified"
    step("change stage from the table", t_stage_select)

    def t_peek_log():
        open_row("Tenant request intake")
        pg.fill("#act-body", "Called about the proposal.")
        pg.get_by_role("button", name="Log", exact=True).click()
        pg.wait_for_timeout(800)
        assert "Called about the proposal." in pg.locator("#peek-body").inner_text()
        pg.keyboard.press("Escape")
    step("open a deal and log an activity", t_peek_log)

    def t_new_person():
        side("People")
        pg.get_by_role("button", name="+ New person").click()
        pg.wait_for_timeout(300)
        pg.fill("[name=first_name]", "<img src=x onerror=alert(1)>")
        pg.fill("[name=last_name]", "Tester")
        pg.get_by_role("button", name="Create").click()
        pg.wait_for_timeout(900)
        assert "<img src=x onerror=alert(1)> Tester" in pg.locator("#peek-title").inner_text()
        assert not any(m == "1" for _, m in dialogs), "HTML payload executed"
        pg.keyboard.press("Escape")
        assert "<img src=x" in pg.locator("tbody").inner_text()
    step("create a person (HTML payload stays text)", t_new_person)

    def t_unlink():
        open_row("Dana")
        pg.select_option("#peek-form [name=company_id]", value="")
        pg.get_by_role("button", name="Save changes").click()
        pg.wait_for_timeout(800)
        c = [x for x in api("/api/contacts") if x["first_name"] == "Dana"][0]
        assert c["company_id"] is None, c["company_id"]
        pg.keyboard.press("Escape")
    step("unlink a person's company in the panel", t_unlink)

    def t_new_deal():
        side("Deals")
        pg.get_by_role("button", name="+ New deal").click()
        pg.wait_for_timeout(300)
        pg.fill("[name=name]", "Walk-in inquiry")
        pg.fill("[name=monetary_value]", "650")
        pg.get_by_role("button", name="Create").click()
        pg.wait_for_timeout(900)
        assert deal("Walk-in inquiry")["contact_id"] is None
        pg.keyboard.press("Escape")
    step("create a deal with no contact", t_new_deal)

    def t_board():
        pg.get_by_role("button", name="Board").click()
        pg.wait_for_timeout(600)
        pg.drag_and_drop("[data-drag]:has-text('Walk-in inquiry')", "[data-drop]:has(h3:has-text('Won'))")
        pg.wait_for_timeout(1000)
        d = deal("Walk-in inquiry")
        assert d["stage_name"] == "Won" and d["status"] == "won", (d["stage_name"], d["status"])
        pg.get_by_role("button", name="Table").click()
        pg.wait_for_timeout(400)
    step("drag a card into Won on the board (closes it)", t_board)

    def t_panel_stage_won():
        open_row("Review request automation")
        pg.select_option("#peek-form [name=stage_id]", label="Won")
        pg.get_by_role("button", name="Save changes").click()
        pg.wait_for_timeout(800)
        assert deal("Review request automation")["status"] == "won"
        pg.keyboard.press("Escape")
    step("set stage to Won in the panel (closes it)", t_panel_stage_won)

    def t_bulk():
        boxes = pg.locator("tbody input[data-check]")
        boxes.nth(0).check()
        pg.wait_for_timeout(200)
        pg.locator("tbody input[data-check]").nth(1).check()
        pg.wait_for_timeout(300)
        pg.select_option("select[data-change=bulk-stage]", label="Proposal Sent")
        pg.wait_for_timeout(1200)
        assert pg.locator(".bulk").count() == 0
    step("bulk-move two deals", t_bulk)

    def t_tasks():
        side("Tasks")
        n0 = len([t for t in api("/api/tasks") if t["status"] == "done"])
        pg.locator("input[data-toggle-task]").first.check()
        pg.wait_for_timeout(800)
        assert len([t for t in api("/api/tasks") if t["status"] == "done"]) == n0 + 1
        due = pg.locator("input[data-change=task-due]").first
        due.fill("2026-12-31")
        due.dispatch_event("change")
        pg.wait_for_timeout(800)
        assert any(t["due_date"] == "2026-12-31" for t in api("/api/tasks"))
    step("complete a task and change a due date", t_tasks)

    def t_palette():
        pg.keyboard.press("Control+k")
        pg.wait_for_timeout(300)
        pg.keyboard.type("okafor")
        pg.wait_for_timeout(800)
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(600)
        assert "Tom Okafor" in pg.locator("#peek-title").inner_text()
        pg.keyboard.press("Escape")
    step("Ctrl+K finds and opens a person", t_palette)

    def t_saved_view():
        side("Deals")
        pg.fill("[data-input=q]", "tenant")
        pg.wait_for_timeout(300)
        answer[0] = "Tenant deals"
        pg.get_by_role("button", name="Save view").click()
        pg.wait_for_timeout(800)
        answer[0] = ""
        side("People")
        pg.locator("aside").get_by_text("Tenant deals").click()
        pg.wait_for_timeout(500)
        assert pg.locator("[data-input=q]").input_value() == "tenant"
        assert pg.locator("tbody tr.row").count() == 1
    step("save a view and re-apply it", t_saved_view)

    def t_settings():
        side("Pipelines")
        pg.fill("[data-add-stage]", "Negotiation")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(700)
        names = [s["name"] for s in api("/api/pipelines")[0]["stages"]]
        assert names[-1] == "Negotiation", names
        pg.locator("button[data-act=move-stage][data-dir='-1']").last.click()
        pg.wait_for_timeout(700)
        names = [s["name"] for s in api("/api/pipelines")[0]["stages"]]
        assert names[-2] == "Negotiation", names
    step("add and reorder a pipeline stage", t_settings)

    def t_reports():
        side("Reports")
        pg.wait_for_timeout(600)
        assert "open pipeline" in pg.locator("#body").inner_text().lower()
    step("reports render", t_reports)

    def value_cell(name):
        side("Deals")
        pg.get_by_role("button", name="All", exact=True).click()
        pg.wait_for_timeout(300)
        return pg.locator(f"[data-edit='deal:{deal(name)['id']}:monetary_value']")

    def t_cents():
        put(f"/api/opportunities/{deal('Storm-season lead capture')['id']}", {"monetary_value": 997.5})
        pg.reload()
        pg.wait_for_timeout(900)
        cell = value_cell("Storm-season lead capture")
        assert cell.inner_text() == "$997.50", cell.inner_text()
        cell.click()
        pg.locator("h1").click()
        pg.wait_for_timeout(600)
        assert deal("Storm-season lead capture")["monetary_value"] == 997.5
    step("a value with cents survives a click in and out", t_cents)

    def t_letters():
        cell = value_cell("Storm-season lead capture")
        cell.click()
        pg.keyboard.press("Control+a")
        pg.keyboard.type("abc")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(600)
        assert deal("Storm-season lead capture")["monetary_value"] == 997.5
    step("letters in a value cell are refused", t_letters)

    def t_escape():
        cell = value_cell("Storm-season lead capture")
        cell.click()
        pg.keyboard.press("Control+a")
        pg.keyboard.type("1")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(600)
        assert deal("Storm-season lead capture")["monetary_value"] == 997.5
        assert cell.inner_text() == "$997.50", cell.inner_text()
    step("Escape cancels an inline edit", t_escape)

    def t_delete():
        side("Deals")
        pg.get_by_role("button", name="All", exact=True).click()
        pg.wait_for_timeout(300)
        open_row("Walk-in inquiry")
        pg.get_by_role("button", name="Delete").click()
        pg.wait_for_timeout(800)
        assert not [d for d in api("/api/opportunities?limit=999") if d["name"] == "Walk-in inquiry"]
    step("delete a deal from the panel", t_delete)
    b.close()

for r in results:
    print(*r)
print("external requests:", external or "none")
print("issues:", *issues, sep="\n  ") if issues else print("issues: none")
failed = [r for r in results if r[0] == "FAIL"]
print(f"{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed or issues or external else 0)
