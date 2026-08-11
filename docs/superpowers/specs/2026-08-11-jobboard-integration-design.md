# Integração LinkedIn/Indeed/Glassdoor via jobspy

## Contexto

`main.py` hoje só varre vagas do Gupy (empresas listadas em `slugs_empresas.txt`),
filtra por `KEYWORDS` (estágio/júnior/trainee) + `TECH_KEYWORDS`, e posta no Discord
evitando repetição via `seen_jobs.json`.

Pedido: adicionar LinkedIn, Indeed e Glassdoor como fontes, restritas a:
- Presencial/híbrido em Brasília
- Remoto em qualquer lugar do Brasil
- Só vaga publicada nas últimas 6 horas

## Constraint descoberta

Testado ao vivo (`afya.gupy.io`): o JSON `__NEXT_DATA__` do Gupy não expõe data de
publicação (nem na listagem nem na página de detalhe da vaga, nem em `ld+json`).
Não dá pra aplicar filtro de 6h no Gupy. Decisão do usuário: Gupy fica como está
(dedup via `seen_jobs.json`, que já é mais restrito que 6h já que o loop roda a
cada 30min).

Testado `python-jobspy` ao vivo (Indeed e LinkedIn, busca real em Brasília):
funciona, retorna vaga real com `date_posted`. A lib tem parâmetro `hours_old`
nativo que filtra na origem — não precisamos recalcular data na mão.

## Design

### Config novo (`main.py`)

```python
JOBBOARD_SITES = ["linkedin", "indeed", "glassdoor"]
JOBBOARD_HOURS_OLD = 6
JOBBOARD_RESULTS_WANTED = 50
BRASILIA_LOCATION = "Brasília, DF, Brazil"
JOBBOARD_SEARCH_TERM = "tecnologia"

PLATFORM_ICONS = {
    "gupy": "🚀",
    "linkedin": "💼",
    "indeed": "🔍",
    "glassdoor": "🏢",
}
```

### Busca

Duas chamadas `jobspy.scrape_jobs()` por ciclo de checagem (não uma por site — a
lib já aceita `site_name` como lista e faz as 3 plataformas numa chamada):

1. Presencial/híbrido: `location=BRASILIA_LOCATION, is_remote=False`
2. Remoto: `location="Brazil", is_remote=True`

Ambas com `site_name=JOBBOARD_SITES`, `search_term=JOBBOARD_SEARCH_TERM`,
`country_indeed="brazil"`, `hours_old=JOBBOARD_HOURS_OLD`,
`results_wanted=JOBBOARD_RESULTS_WANTED`.

### Filtro

Reusa `matches_keywords(title)` e `is_tech_job(title, "")` já existentes
(department não vem confiável do jobspy, então passa string vazia — mesmo
fallback que já existiria se Gupy não mandasse department).

### Dedup

Mesmo `seen_jobs.json` (`set` compartilhado). ID vira `f"{site}_{job_id}"`
(usa a coluna `id` do DataFrame do jobspy, cai pro `job_url` se vier vazio)
pra não colidir com IDs numéricos do Gupy nem entre plataformas.

### Estrutura de dados

`collect_new_jobs()` passa a combinar:
- lista atual do Gupy (sem mudança)
- nova lista do jobboard: `{"id", "company", "title", "url", "city", "type", "source"}`

`source` guarda o nome da plataforma (`"gupy"`, `"linkedin"`, `"indeed"`,
`"glassdoor"`) pra escolher o ícone no embed.

### Erros

`try/except` em volta de cada chamada `scrape_jobs()`, loga e segue com lista
vazia se falhar (bloqueio/captcha) — mesmo padrão do `fetch_gupy_jobs` atual.
Risco real: produção roda no Render (IP de datacenter), LinkedIn/Indeed
bloqueiam esse tipo de IP mais que rede residencial — pode falhar em prod
mesmo funcionando localmente. Sem mitigação nesta primeira versão (proxy fica
pra depois se acontecer).

### Discord embed

Mesmo formato atual, com ícone da plataforma (emoji, `PLATFORM_ICONS[source]`)
prefixado no título do embed. Sem dependência de URL externa de logo.

### Testes

Função pura de filtro/normalização das linhas do jobspy
(`build_jobboard_entries(rows: list[dict]) -> list[dict]`) recebe dado fake
(sem rede) e é testada em `test_gupy_parsing.py`, mesmo padrão de
`parse_jobs_from_html`. A chamada de rede (`fetch_jobboard_jobs`) fica sem
teste automatizado, igual `fetch_gupy_jobs` hoje.

## Fora de escopo

- Proxy/rotação de IP pra evitar bloqueio em produção.
- Deduplicação de vaga idêntica postada em mais de uma plataforma (mesma vaga
  no LinkedIn e Indeed conta como 2 posts separados).
- Filtro de senioridade diferente do já existente (KEYWORDS).
