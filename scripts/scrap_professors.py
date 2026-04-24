import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DEPT_URL = "https://sigaa.ufpi.br/sigaa/public/departamento/professores.jsf?id=144"
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "extracted_docs" / "professors"
OUTPUT_MD = OUTPUT_ROOT / "md"
OUTPUT_TXT = OUTPUT_ROOT / "txt"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_MD.mkdir(exist_ok=True)
OUTPUT_TXT.mkdir(exist_ok=True)


def slugify(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[áàãâä]", "a", name)
    name = re.sub(r"[éèêë]", "e", name)
    name = re.sub(r"[íìîï]", "i", name)
    name = re.sub(r"[óòõôö]", "o", name)
    name = re.sub(r"[úùûü]", "u", name)
    name = re.sub(r"[ç]", "c", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def get_text_or_default(locator, default="Não informado") -> str:
    try:
        text = clean(locator.first.inner_text())
        return text if text else default
    except Exception:
        return default


def scrape_profile(page, profile_url: str) -> dict:
    data = {
        "descricao": "",
        "formacao_profissional": "",
        "areas_interesse": "",
        "lattes": "",
        "endereco": "",
        "sala": "",
        "telefone": "",
        "email": "",
        "disciplinas": [],
    }

    page.goto(profile_url, wait_until="networkidle", timeout=30000)

    # ── Perfil Pessoal ──────────────────────────────────────────────────────────
    try:
        rows = page.locator("table.visualizacao tr")
        current_label = ""
        for i in range(rows.count()):
            row = rows.nth(i)
            cells = row.locator("td")
            if cells.count() == 0:
                continue
            first_cell = clean(cells.first.inner_text())

            if "Descrição pessoal" in first_cell or "Descri" in first_cell and "pessoal" in first_cell:
                current_label = "descricao"
            elif "Formação acadêmica" in first_cell or "Forma" in first_cell and "profissional" in first_cell:
                current_label = "formacao"
            elif "Áreas de Interesse" in first_cell or "reas de Interesse" in first_cell:
                current_label = "areas"
            elif "Currículo Lattes" in first_cell or "Curr" in first_cell and "Lattes" in first_cell:
                current_label = "lattes"
                lattes_link = row.locator("a")
                if lattes_link.count() > 0:
                    data["lattes"] = clean(lattes_link.first.get_attribute("href") or "")
                current_label = ""
                continue
            else:
                if current_label and cells.count() >= 1:
                    value = ""
                    if cells.count() >= 2:
                        value = clean(cells.nth(1).inner_text())
                    else:
                        value = clean(cells.first.inner_text())

                    if current_label == "descricao" and not data["descricao"]:
                        data["descricao"] = value
                    elif current_label == "formacao" and not data["formacao_profissional"]:
                        data["formacao_profissional"] = value
                    elif current_label == "areas" and not data["areas_interesse"]:
                        data["areas_interesse"] = value
    except Exception:
        pass

    # fallback: look for labeled sections by heading text
    if not data["descricao"]:
        try:
            sections = page.locator("td.subFormulario, td.descricao, .rich-panel-body")
            for i in range(min(sections.count(), 30)):
                txt = clean(sections.nth(i).inner_text())
                if len(txt) > 60:
                    data["descricao"] = txt
                    break
        except Exception:
            pass

    # ── Contatos ────────────────────────────────────────────────────────────────
    try:
        all_trs = page.locator("tr")
        for i in range(all_trs.count()):
            row_text = clean(all_trs.nth(i).inner_text())
            cells = all_trs.nth(i).locator("td")
            if cells.count() < 2:
                continue
            label = clean(cells.first.inner_text()).lower()
            value = clean(cells.nth(1).inner_text())

            if "sala" in label and not data["sala"]:
                data["sala"] = value or "Não informado"
            elif "telefone" in label or "ramal" in label:
                data["telefone"] = value or "Não informado"
            elif "eletr" in label or "e-mail" in label or "email" in label:
                email_link = all_trs.nth(i).locator("a")
                if email_link.count() > 0:
                    href = email_link.first.get_attribute("href") or ""
                    data["email"] = href.replace("mailto:", "").strip() or value
                else:
                    data["email"] = value
    except Exception:
        pass

    # ── Endereço profissional ────────────────────────────────────────────────────
    try:
        endereco_label = page.get_by_text("Endereço profissional", exact=False)
        if endereco_label.count() > 0:
            parent = endereco_label.first.locator("xpath=ancestor::tr[1]")
            next_row = parent.locator("xpath=following-sibling::tr[1]")
            if next_row.count() > 0:
                data["endereco"] = clean(next_row.first.inner_text())
    except Exception:
        pass

    # ── Disciplinas Ministradas (Graduação only) ─────────────────────────────────
    try:
        disc_link = page.get_by_role("link", name=re.compile("disciplinas ministradas", re.IGNORECASE))
        if disc_link.count() == 0:
            disc_link = page.locator("a", has_text=re.compile("disciplina", re.IGNORECASE))

        if disc_link.count() > 0:
            disc_link.first.click()
            page.wait_for_load_state("networkidle", timeout=15000)

            # Click the "Graduação" tab explicitly
            grad_tab = page.get_by_role("link", name=re.compile(r"^Gradua", re.IGNORECASE))
            if grad_tab.count() == 0:
                grad_tab = page.locator("a, span, li", has_text=re.compile(r"^Gradua", re.IGNORECASE))
            if grad_tab.count() > 0:
                grad_tab.first.click()
                time.sleep(1)
                page.wait_for_load_state("networkidle", timeout=10000)

            data["disciplinas"] = parse_disciplines_table(page)
    except Exception as e:
        print(f"      [WARN] Disciplinas: {e}")

    return data


def parse_disciplines_table(page) -> list:
    disciplines = []
    current_semester = ""

    try:
        rows = page.locator("table tr")
        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            cells = row.locator("td, th")
            cell_count = cells.count()

            if cell_count == 0:
                continue

            row_text = clean(row.inner_text())

            # Semester header row (e.g. "2026.1")
            if re.match(r"^\d{4}\.\d$", row_text):
                current_semester = row_text
                continue

            # Header row — skip
            if re.match(r"disciplina.*carga|código.*disciplina", row_text.lower()):
                continue

            # Data row — expect at least 3 cells: code+name, workload, schedule
            if cell_count >= 3 and current_semester:
                code_name = clean(cells.nth(0).inner_text())
                workload = clean(cells.nth(1).inner_text())
                schedule = clean(cells.nth(2).inner_text()) if cell_count > 2 else ""

                # Split code from name (code is usually "XX/XXXnnn" pattern)
                code_match = re.match(r"^([A-Z]{2}/[A-Z]{2,4}\d{3})\s+(.*)", code_name, re.DOTALL)
                if code_match:
                    code = code_match.group(1).strip()
                    name = clean(code_match.group(2))
                else:
                    code = ""
                    name = code_name

                if name and workload:
                    disciplines.append({
                        "semester": current_semester,
                        "code": code,
                        "name": name,
                        "workload": workload,
                        "schedule": schedule,
                    })
    except Exception as e:
        print(f"      [WARN] parse_disciplines: {e}")

    return disciplines


def format_txt(name: str, url: str, data: dict) -> str:
    lines = []
    sep = "=" * 60

    lines.append(sep)
    lines.append(f"PROFESSOR: {name.upper()}")
    lines.append(f"Perfil SIGAA: {url}")
    lines.append(sep)

    lines.append("\n--- DESCRIÇÃO PESSOAL ---")
    lines.append(data["descricao"] or "Não informado")

    lines.append("\n--- FORMAÇÃO ACADÊMICA / PROFISSIONAL ---")
    lines.append(data["formacao_profissional"] or "Não informado")

    lines.append("\n--- ÁREAS DE INTERESSE ---")
    lines.append(data["areas_interesse"] or "Não informado")

    lines.append("\n--- CURRÍCULO LATTES ---")
    lines.append(data["lattes"] or "Não informado")

    lines.append("\n--- CONTATOS ---")
    lines.append(f"Endereço: {data['endereco'] or 'Não informado'}")
    lines.append(f"Sala: {data['sala'] or 'Não informado'}")
    lines.append(f"Telefone/Ramal: {data['telefone'] or 'Não informado'}")
    lines.append(f"E-mail: {data['email'] or 'Não informado'}")

    if data["disciplinas"]:
        lines.append("\n--- DISCIPLINAS MINISTRADAS (GRADUAÇÃO) ---")
        current_sem = ""
        for d in data["disciplinas"]:
            if d["semester"] != current_sem:
                current_sem = d["semester"]
                lines.append(f"\n  Semestre: {current_sem}")
                lines.append(f"  {'Código':<14} {'Disciplina':<45} {'C.H.':<8} Horário")
                lines.append(f"  {'-'*14} {'-'*45} {'-'*8} {'-'*16}")
            lines.append(
                f"  {d['code']:<14} {d['name']:<45} {d['workload']:<8} {d['schedule']}"
            )
    else:
        lines.append("\n--- DISCIPLINAS MINISTRADAS (GRADUAÇÃO) ---")
        lines.append("Nenhuma disciplina de graduação encontrada.")

    lines.append(f"\n{sep}")
    return "\n".join(lines)


def format_md(name: str, url: str, data: dict) -> str:
    lines = []

    lines.append(f"# {name}")
    lines.append(f"\n**Perfil SIGAA:** [{url}]({url})\n")

    lines.append("## Descrição Pessoal")
    lines.append(data["descricao"] or "_Não informado_")

    lines.append("\n## Formação Acadêmica / Profissional")
    lines.append(data["formacao_profissional"] or "_Não informado_")

    lines.append("\n## Áreas de Interesse")
    lines.append(data["areas_interesse"] or "_Não informado_")

    lines.append("\n## Currículo Lattes")
    if data["lattes"]:
        lines.append(f"[{data['lattes']}]({data['lattes']})")
    else:
        lines.append("_Não informado_")

    lines.append("\n## Contatos")
    lines.append(f"- **Endereço:** {data['endereco'] or 'Não informado'}")
    lines.append(f"- **Sala:** {data['sala'] or 'Não informado'}")
    lines.append(f"- **Telefone/Ramal:** {data['telefone'] or 'Não informado'}")
    lines.append(f"- **E-mail:** {data['email'] or 'Não informado'}")

    lines.append("\n## Disciplinas Ministradas (Graduação)")

    if data["disciplinas"]:
        current_sem = ""
        for d in data["disciplinas"]:
            if d["semester"] != current_sem:
                current_sem = d["semester"]
                lines.append(f"\n### {current_sem}")
                lines.append("| Código | Disciplina | Carga Horária | Horário |")
                lines.append("|--------|-----------|---------------|---------|")
            lines.append(
                f"| {d['code']} | {d['name']} | {d['workload']} | {d['schedule']} |"
            )
    else:
        lines.append("\n_Nenhuma disciplina de graduação encontrada._")

    return "\n".join(lines)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # ── Step 1: Collect professor list ──────────────────────────────────────
        print(f"[INFO] Acessando lista de professores: {DEPT_URL}")
        page.goto(DEPT_URL, wait_until="networkidle", timeout=30000)

        professors = []
        rows = page.locator("table tr")
        for i in range(rows.count()):
            row = rows.nth(i)
            name_cell = row.locator("td").first
            link = row.locator("a", has_text=re.compile("ver p.gina|ver perfil|perfil", re.IGNORECASE))

            if link.count() == 0:
                link = row.locator("a")

            if link.count() > 0:
                name = clean(name_cell.inner_text())
                href = link.first.get_attribute("href") or ""
                if href and name and name.lower() not in {"nome", "professor", "docente"}:
                    if not href.startswith("http"):
                        href = "https://sigaa.ufpi.br" + href
                    professors.append({"name": name, "url": href})

        print(f"[INFO] {len(professors)} professores encontrados.")

        index_entries = []

        # ── Step 2: Scrape each professor ────────────────────────────────────────
        for i, prof in enumerate(professors):
            name = prof["name"]
            url = prof["url"]
            slug = slugify(name)
            print(f"[{i+1}/{len(professors)}] {name}")

            try:
                data = scrape_profile(page, url)

                txt_content = format_txt(name, url, data)
                md_content = format_md(name, url, data)

                (OUTPUT_TXT / f"{slug}.txt").write_text(txt_content, encoding="utf-8")
                (OUTPUT_MD / f"{slug}.md").write_text(md_content, encoding="utf-8")

                index_entries.append({
                    "name": name,
                    "email": data["email"] or "—",
                    "lattes": data["lattes"] or "—",
                    "slug": slug,
                    "disciplines_count": len(data["disciplinas"]),
                })
                print(f"   [OK] {slug}.txt / {slug}.md")
            except Exception as e:
                print(f"   [ERRO] {name}: {e}")
                index_entries.append({
                    "name": name,
                    "email": "—",
                    "lattes": "—",
                    "slug": slug,
                    "disciplines_count": 0,
                })

        browser.close()

        # ── Step 3: Write index files ─────────────────────────────────────────────
        _write_index_txt(index_entries)
        _write_index_md(index_entries)
        print(f"\n[DONE] Arquivos salvos em: {OUTPUT_ROOT}")


def _write_index_txt(entries: list):
    sep = "=" * 60
    lines = [sep, "ÍNDICE DE PROFESSORES — CIÊNCIA DA COMPUTAÇÃO / UFPI", sep, ""]
    for e in entries:
        lines.append(f"Professor : {e['name']}")
        lines.append(f"E-mail    : {e['email']}")
        lines.append(f"Lattes    : {e['lattes']}")
        lines.append(f"Arquivo   : txt/{e['slug']}.txt  |  md/{e['slug']}.md")
        lines.append(f"Disciplinas (graduação): {e['disciplines_count']}")
        lines.append("")
    (OUTPUT_ROOT / "index.txt").write_text("\n".join(lines), encoding="utf-8")
    print("[OK] index.txt")


def _write_index_md(entries: list):
    lines = [
        "# Índice de Professores — Ciência da Computação / UFPI",
        "",
        "| Professor | E-mail | Lattes | Disciplinas |",
        "|-----------|--------|--------|-------------|",
    ]
    for e in entries:
        name_link = f"[{e['name']}](md/{e['slug']}.md)"
        lattes = f"[link]({e['lattes']})" if e["lattes"] != "—" else "—"
        lines.append(f"| {name_link} | {e['email']} | {lattes} | {e['disciplines_count']} |")
    (OUTPUT_ROOT / "index.md").write_text("\n".join(lines), encoding="utf-8")
    print("[OK] index.md")


if __name__ == "__main__":
    main()
