"""Self-check: valida parse_jobs_from_html contra um HTML Next.js de exemplo.

Roda com: python3 test_gupy_parsing.py
"""

from main import is_tech_job, matches_keywords, parse_jobs_from_html

FAKE_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"jobs":[
  {"id": 111, "title": "Estagiário de Dados", "type": "vacancy_type_internship",
   "workplace": {"address": {"city": "São Paulo"}}},
  {"id": 222, "title": "Analista de Sistemas Sênior", "type": "vacancy_type_employee",
   "workplace": {"address": {"city": "Rio de Janeiro"}}}
]}}}</script>
</body></html>
"""

jobs = parse_jobs_from_html(FAKE_HTML)
assert len(jobs) == 2, f"esperava 2 vagas, veio {len(jobs)}"
assert jobs[0]["title"] == "Estagiário de Dados"
assert jobs[0]["workplace"]["address"]["city"] == "São Paulo"

assert matches_keywords("Estagiário de Dados") is True
assert matches_keywords("Analista de Sistemas Sênior") is False

assert parse_jobs_from_html("<html>sem next data</html>") == []

assert is_tech_job("Desenvolvedor Backend Júnior", "Tecnologia") is True
assert is_tech_job("Analista de Sistemas Sênior", "") is True
assert is_tech_job("Estagiário de Marketing", "Marketing") is False
assert is_tech_job("Estagiário de Desenvolvimento Organizacional", "Gente e Gestão") is False

print("[ok] parse_jobs_from_html e matches_keywords passaram.")

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

from main import is_in_brasilia

assert is_in_brasilia("Brasília, DF, BR") is True
assert is_in_brasilia("Brasilia, DF, BR") is True
assert is_in_brasilia("Valparaíso de Goiás, GO, BR") is False
assert is_in_brasilia("Águas Lindas de Goiás, GO, BR") is False
assert is_in_brasilia("São Paulo, SP, BR") is False
assert is_in_brasilia("") is False
assert is_in_brasilia(None) is False

print("[ok] is_in_brasilia passou.")
