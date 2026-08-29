from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

OUT = Path(os.environ.get("OUT_DIR", "insurance_harvest_output"))
OUT.mkdir(parents=True, exist_ok=True)

SOURCES = [
    {"key": "ma", "name": "بیمه ما", "urls": ["https://www.bimehma.com/"]},
    {"key": "mellat", "name": "بیمه ملت", "urls": ["https://www.mellatinsurance.com/marakez", "https://darman.mellatyar.app/home/Centers"]},
    {"key": "moallem", "name": "بیمه معلم", "urls": ["https://my.mic.co.ir/map/medical-centers"]},
    {"key": "saman", "name": "بیمه سامان", "urls": ["https://providers.darmanet.ir/", "https://darmanet.ir/table"]},
    {"key": "pasargad", "name": "بیمه پاسارگاد", "urls": ["https://www.insurancepasargad.com/service-portal/174-treatment-centers", "https://iranassistance.com/CareCenter/Index"]},
    {"key": "kosar", "name": "بیمه کوثر", "urls": ["https://www.kins.ir/"]},
    {"key": "razi", "name": "بیمه رازی", "urls": ["https://razi24.ir/"]},
    {"key": "sarmad", "name": "بیمه سرمد", "urls": ["https://webapp.sarmadins.ir/", "https://www.sarmadins.ir/"]},
    {"key": "parsian", "name": "بیمه پارسیان", "urls": ["https://www.parsianinsurance.ir/"]},
    {"key": "novin", "name": "بیمه نوین", "urls": ["https://www.novininsurance.com/"]},
]

KW = re.compile(r"(درمان|مرکز|مراکز|قرارداد|medical|health|center|provider)", re.I)
DL = re.compile(r"(اکسل|excel|xlsx|xls|csv|خروجی|دانلود|download)", re.I)
FILE_EXT = re.compile(r"\.(xlsx?|csv)(?:$|[?#])", re.I)
EXCEL_MIME = ("spreadsheet", "excel", "csv", "octet-stream")


def safe_name(s: str, limit: int = 100) -> str:
    s = re.sub(r"[^\w\-.\u0600-\u06FF]+", "_", s, flags=re.UNICODE).strip("_")
    return (s or "file")[:limit]


def unique_path(folder: Path, name: str) -> Path:
    p = folder / name
    if not p.exists():
        return p
    stem, suf = p.stem, p.suffix
    i = 2
    while True:
        q = folder / f"{stem}_{i}{suf}"
        if not q.exists():
            return q
        i += 1


async def save_response_if_file(resp, folder: Path, downloads: list[dict]):
    try:
        headers = await resp.all_headers()
        cd = headers.get("content-disposition", "")
        ct = headers.get("content-type", "").lower()
        url = resp.url
        is_file = FILE_EXT.search(url) or "attachment" in cd.lower() or any(x in ct for x in EXCEL_MIME)
        if not is_file:
            return
        # Avoid saving ordinary binary site assets.
        if "octet-stream" in ct and not ("attachment" in cd.lower() or FILE_EXT.search(url)):
            return
        body = await resp.body()
        if len(body) < 100:
            return
        filename = None
        m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", cd, re.I)
        if m:
            filename = m.group(1).strip().strip('"')
        if not filename:
            filename = Path(urlparse(url).path).name or "download.bin"
        filename = safe_name(filename)
        if not Path(filename).suffix and "csv" in ct:
            filename += ".csv"
        path = unique_path(folder, filename)
        path.write_bytes(body)
        downloads.append({"kind": "network", "url": url, "path": str(path), "bytes": len(body), "content_type": ct})
    except Exception:
        return


async def direct_download(context, href: str, folder: Path, downloads: list[dict]):
    try:
        r = await context.request.get(href, timeout=30000)
        if not r.ok:
            return
        body = await r.body()
        if len(body) < 100:
            return
        headers = r.headers
        cd = headers.get("content-disposition", "")
        filename = Path(urlparse(href).path).name or "download"
        m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", cd, re.I)
        if m:
            filename = m.group(1).strip().strip('"')
        filename = safe_name(filename)
        ct = headers.get("content-type", "").lower()
        if not Path(filename).suffix:
            filename += ".csv" if "csv" in ct else ".xlsx"
        path = unique_path(folder, filename)
        path.write_bytes(body)
        downloads.append({"kind": "direct", "url": href, "path": str(path), "bytes": len(body), "content_type": ct})
    except Exception:
        pass


