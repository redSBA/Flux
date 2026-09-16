import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import random
import io
import os
from urllib.parse import quote
from typing import Optional

# Railway сам подставляет переменные окружения
TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN не найден! Добавь его в Variables на Railway.")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} slash-команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации команд: {e}")

@bot.tree.command(name="fluxgen", description="Генерация изображения через Flux (Pollinations.AI)")
@app_commands.describe(
    prompt="Описание изображения (обязательно)",
    photo="Референс-фото (необязательно)"
)
async def fluxgen(
    interaction: discord.Interaction,
    prompt: str,
    photo: Optional[discord.Attachment] = None
):
    await interaction.response.defer(thinking=True)

    seed = random.randint(0, 999_999_999)

    params = {
        "model": "flux",
        "enhance": "true",
        "seed": str(seed),
        "nologo": "true",
        "width": "1024",
        "height": "1024",
    }

    if photo is not None:
        if not photo.content_type or not photo.content_type.startswith("image/"):
            await interaction.followup.send("❌ Файл должен быть изображением!", ephemeral=True)
            return
        params["image"] = photo.url

    encoded_prompt = quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    await interaction.followup.send(
                        f"❌ Ошибка API ({resp.status}):\n```{error_text[:400]}```"
                    )
                    return

                image_data = await resp.read()

        file = discord.File(io.BytesIO(image_data), filename=f"flux_{seed}.png")

        embed = discord.Embed(
            title="Flux Generation",
            description=f"**Prompt:** {prompt}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Seed", value=f"`{seed}`", inline=True)
        embed.add_field(name="Enhance", value="✅ Включён", inline=True)
        if photo:
            embed.add_field(name="Референс", value="Да", inline=True)
        embed.set_image(url=f"attachment://flux_{seed}.png")
        embed.set_footer(text="Pollinations.AI • Flux • Railway")

        await interaction.followup.send(embed=embed, file=file)

    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: `{str(e)[:300]}`")

if __name__ == "__main__":
    bot.run(TOKEN)
