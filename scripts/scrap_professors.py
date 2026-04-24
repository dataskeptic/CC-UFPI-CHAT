import re
from pathlib import Path
from playwright.sync_api import sync_playwright

DEPT_URL = "https://sigaa.ufpi.br/sigaa/public/departamento/professores.jsf?id=144"
BASE_URL = "https://sigaa.ufpi.br"
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "extracted_docs" / "professors"
OUTPUT_MD = OUTPUT_ROOT / "md"
OUTPUT_TXT = OUTPUT_ROOT / "txt"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUT_MD.mkdir(exist_ok=True)
OUTPUT_TXT.mkdir(exist_ok=True)


def slugify(name: str) -> str:
    name = name.lower().strip()
    for src, dst in [("áàãâä", "a"), ("éèêë", "e"), ("íìîï", "i"),
                     ("óòõôö", "o"), ("úùûü", "u"), ("ç", "c")]:
        for ch in src:
            name = name.replace(ch, dst)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ── Step 1: collect professor list ────────────────────────────────────────────

def collect_professors(page) -> list:
    print(f"[INFO] Acessando lista: {DEPT_URL}")
    page.goto(DEPT_URL, wait_until="networkidle", timeout=30000)

    professors = []
    spans = page.locator("span.pagina")
    for i in range(spans.count()):
        link = spans.nth(i).locator("a")
        if link.count() == 0:
            continue
        href = link.first.get_attribute("href") or ""
        if not href:
            continue

        row = spans.nth(i).locator("xpath=ancestor::tr[1]")
        name_span = row.locator("span.nome")
        if name_span.count() == 0:
            continue
        raw_name = clean(name_span.first.inner_text())
        name = re.sub(r"\s*\(.*?\)\s*$", "", raw_name).strip()
        if not name:
            continue

        profile_url = (BASE_URL + href) if href.startswith("/") else href
        siape_match = re.search(r"siape=(\d+)", href)
        siape = siape_match.group(1) if siape_match else ""
        disciplines_url = (
            f"{BASE_URL}/sigaa/public/docente/disciplinas.jsf?siape={siape}" if siape else ""
        )

        professors.append({
            "name": name,
            "siape": siape,
            "profile_url": profile_url,
            "disciplines_url": disciplines_url,
        })

    print(f"[INFO] {len(professors)} professores encontrados.")
    return professors


# ── Step 2: scrape individual profile ─────────────────────────────────────────

def scrape_profile(page, prof: dict) -> dict:
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

    page.goto(prof["profile_url"], wait_until="networkidle", timeout=30000)

    # Profile: dl/dt/dd inside #perfil-docente
    # Contacts: dl/dt/dd inside #contato  (singular, confirmed from live HTML)
    try:
        dls = page.locator("#perfil-docente dl, #contato dl")
        for i in range(dls.count()):
            dl = dls.nth(i)
            dt_loc = dl.locator("dt")
            dd_loc = dl.locator("dd")
            if dt_loc.count() == 0 or dd_loc.count() == 0:
                continue

            dt = clean(dt_loc.first.inner_text())
            # dd may contain <i>não informado</i> — still read the text
            value = clean(dd_loc.first.inner_text())
            # treat "não informado" as empty
            if value.lower() in ("não informado", "nao informado"):
                value = ""

            dt_lower = dt.lower()

            if "descri" in dt_lower and "pessoal" in dt_lower:
                data["descricao"] = value

            elif "forma" in dt_lower and ("acad" in dt_lower or "profissional" in dt_lower):
                data["formacao_profissional"] = value

            elif "reas de interesse" in dt_lower:
                data["areas_interesse"] = value

            elif "lattes" in dt_lower:
                a = dl.locator("a")
                if a.count() > 0:
                    data["lattes"] = clean(a.first.get_attribute("href") or value)
                else:
                    data["lattes"] = value

            elif "endere" in dt_lower and "profissional" in dt_lower:
                data["endereco"] = value

            elif dt_lower.strip() == "sala":
                data["sala"] = value

            elif "telefone" in dt_lower or "ramal" in dt_lower:
                data["telefone"] = value

            # "Endereço eletrônico" — the email field
            elif "eletr" in dt_lower:
                a = dl.locator("a")
                if a.count() > 0:
                    href = clean(a.first.get_attribute("href") or "")
                    data["email"] = href.replace("mailto:", "").strip() or value
                else:
                    data["email"] = value

    except Exception as e:
        print(f"      [WARN] perfil/contato: {e}")

    # Disciplines page
    if prof["disciplines_url"]:
        try:
            page.goto(prof["disciplines_url"], wait_until="networkidle", timeout=30000)
            data["disciplinas"] = parse_graduation_table(page)
        except Exception as e:
            print(f"      [WARN] disciplinas: {e}")

    return data