async def inspect_page(page, context, url: str, folder: Path, rec: dict):
    page_downloads = rec.setdefault("downloads", [])
    network_tasks = []

    def on_response(resp):
        network_tasks.append(asyncio.create_task(save_response_if_file(resp, folder, page_downloads)))

    page.on("response", on_response)
    t0 = time.time()
    try:
        r = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        rec["opened"].append({"requested": url, "final": page.url, "status": r.status if r else None})
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)
    except Exception as e:
        rec["errors"].append({"url": url, "stage": "goto", "error": repr(e)})
        return []

    # Save a lightweight trace of what was visible.
    try:
        html = await page.content()
        h = hashlib.sha1(page.url.encode()).hexdigest()[:10]
        (folder / f"page_{h}.html").write_text(html, encoding="utf-8", errors="ignore")
        await page.screenshot(path=str(folder / f"page_{h}.png"), full_page=True)
    except Exception:
        pass

    # Direct file links.
    candidates = []
    try:
        links = await page.locator("a[href]").evaluate_all("els => els.map(a => ({text:(a.innerText||a.textContent||'').trim(), href:a.href}))")
    except Exception:
        links = []
    for x in links:
        href = x.get("href") or ""
        text = x.get("text") or ""
        if href.startswith("javascript:") or not href.startswith("http"):
            continue
        if FILE_EXT.search(href):
            await direct_download(context, href, folder, page_downloads)
        if KW.search(text + " " + href) or DL.search(text + " " + href):
            candidates.append(href)

    # Buttons/links that may trigger a download.
    try:
        loc = page.locator("a,button,input[type=button],input[type=submit]")
        n = min(await loc.count(), 400)
        clicked = 0
        for i in range(n):
            el = loc.nth(i)
            try:
                text = (await el.inner_text(timeout=500)).strip()
            except Exception:
                try:
                    text = (await el.get_attribute("value") or "").strip()
                except Exception:
                    text = ""
            if not DL.search(text):
                continue
            if clicked >= 8:
                break
            clicked += 1
            before = len(page_downloads)
            try:
                async with page.expect_download(timeout=10000) as dinfo:
                    await el.click(timeout=5000)
                d = await dinfo.value
                suggested = safe_name(d.suggested_filename or f"download_{clicked}.bin")
                path = unique_path(folder, suggested)
                await d.save_as(str(path))
                page_downloads.append({"kind": "click", "url": page.url, "button": text, "path": str(path), "bytes": path.stat().st_size})
            except Exception:
                # Some export buttons launch an XHR instead of a browser download; response listener handles those.
                try:
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
    except Exception as e:
        rec["errors"].append({"url": page.url, "stage": "click_scan", "error": repr(e)})

    # Record visible table size. Do not call it complete automatically.
    try:
        rows = await page.locator("table tbody tr").count()
        rec.setdefault("tables", []).append({"url": page.url, "visible_rows": rows})
        if rows >= 20:
            data = await page.locator("table").first.evaluate("tbl => [...tbl.rows].map(r => [...r.cells].map(c => (c.innerText||'').trim()))")
            if data:
                tpath = unique_path(folder, "visible_table_candidate.csv")
                with tpath.open("w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerows(data)
                rec.setdefault("table_candidates", []).append(str(tpath))
    except Exception:
        pass

    if network_tasks:
        await asyncio.gather(*network_tasks, return_exceptions=True)
    page.remove_listener("response", on_response)
    rec.setdefault("timing", []).append({"url": page.url, "seconds": round(time.time()-t0, 1)})

    # Keep only a small set of likely useful next pages.
    base_host = urlparse(page.url).netloc.lower().replace("www.", "")
    out = []
    seen = set()
    for href in candidates:
        hhost = urlparse(href).netloc.lower().replace("www.", "")
        if href in seen:
            continue
        # Same site, or known treatment partner portals.
        if hhost == base_host or any(x in hhost for x in ["darmanet.ir", "mellatyar.app", "iranassistance.com", "iraneit.com", "rasatpa.ir"]):
            seen.add(href)
            out.append(href)
        if len(out) >= 12:
            break
    return out


async def harvest_source(browser, source):
    folder = OUT / source["key"]
    folder.mkdir(parents=True, exist_ok=True)
    rec = {"key": source["key"], "insurer": source["name"], "seed_urls": source["urls"], "opened": [], "downloads": [], "errors": []}
    context = await browser.new_context(
        accept_downloads=True,
        locale="fa-IR",
        timezone_id="Asia/Tehran",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        ignore_https_errors=True,
    )
    page = await context.new_page()
    visited = set()
    queue = list(source["urls"])
    depth = {}
    for u in queue:
        depth[u] = 0
    while queue and len(visited) < 16:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        next_links = await inspect_page(page, context, url, folder, rec)
        d = depth.get(url, 0)
        if d < 2:
            for x in next_links:
                if x not in visited and x not in queue:
                    depth[x] = d + 1
                    queue.append(x)
    await context.close()
    # De-duplicate duplicate download entries by exact content hash.
    hashes = {}
    kept = []
    for item in rec["downloads"]:
        p = Path(item["path"])
        if not p.exists():
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        item["sha256"] = digest
        if digest in hashes:
            item["duplicate_of"] = hashes[digest]
        else:
            hashes[digest] = str(p)
            kept.append(item)
    rec["unique_downloads"] = kept
    (folder / "report.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


async def main():
    report = {"generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        for source in SOURCES:
            try:
                rec = await harvest_source(browser, source)
            except Exception as e:
                rec = {"key": source["key"], "insurer": source["name"], "errors": [{"stage": "fatal", "error": repr(e)}], "unique_downloads": []}
            report["sources"].append(rec)
        await browser.close()
    (OUT / "master_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Human-readable summary for quick review.
    with (OUT / "SUMMARY.md").open("w", encoding="utf-8") as f:
        f.write("# DrLinq insurance source harvest\n\n")
        for r in report["sources"]:
            f.write(f"## {r.get('insurer')}\n")
            f.write(f"- opened: {len(r.get('opened', []))}\n")
            f.write(f"- unique downloads: {len(r.get('unique_downloads', []))}\n")
            f.write(f"- errors: {len(r.get('errors', []))}\n")
            for d in r.get("unique_downloads", []):
                f.write(f"  - {d.get('path')} ({d.get('bytes', 0)} bytes) ← {d.get('url','')}\n")
            f.write("\n")

if __name__ == "__main__":
    asyncio.run(main())
