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
