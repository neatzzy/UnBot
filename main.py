"""
Configuração necessária:
    DISCORD_TOKEN   -> token do seu bot
    DISCORD_CHANNEL_ID -> ID do canal onde as vagas serão postadas
"""

#import asyncio
import json
import os

#import re
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ------------------------------------------------------------------
# CONFIGURAÇÃO
# ------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "COLOQUE_SEU_TOKEN_AQUI")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))  # ID do canal do Discord
CHECK_INTERVAL_MINUTES = 30

# Palavras-chave que definem "estágio/júnior"
KEYWORDS = [
    "estágio", "estagio", "estagiário", "estagiario",
    "júnior", "junior", "trainee", "jovem aprendiz",
]

# Slugs de empresas no Gupy. O slug é o nome que aparece na URL da página de
# carreiras: https://<slug>.gupy.io  ou  https://portal.gupy.io/empresas/<slug>
# Descubra o slug de uma empresa acessando a página de vagas dela e olhando a URL.
GUPY_COMPANY_SLUGS = [
    "nubank",
    "ifood",
    "magazineluiza",
    "stone-pagamentos",
    "vtex",
    "creditas",
    "quintoandar",
    "loft",
    "gympass",
    "hotmart",
    
]

GUPY_API_URL = "https://portal.api.gupy.io/api/v1/jobs?jobName=&offset=0&limit=100&companyName={slug}"

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


async def fetch_gupy_jobs(session: aiohttp.ClientSession, slug: str) -> list[dict]:
    """Busca vagas públicas de uma empresa no Gupy."""
    url = GUPY_API_URL.format(slug=slug)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("data", [])
    except Exception as e:
        print(f"[erro] falha ao buscar vagas de '{slug}': {e}")
        return []


async def collect_new_jobs(seen: set) -> list[dict]:
    """Percorre todas as empresas configuradas e retorna vagas novas que batem com as keywords."""
    new_jobs = []
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        for slug in GUPY_COMPANY_SLUGS:
            jobs = await fetch_gupy_jobs(session, slug)
            for job in jobs:
                job_id = str(job.get("id"))
                title = job.get("name", "")
                if job_id in seen:
                    continue
                if not matches_keywords(title):
                    continue
                new_jobs.append({
                    "id": job_id,
                    "company": slug,
                    "title": title,
                    "url": job.get("careerPageUrl") or job.get("jobUrl") or "",
                    "city": (job.get("city") or "Não informado"),
                    "type": (job.get("type") or ""),
                })
                seen.add(job_id)
    return new_jobs


# ------------------------------------------------------------------
# BOT DISCORD
# ------------------------------------------------------------------

intents = discord.Intents.default()
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


if __name__ == "__main__":
    if DISCORD_TOKEN == "COLOQUE_SEU_TOKEN_AQUI":
        raise SystemExit("Defina DISCORD_TOKEN (variável de ambiente) antes de rodar.")
    bot.run(DISCORD_TOKEN)