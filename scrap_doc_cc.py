import re
from pathlib import Path
from playwright.sync_api import sync_playwright

PAGE_URL = "https://sigaa.ufpi.br/sigaa/public/curso/documentos.jsf?lc=pt_BR&id=74268"
OUTPUT_DIR = Path("documentos_sigaa")

def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]+', " - ", name)
    name = re.sub(r"\s+", " ", name)
    return name[:200].strip(" .")

OUTPUT_DIR.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.goto(PAGE_URL, wait_until="networkidle")

    # Adjust this selector after inspecting the page if needed
    rows = page.locator("tr")
    total = rows.count()

    for i in range(total):
        row = rows.nth(i)
        text = row.inner_text().strip()

        if not text or text.lower() in {"nome", "baixar arquivo"}:
            continue

        links = row.locator("a")
        if links.count() == 0:
            continue

        title = sanitize_filename(text.split("\n")[-1])

        try:
            with page.expect_download() as download_info:
                links.nth(0).click()

            download = download_info.value
            suggested = download.suggested_filename
            ext = Path(suggested).suffix
            download.save_as(str(OUTPUT_DIR / f"{title}{ext}"))
            print(f"[OK] {title}{ext}")
        except Exception as e:
            print(f"[ERRO] {title}: {e}")

    browser.close()