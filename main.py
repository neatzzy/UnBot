"""
Configuração necessária:
    DISCORD_TOKEN   -> token do seu bot
    DISCORD_CHANNEL_ID -> ID do canal onde as vagas serão postadas
"""

import asyncio
import json
import os
import re
from pathlib import Path

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ------------------------------------------------------------------
# CONFIGURAÇÃO
# ------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))  # ID do canal do Discord
CHECK_INTERVAL_MINUTES = 30

# Porta HTTP exigida pelo Render (Web Service) para o health check.
# O Render injeta a variável PORT automaticamente; 8080 é usado como fallback local.
PORT = int(os.getenv("PORT", "8080"))

# Palavras-chave que definem "estágio/júnior"
KEYWORDS = [
    "estágio", "estagio", "estagiário", "estagiario",
    "júnior", "junior", "trainee", "jovem aprendiz",
    "jr"
]

# Palavras-chave que definem "área de tecnologia" (checadas no título e no
# departamento da vaga, já que o campo "department" da Gupy não segue um
# padrão único entre empresas).
TECH_KEYWORDS = [
    "tecnologia", "tecnologia da informação", "t.i.", " ti ",
    "desenvolvedor", "desenvolvimento de software", "desenvolvimento de sistemas",
    "engenheiro de software", "engenharia de software", "programador", "programação",
    "software", "sistemas", "dados", "data", "devops", "sre",
    "segurança da informação", "cibersegurança", "cyber", "cloud",
    "infraestrutura de ti", "suporte técnico", "helpdesk", "help desk",
    "banco de dados", "qa", "quality assurance", "full stack", "fullstack",
    "backend", "frontend", "front-end", "back-end", "mobile developer",
    "redes de computadores", "scrum", "product design", "ux", "ui designer",
]

# Slugs de empresas no Gupy. O slug é o nome que aparece na URL da página de
# carreiras: https://<slug>.gupy.io  ou  https://portal.gupy.io/empresas/<slug>
# Descubra o slug de uma empresa acessando a página de vagas dela e olhando a URL.
def load_slugs(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return[line.strip() for line in f if line.strip()]

GUPY_CAREER_PAGE_URL = "https://{slug}.gupy.io/"

# A Gupy renderiza a página de carreiras em Next.js e embute a lista de
# vagas como JSON dentro de <script id="__NEXT_DATA__">. A antiga API REST
# pública (portal.api.gupy.io/api/v1/jobs) foi descontinuada e hoje responde
# 404 para qualquer request, por isso extraímos os dados direto do HTML.
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

SEEN_JOBS_FILE = Path("seen_jobs.json")

# ------------------------------------------------------------------
# PERSISTÊNCIA (evita re-postar a mesma vaga)
# ------------------------------------------------------------------

def load_seen_jobs() -> set:
    if SEEN_JOBS_FILE.exists():
        return set(json.loads(SEEN_JOBS_FILE.read_text()))
    return set()


def save_seen_jobs(seen: set) -> None:
    SEEN_JOBS_FILE.write_text(json.dumps(list(seen)))


# ------------------------------------------------------------------
# BUSCA DE VAGAS
# ------------------------------------------------------------------

def matches_keywords(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in KEYWORDS)


def is_tech_job(title: str, department: str) -> bool:
    text = f" {title.lower()} {department.lower()} "
    return any(kw in text for kw in TECH_KEYWORDS)


def parse_jobs_from_html(html: str) -> list[dict]:
    """Extrai a lista de vagas embutida no JSON da página Next.js da Gupy."""
    match = NEXT_DATA_RE.search(html)
    if not match:
        return []
    data = json.loads(match.group(1))
    return data.get("props", {}).get("pageProps", {}).get("jobs", [])


async def fetch_gupy_jobs(session: aiohttp.ClientSession, slug: str) -> list[dict]:
    """Busca vagas públicas de uma empresa no Gupy."""
    url = GUPY_CAREER_PAGE_URL.format(slug=slug)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
            return parse_jobs_from_html(html)
    except Exception as e:
        print(f"[erro] falha ao buscar vagas de '{slug}': {e}")
        return []


async def collect_new_jobs(seen: set) -> list[dict]:
    """Percorre todas as empresas configuradas e retorna vagas novas que batem com as keywords."""
    new_jobs = []
    GUPY_COMPANY_SLUGS = load_slugs('slugs_empresas.txt')
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        for slug in GUPY_COMPANY_SLUGS:
            jobs = await fetch_gupy_jobs(session, slug)
            for job in jobs:
                job_id = str(job.get("id"))
                title = job.get("title", "")
                department = job.get("department", "")
                if job_id in seen:
                    continue
                if not matches_keywords(title):
                    continue
                if not is_tech_job(title, department):
                    continue
                address = (job.get("workplace") or {}).get("address") or {}
                new_jobs.append({
                    "id": job_id,
                    "company": slug,
                    "title": title,
                    "url": f"https://{slug}.gupy.io/job/{job_id}",
                    "city": (address.get("city") or "Não informado"),
                    "type": (job.get("type") or ""),
                })
                seen.add(job_id)
    return new_jobs


# ------------------------------------------------------------------
# SERVIDOR HTTP (health check do Render)
# ------------------------------------------------------------------

async def handle_health(request: web.Request) -> web.Response:
    return web.Response(text="UnBot está rodando.")


async def start_web_server() -> None:
    """Sobe um servidor HTTP mínimo para o Render detectar a porta aberta."""
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[ok] servidor HTTP de health check escutando na porta {PORT}")


# ------------------------------------------------------------------
# BOT DISCORD
# ------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True  # necessário para o bot ler o prefixo "!" nas mensagens
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    if not check_jobs_loop.is_running():
        check_jobs_loop.start()


@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def check_jobs_loop():
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print("[erro] CHANNEL_ID inválido ou bot sem acesso ao canal.")
        return

    seen = load_seen_jobs()
    new_jobs = await collect_new_jobs(seen)
    save_seen_jobs(seen)

    for job in new_jobs:
        embed = discord.Embed(
            title=job["title"],
            url=job["url"] or discord.Embed.Empty,
            description=f"**Empresa:** {job['company']}\n**Local:** {job['city']}",
            color=0x2ECC71,
        )
        await channel.send(embed=embed)

    if new_jobs:
        print(f"[ok] {len(new_jobs)} vaga(s) nova(s) postada(s).")
    else:
        print("[ok] nenhuma vaga nova nesta checagem.")


@bot.command(name="checarvagas")
async def checar_vagas_cmd(ctx):
    """Comando manual: !checarvagas — força uma checagem imediata."""
    await ctx.send("Checando vagas agora...")
    seen = load_seen_jobs()
    new_jobs = await collect_new_jobs(seen)
    save_seen_jobs(seen)

    if not new_jobs:
        await ctx.send("Nenhuma vaga nova encontrada.")
        return

    for job in new_jobs:
        embed = discord.Embed(
            title=job["title"],
            url=job["url"] or discord.Embed.Empty,
            description=f"**Empresa:** {job['company']}\n**Local:** {job['city']}",
            color=0x2ECC71,
        )
        await ctx.send(embed=embed)


async def main() -> None:
    await start_web_server()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    if DISCORD_TOKEN == "COLOQUE_SEU_TOKEN_AQUI":
        raise SystemExit("Defina DISCORD_TOKEN (variável de ambiente) antes de rodar.")
    asyncio.run(main())