# ── Step 3: parse graduation disciplines table ────────────────────────────────

def parse_graduation_table(page) -> list:
    disciplines = []
    current_semester = ""

    try:
        grad_div = page.locator("div#turmas-graduacao")
        if grad_div.count() == 0:
            return disciplines

        rows = grad_div.locator("table tr")
        for i in range(rows.count()):
            row = rows.nth(i)

            # Semester header
            periodo = row.locator("td.anoPeriodo")
            if periodo.count() > 0:
                current_semester = clean(periodo.first.inner_text())
                continue

            # Spacer rows
            if row.locator("td.spacer").count() > 0:
                continue

            # Discipline row
            codigo_td = row.locator("td.codigo")
            if codigo_td.count() == 0:
                continue

            code = clean(codigo_td.first.inner_text())
            name = ""
            ch = ""
            horario = ""

            all_tds = row.locator("td")
            for j in range(all_tds.count()):
                cls = (all_tds.nth(j).get_attribute("class") or "").strip()
                val = clean(all_tds.nth(j).inner_text())
                if cls == "":
                    name = val
                elif cls == "ch":
                    ch = val
                elif cls == "horario":
                    horario = val

            if code and name and current_semester:
                disciplines.append({
                    "semester": current_semester,
                    "code": code,
                    "name": name,
                    "workload": ch,
                    "schedule": horario,
                })
    except Exception as e:
        print(f"      [WARN] parse_graduation_table: {e}")

    return disciplines


# ── Formatters ─────────────────────────────────────────────────────────────────

def format_txt(name: str, prof: dict, data: dict) -> str:
    sep = "=" * 60
    lines = [
        sep,
        f"PROFESSOR: {name.upper()}",
        f"Perfil SIGAA: {prof['profile_url']}",
        sep,
        "",
        "--- DESCRIÇÃO PESSOAL ---",
        data["descricao"] or "Não informado",
        "",
        "--- FORMAÇÃO ACADÊMICA / PROFISSIONAL ---",
        data["formacao_profissional"] or "Não informado",
        "",
        "--- ÁREAS DE INTERESSE ---",
        data["areas_interesse"] or "Não informado",
        "",
        "--- CURRÍCULO LATTES ---",
        data["lattes"] or "Não informado",
        "",
        "--- CONTATOS ---",
        f"Endereço      : {data['endereco'] or 'Não informado'}",
        f"Sala          : {data['sala'] or 'Não informado'}",
        f"Telefone/Ramal: {data['telefone'] or 'Não informado'}",
        f"E-mail        : {data['email'] or 'Não informado'}",
        "",
        "--- DISCIPLINAS MINISTRADAS (GRADUAÇÃO) ---",
    ]

    if data["disciplinas"]:
        current_sem = ""
        for d in data["disciplinas"]:
            if d["semester"] != current_sem:
                current_sem = d["semester"]
                lines.append("")
                lines.append(f"  Semestre: {current_sem}")
                lines.append(f"  {'Código':<14} {'Disciplina':<50} {'C.H.':<8} Horário")
                lines.append(f"  {'-'*14} {'-'*50} {'-'*8} {'-'*16}")
            lines.append(
                f"  {d['code']:<14} {d['name']:<50} {d['workload']:<8} {d['schedule']}"
            )
    else:
        lines.append("Nenhuma disciplina de graduação encontrada.")

    lines += ["", sep]
    return "\n".join(lines)


