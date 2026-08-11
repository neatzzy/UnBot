# LinkedIn/Indeed/Glassdoor Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LinkedIn, Indeed and Glassdoor as job sources to the existing Discord bot (`main.py`), alongside the current Gupy scraper, restricted to on-site/hybrid jobs in Brasília plus remote jobs anywhere in Brazil, posted in the last 6 hours.

**Architecture:** `python-jobspy` runs two blocking `scrape_jobs()` calls (Brasília on-site/hybrid, Brazil-wide remote) offloaded to a thread via `asyncio.to_thread` since jobspy is synchronous and the bot is asyncio-based. Results are filtered through the existing `matches_keywords`/`is_tech_job` functions and normalized into the same job-dict shape the Gupy path already produces, then merged into `collect_new_jobs()` and deduped through the existing `seen_jobs.json` set (job board IDs get a `{site}_` prefix to avoid colliding with Gupy's numeric IDs).

**Tech Stack:** Python 3.12, `python-jobspy` (new dependency), existing `aiohttp`/`discord.py` stack.

## Global Constraints

- Gupy stays untouched functionally — no publish-date filter added there (confirmed the public Gupy data has no date field). Spec: [docs/superpowers/specs/2026-08-11-jobboard-integration-design.md](../specs/2026-08-11-jobboard-integration-design.md)
- `hours_old=6` passed natively to jobspy — no manual date math.
- Job level filter for job boards reuses existing `KEYWORDS` (estágio/júnior/trainee) — same as Gupy.
- Search term: `"tecnologia"` generic, filtering happens locally via existing keyword functions.
- Platform icon in Discord embeds: fixed emoji per source, no external logo URL.
- Dedup: same `seen_jobs.json`, IDs prefixed by site to avoid cross-source collisions.

---

### Task 1: Dependency and config constants

**Files:**
- Modify: `requirements.txt`
- Modify: `main.py:1-53` (imports and config section)

**Interfaces:**
- Produces: `JOBBOARD_SITES: list[str]`, `JOBBOARD_HOURS_OLD: int`, `JOBBOARD_RESULTS_WANTED: int`, `BRASILIA_LOCATION: str`, `JOBBOARD_SEARCH_TERM: str`, `PLATFORM_ICONS: dict[str, str]` — all module-level constants in `main.py`, consumed by Tasks 2-5.

- [ ] **Step 1: Add `python-jobspy` to `requirements.txt`**

Append this line (installed version confirmed working during design validation):

```
python-jobspy==1.1.82
```

- [ ] **Step 2: Install it into the project venv**

Run: `source venv/bin/activate && pip install -r requirements.txt`
Expected: `python-jobspy` and its transitive deps (pandas, numpy, requests, tls-client, markdownify, beautifulsoup4, regex) install without error.

- [ ] **Step 3: Add config constants to `main.py`**

In `main.py`, right after the `TECH_KEYWORDS` list (currently ends at line 53), add:

```python
# Configuração da busca em LinkedIn/Indeed/Glassdoor via jobspy.
JOBBOARD_SITES = ["linkedin", "indeed", "glassdoor"]
JOBBOARD_HOURS_OLD = 6
JOBBOARD_RESULTS_WANTED = 50
BRASILIA_LOCATION = "Brasília, DF, Brazil"
JOBBOARD_SEARCH_TERM = "tecnologia"

# Ícone (emoji) mostrado no embed do Discord conforme a origem da vaga.
PLATFORM_ICONS = {
    "gupy": "🚀",
    "linkedin": "💼",
    "indeed": "🔍",
    "glassdoor": "🏢",
}
```

- [ ] **Step 4: Verify the file still imports cleanly**

Run: `source venv/bin/activate && python3 -c "import main"`
Expected: no traceback (it will try to read `.env`/slugs, that's fine — we're only checking for syntax/import errors, not running the bot).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt main.py
git commit -m "build: add python-jobspy dependency and job board config constants"
```

---

### Task 2: Pure filter/normalize function `build_jobboard_entries`

**Files:**
- Modify: `main.py` (add function after `collect_new_jobs`, i.e. after current line 152)
- Test: `test_gupy_parsing.py`

**Interfaces:**
- Consumes: `matches_keywords(title: str) -> bool`, `is_tech_job(title: str, department: str) -> bool` (both already defined in `main.py`)
- Produces: `build_jobboard_entries(rows: list[dict]) -> list[dict]`, called by Task 3's `fetch_jobboard_jobs`. Each returned dict has keys: `id` (str, `{site}_{raw_id}`), `company` (str), `title` (str), `url` (str), `city` (str), `type` (str, always `""`), `source` (str, the site name).

- [ ] **Step 1: Write the failing test**

Add to `test_gupy_parsing.py` (append at the end, after the existing `is_tech_job` assertions and before the final `print`):

```python
from main import build_jobboard_entries

FAKE_JOBBOARD_ROWS = [
    {
        "id": "in-abc123",
        "site": "indeed",
        "title": "Estágio de Desenvolvimento Backend",
        "company": "Empresa X",
        "location": "Brasília, DF, BR",
        "job_url": "https://br.indeed.com/viewjob?jk=abc123",
    },
    {
        "id": "li-def456",
        "site": "linkedin",
        "title": "Analista de Sistemas Sênior",  # não bate keyword, deve ser descartada
        "company": "Empresa Y",
        "location": "São Paulo, SP, BR",
        "job_url": "https://linkedin.com/jobs/def456",
    },
    {
        "id": "gd-ghi789",
        "site": "glassdoor",
        "title": "Desenvolvedor Júnior",
        "company": None,  # empresa ausente, deve virar "Não informado"
        "location": None,
        "job_url": "https://glassdoor.com/job/ghi789",
    },
]

entries = build_jobboard_entries(FAKE_JOBBOARD_ROWS)
assert len(entries) == 2, f"esperava 2 vagas filtradas, veio {len(entries)}"

assert entries[0]["id"] == "indeed_in-abc123"
assert entries[0]["source"] == "indeed"
assert entries[0]["company"] == "Empresa X"
assert entries[0]["city"] == "Brasília, DF, BR"
assert entries[0]["url"] == "https://br.indeed.com/viewjob?jk=abc123"

assert entries[1]["id"] == "glassdoor_gd-ghi789"
assert entries[1]["company"] == "Não informado"
assert entries[1]["city"] == "Não informado"

print("[ok] build_jobboard_entries passou.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python3 test_gupy_parsing.py`
Expected: `ImportError: cannot import name 'build_jobboard_entries' from 'main'`

- [ ] **Step 3: Implement `build_jobboard_entries` in `main.py`**

Add right after `collect_new_jobs` (after current line 152, before the `# SERVIDOR HTTP` section header):

```python
def build_jobboard_entries(rows: list[dict]) -> list[dict]:
    """Filtra e normaliza linhas vindas do jobspy (LinkedIn/Indeed/Glassdoor)
    pro mesmo formato de dict que o fluxo do Gupy já produz."""
    entries = []
    for row in rows:
        title = row.get("title") or ""
        if not matches_keywords(title):
            continue
        if not is_tech_job(title, ""):
            continue
        site = row.get("site") or "indeed"
        raw_id = row.get("id") or row.get("job_url") or title
        entries.append({
            "id": f"{site}_{raw_id}",
            "company": row.get("company") or "Não informado",
            "title": title,
            "url": row.get("job_url") or "",
            "city": row.get("location") or "Não informado",
            "type": "",
            "source": site,
        })
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source venv/bin/activate && python3 test_gupy_parsing.py`
Expected: prints `[ok] parse_jobs_from_html e matches_keywords passaram.` then `[ok] build_jobboard_entries passou.`, no assertion errors.

- [ ] **Step 5: Commit**

```bash
git add main.py test_gupy_parsing.py
git commit -m "feat: add build_jobboard_entries filter/normalize function"
```

---

### Task 3: Network fetch wrapper `fetch_jobboard_jobs`

**Files:**
- Modify: `main.py` (add function right after `build_jobboard_entries`, and add `from jobspy import scrape_jobs` to the imports block at the top)

**Interfaces:**
- Consumes: `JOBBOARD_SITES`, `JOBBOARD_SEARCH_TERM`, `JOBBOARD_HOURS_OLD`, `JOBBOARD_RESULTS_WANTED`, `BRASILIA_LOCATION` (Task 1), `build_jobboard_entries` (Task 2)
- Produces: `fetch_jobboard_jobs() -> list[dict]` (synchronous, blocking — Task 4 offloads it to a thread). Same return shape as `build_jobboard_entries`.

No test for this step — it's a live network call, same pattern as `fetch_gupy_jobs` which also has no automated test (see spec's "Testes" section).

- [ ] **Step 1: Add the jobspy import**

In `main.py`, in the imports block (currently lines 7-17), add after `import aiohttp`:

```python
from jobspy import scrape_jobs
```

- [ ] **Step 2: Implement `fetch_jobboard_jobs`**

Add right after `build_jobboard_entries`:

```python
def fetch_jobboard_jobs() -> list[dict]:
    """Busca vagas no LinkedIn/Indeed/Glassdoor via jobspy: presencial/híbrido
    em Brasília + remoto no resto do Brasil, só das últimas
    JOBBOARD_HOURS_OLD horas. Função síncrona (jobspy é bloqueante) — quem
    chama deve rodar em thread separada."""
    common_kwargs = dict(
        site_name=JOBBOARD_SITES,
        search_term=JOBBOARD_SEARCH_TERM,
        country_indeed="brazil",
        hours_old=JOBBOARD_HOURS_OLD,
        results_wanted=JOBBOARD_RESULTS_WANTED,
    )
    rows = []
    try:
        df = scrape_jobs(location=BRASILIA_LOCATION, is_remote=False, **common_kwargs)
        rows.extend(df.where(df.notna(), None).to_dict("records"))
    except Exception as e:
        print(f"[erro] falha ao buscar vagas presenciais/híbridas em Brasília: {e}")
    try:
        df = scrape_jobs(location="Brazil", is_remote=True, **common_kwargs)
        rows.extend(df.where(df.notna(), None).to_dict("records"))
    except Exception as e:
        print(f"[erro] falha ao buscar vagas remotas: {e}")
    return build_jobboard_entries(rows)
```

- [ ] **Step 3: Verify it runs standalone**

Run: `source venv/bin/activate && python3 -c "from main import fetch_jobboard_jobs; jobs = fetch_jobboard_jobs(); print(len(jobs)); print(jobs[:2])"`
Expected: no traceback, prints a count (0+) and up to 2 job dicts. If it prints `[erro]` lines but still returns (possibly empty) — that's the expected degraded-mode behavior (see Global Constraints on blocking risk), not a failure of this step.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add fetch_jobboard_jobs network wrapper around jobspy"
```

---

### Task 4: Wire job boards into `collect_new_jobs`

**Files:**
- Modify: `main.py:125-152` (the `collect_new_jobs` function)

**Interfaces:**
- Consumes: `fetch_jobboard_jobs` (Task 3), `asyncio.to_thread` (stdlib, `asyncio` already imported at top)
- Produces: `collect_new_jobs(seen: set) -> list[dict]` now returns Gupy jobs (each with a new `"source": "gupy"` key) merged with job board jobs, deduped against `seen` — same signature as before, consumed by `check_jobs_loop` and `checar_vagas_cmd` (Task 5).

- [ ] **Step 1: Add `"source": "gupy"` to the Gupy job dict**

In `main.py`, inside `collect_new_jobs`, find the `new_jobs.append({...})` block (current lines 143-150):

```python
                new_jobs.append({
                    "id": job_id,
                    "company": slug,
                    "title": title,
                    "url": f"https://{slug}.gupy.io/job/{job_id}",
                    "city": (address.get("city") or "Não informado"),
                    "type": (job.get("type") or ""),
                })
```

Replace with:

```python
                new_jobs.append({
                    "id": job_id,
                    "company": slug,
                    "title": title,
                    "url": f"https://{slug}.gupy.io/job/{job_id}",
                    "city": (address.get("city") or "Não informado"),
                    "type": (job.get("type") or ""),
                    "source": "gupy",
                })
```

- [ ] **Step 2: Append the job board fetch + dedup at the end of `collect_new_jobs`**

Right before the function's final `return new_jobs` (current line 152), add:

```python

    jobboard_entries = await asyncio.to_thread(fetch_jobboard_jobs)
    for entry in jobboard_entries:
        if entry["id"] in seen:
            continue
        new_jobs.append(entry)
        seen.add(entry["id"])
```

So the full function tail reads:

```python
                seen.add(job_id)

    jobboard_entries = await asyncio.to_thread(fetch_jobboard_jobs)
    for entry in jobboard_entries:
        if entry["id"] in seen:
            continue
        new_jobs.append(entry)
        seen.add(entry["id"])

    return new_jobs
```

- [ ] **Step 3: Run the existing self-check to make sure nothing broke**

Run: `source venv/bin/activate && python3 test_gupy_parsing.py`
Expected: both `[ok]` lines print, no errors (this test doesn't call `collect_new_jobs` directly, it just guards against import/syntax breakage).

- [ ] **Step 4: Manual smoke test of the merged flow**

Run:
```bash
source venv/bin/activate && python3 -c "
import asyncio
from main import collect_new_jobs
jobs = asyncio.run(collect_new_jobs(set()))
print(len(jobs))
sources = {j['source'] for j in jobs}
print(sources)
"
```
Expected: no traceback; prints a count and a set of sources seen (subset of `{'gupy', 'linkedin', 'indeed', 'glassdoor'}` depending on what's live right now — empty set is fine if no keyword-matching vaga is currently posted).

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: merge job board results into collect_new_jobs"
```

---

### Task 5: Platform icon in Discord embeds

**Files:**
- Modify: `main.py:201-208` (`check_jobs_loop`)
- Modify: `main.py:228-235` (`checar_vagas_cmd`)

**Interfaces:**
- Consumes: `PLATFORM_ICONS` (Task 1), `job["source"]` (present on every job dict since Task 4)

- [ ] **Step 1: Update the embed title in `check_jobs_loop`**

Find (current lines 202-207):

```python
        embed = discord.Embed(
            title=job["title"],
            url=job["url"] or discord.Embed.Empty,
            description=f"**Empresa:** {job['company']}\n**Local:** {job['city']}",
            color=0x2ECC71,
        )
```

Replace with:

```python
        icon = PLATFORM_ICONS.get(job["source"], "")
        embed = discord.Embed(
            title=f"{icon} {job['title']}".strip(),
            url=job["url"] or discord.Embed.Empty,
            description=f"**Empresa:** {job['company']}\n**Local:** {job['city']}",
            color=0x2ECC71,
        )
```

- [ ] **Step 2: Apply the same change in `checar_vagas_cmd`**

Find (current lines 229-234, same shape):

```python
        embed = discord.Embed(
            title=job["title"],
            url=job["url"] or discord.Embed.Empty,
            description=f"**Empresa:** {job['company']}\n**Local:** {job['city']}",
            color=0x2ECC71,
        )
```

Replace with:

```python
        icon = PLATFORM_ICONS.get(job["source"], "")
        embed = discord.Embed(
            title=f"{icon} {job['title']}".strip(),
            url=job["url"] or discord.Embed.Empty,
            description=f"**Empresa:** {job['company']}\n**Local:** {job['city']}",
            color=0x2ECC71,
        )
```

- [ ] **Step 3: Run the self-check**

Run: `source venv/bin/activate && python3 test_gupy_parsing.py`
Expected: both `[ok]` lines print, no errors.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: prefix Discord embed title with platform icon"
```

---

### Task 6: Final end-to-end check

**Files:** none (verification only)

- [ ] **Step 1: Run full self-check suite**

Run: `source venv/bin/activate && python3 test_gupy_parsing.py`
Expected: `[ok] parse_jobs_from_html e matches_keywords passaram.` and `[ok] build_jobboard_entries passou.`, exit code 0.

- [ ] **Step 2: Confirm `main.py` still starts up to the token check**

Run: `source venv/bin/activate && python3 main.py`
Expected: fails fast with `Defina DISCORD_TOKEN (variável de ambiente) antes de rodar.` if `.env` has no real token configured (expected in a dev sandbox), OR connects successfully if a real token is present. Either outcome confirms no import/syntax errors reached that point.

- [ ] **Step 3: Re-read the diff against the spec's "Fora de escopo" section**

Confirm no proxy/IP-rotation code, no cross-platform same-job dedup, and no seniority filter beyond `KEYWORDS` were added — all three were explicitly out of scope.
