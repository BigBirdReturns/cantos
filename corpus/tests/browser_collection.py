"""Exercise the real local delivery through discovery, replay, export and reopen."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from corpus.reader import Collection, read_json
from corpus.server import make_server
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    state = args.out / "attempts"
    server = make_server(args.bundle, state, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks, errors = [], []

    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1450, "height": 1050})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator("#status")).to_contain_text("1,448 matching")
            check("real corpus summary", "70,725" in page.locator("#collectionInfo").inner_text())
            first_page = page.locator(".result").first.get_attribute("data-row")
            page.locator("#next").click()
            expect(page.locator("#page")).to_have_text("26–50")
            check("pagination advances", page.locator(".result").first.get_attribute("data-row") != first_page)
            page.locator("select[name=unit]").select_option("Latency (ms)")
            page.locator("#search button").click()
            expect(page.locator("#status")).to_contain_text("571 matching")
            row_id = page.locator(".result").first.get_attribute("data-row")
            page.locator(".result").first.click()
            page.locator("#rebuild").wait_for()
            collection = Collection(args.bundle, state)
            history = collection.history(row_id)
            original_path = collection.export(row_id)
            original_bytes = original_path.read_bytes()
            original_events = read_json(original_path)["workspace"]["events"]
            check("real normalization correction", any(c["field"] == "throughput" and c["after"] is None for c in history["changes"]))
            check("producer rationale stays missing", "does not record the producer" in page.locator("#history").inner_text())
            check("producer implementation link exposed", page.get_by_role("link", name="Producer implementation").count() == 1)
            page.locator("#pin").click()
            check("conditions comparison visible", page.locator("#comparison").is_visible())
            for index in range(2):
                page.locator("#actor").fill("Cantos local verification")
                with page.expect_response(lambda r: r.url.endswith("/api/reproject"), timeout=120000) as response:
                    page.locator("#rebuild").click()
                check(f"attempt {index+1} returned", response.value.status == 201)
                expect(page.get_by_role("link", name="Export this history", exact=True)).to_have_count(index+1)
            # A server commit followed by a lost response must reopen the saved
            # history instead of asserting that no attempt was added.
            def lose_response(route):
                route.fetch()
                route.abort()
            page.route("**/api/reproject", lose_response)
            page.locator("#actor").fill("Cantos local verification")
            page.locator("#rebuild").click()
            expect(page.locator("#error")).to_contain_text("Could not confirm completion", timeout=15000)
            expect(page.get_by_role("link", name="Export this history", exact=True)).to_have_count(3)
            check("lost response reconciles committed attempt", True)
            page.unroute("**/api/reproject", lose_response)
            page.screenshot(path=str(args.out / "collection-recovery.png"), full_page=True)
            with page.expect_download() as download:
                page.get_by_role("link", name="Export this history", exact=True).last.click()
            export_path = args.out / "exported.research-packet.json"
            download.value.save_as(export_path)
            exported = read_json(export_path)
            events = exported["workspace"]["events"]
            check("native packet schema", exported["schema"] == "second-run/research-packet@1")
            check("original history preserved", events[:len(original_events)] == original_events)
            check("all three attempts extend one journal", len(events) == len(original_events) + 6)
            check("source packet unchanged", original_bytes == original_path.read_bytes())
            reopened = Collection(args.bundle, state).history(row_id)
            check("independent reader reopens retained attempts", len(reopened["attempts"]) == 3)
            check("source replay remains bounded", all(a["matches_current_projection"] and "no hardware benchmark" in a["boundary"] for a in reopened["attempts"]))
            page.reload()
            page.wait_for_selector(".result")
            expect(page.get_by_role("link", name="Export this history", exact=True)).to_have_count(3)
            check("bookmark and reload preserve retained history", True)
            page.screenshot(path=str(args.out / "collection-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(args.out / "collection-mobile.png"), full_page=True)
            check("mobile fits viewport", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            check("no browser exceptions", not errors)
            browser.close()
        request = Request(base + "/api/reproject", data=json.dumps({"row_id":row_id,"actor":"Untrusted"}).encode(), headers={"Content-Type":"application/json","Origin":"https://unrelated.invalid"})
        try:
            urlopen(request)
            raise AssertionError("cross-origin write was accepted")
        except HTTPError as error:
            check("cross-origin mutation rejected", error.code == 403)
        check("rejected operation left history unchanged", len(Collection(args.bundle, state).attempts(row_id)) == 3)
        report = {"checks":checks,"row_id":row_id,"bundle":str(args.bundle.resolve()),
                  "state":str(state.resolve()),"export_sha256":hashlib.sha256(export_path.read_bytes()).hexdigest(),
                  "scope":"Local normalization replay and native history continuity; no benchmark or calibration run."}
        (args.out / "verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