def format_md(name: str, prof: dict, data: dict) -> str:
    lines = [
        f"# {name}",
        "",
        f"**Perfil SIGAA:** [{prof['profile_url']}]({prof['profile_url']})",
        "",
        "## Descrição Pessoal",
        "",
        data["descricao"] or "_Não informado_",
        "",
        "## Formação Acadêmica / Profissional",
        "",
        data["formacao_profissional"] or "_Não informado_",
        "",
        "## Áreas de Interesse",
        "",
        data["areas_interesse"] or "_Não informado_",
        "",
        "## Currículo Lattes",
        "",
        f"[{data['lattes']}]({data['lattes']})" if data["lattes"] else "_Não informado_",
        "",
        "## Contatos",
        "",
        f"- **Endereço:** {data['endereco'] or 'Não informado'}",
        f"- **Sala:** {data['sala'] or 'Não informado'}",
        f"- **Telefone/Ramal:** {data['telefone'] or 'Não informado'}",
        f"- **E-mail:** {data['email'] or 'Não informado'}",
        "",
        "## Disciplinas Ministradas (Graduação)",
    ]

    if data["disciplinas"]:
        current_sem = ""
        for d in data["disciplinas"]:
            if d["semester"] != current_sem:
                current_sem = d["semester"]
                lines.append("")
                lines.append(f"### {current_sem}")
                lines.append("")
                lines.append("| Código | Disciplina | Carga Horária | Horário |")
                lines.append("|--------|------------|---------------|---------|")
            lines.append(
                f"| {d['code']} | {d['name']} | {d['workload']} | {d['schedule']} |"
            )
    else:
        lines += ["", "_Nenhuma disciplina de graduação encontrada._"]

    return "\n".join(lines)


# ── Index writers ──────────────────────────────────────────────────────────────

def write_index_txt(entries: list):
    sep = "=" * 60
    lines = [sep, "ÍNDICE DE PROFESSORES — CIÊNCIA DA COMPUTAÇÃO / UFPI", sep, ""]
    for e in entries:
        lines += [
            f"Professor : {e['name']}",
            f"E-mail    : {e['email']}",
            f"Lattes    : {e['lattes']}",
            f"Arquivo   : txt/{e['slug']}.txt  |  md/{e['slug']}.md",
            f"Disciplinas (graduação): {e['disciplines_count']}",
            "",
        ]
    (OUTPUT_ROOT / "index.txt").write_text("\n".join(lines), encoding="utf-8")
    print("[OK] index.txt")


def write_index_md(entries: list):
    lines = [
        "# Índice de Professores — Ciência da Computação / UFPI",
        "",
        "| Professor | E-mail | Lattes | Disciplinas (grad.) |",
        "|-----------|--------|--------|---------------------|" ,
    ]
    for e in entries:
        name_link = f"[{e['name']}](md/{e['slug']}.md)"
        lattes = f"[link]({e['lattes']})" if e["lattes"] not in ("", "—") else "—"
        lines.append(
            f"| {name_link} | {e['email'] or '—'} | {lattes} | {e['disciplines_count']} |"
        )
    (OUTPUT_ROOT / "index.md").write_text("\n".join(lines), encoding="utf-8")
    print("[OK] index.md")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        professors = collect_professors(page)
        index_entries = []

        for i, prof in enumerate(professors):
            name = prof["name"]
            slug = slugify(name)
            print(f"[{i+1}/{len(professors)}] {name}")

            try:
                data = scrape_profile(page, prof)

                (OUTPUT_TXT / f"{slug}.txt").write_text(
                    format_txt(name, prof, data), encoding="utf-8"
                )
                (OUTPUT_MD / f"{slug}.md").write_text(
                    format_md(name, prof, data), encoding="utf-8"
                )

                index_entries.append({
                    "name": name,
                    "email": data["email"] or "—",
                    "lattes": data["lattes"] or "—",
                    "slug": slug,
                    "disciplines_count": len(data["disciplinas"]),
                })
                print(
                    f"   [OK] {slug}.txt / {slug}.md"
                    f"  ({len(data['disciplinas'])} disciplinas)"
                )

            except Exception as e:
                print(f"   [ERRO] {name}: {e}")
                index_entries.append({
                    "name": name, "email": "—", "lattes": "—",
                    "slug": slug, "disciplines_count": 0,
                })

        browser.close()

        write_index_txt(index_entries)
        write_index_md(index_entries)
        print(f"\n[DONE] {len(professors)} professores. Arquivos em: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
