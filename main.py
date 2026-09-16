import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import random
import io
import os
from urllib.parse import quote
from typing import Optional
from PIL import Image

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN не найден!")

WATERMARK_URL = "https://raw.githubusercontent.com/redSBA/Ai/refs/heads/main/%D0%91%D0%B5%D0%B7%20%D0%BD%D0%B0%D0%B7%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F1_20260901175659.png"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

_watermark_image: Image.Image | None = None

async def get_watermark() -> Image.Image:
    global _watermark_image
    if _watermark_image is not None:
        return _watermark_image

    async with aiohttp.ClientSession() as session:
        async with session.get(WATERMARK_URL) as resp:
            if resp.status != 200:
                raise Exception(f"Не удалось скачать ватермарк (код {resp.status})")
            data = await resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGBA")

            # Обрезаем пустые края
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)

            # Усиливаем непрозрачность (делаем ярче)
            r, g, b, a = img.split()
            a = a.point(lambda p: min(255, int(p * 2.2)) if p > 15 else 0)
            img = Image.merge("RGBA", (r, g, b, a))

            _watermark_image = img
            print(f"✅ Ватермарк загружен и усилен: {img.size}")
            return _watermark_image

def apply_watermark(base_image: Image.Image, watermark: Image.Image) -> Image.Image:
    base = base_image.convert("RGBA")

    # Делаем ватермарк \~55% ширины картинки (крупно)
    target_width = int(base.width * 0.55)
    ratio = target_width / watermark.width
    target_height = int(watermark.height * ratio)
    wm = watermark.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Создаём прозрачный слой
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))

    # Правый нижний угол
    padding = 18
    x = base.width - wm.width - padding
    y = base.height - wm.height - padding

    overlay.paste(wm, (x, y), wm)

    result = Image.alpha_composite(base, overlay)
    return result.convert("RGB")

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    try:
        await get_watermark()
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка при старте: {e}")

@bot.tree.command(name="fluxgen", description="Генерация изображения через Flux")
@app_commands.describe(
    prompt="Описание изображения",
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
            await interaction.followup.send("❌ Нужно изображение!", ephemeral=True)
            return
        params["image"] = photo.url

    url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    await interaction.followup.send(f"❌ API ошибка ({resp.status}):\n```{text[:300]}```")
                    return
                image_data = await resp.read()

        generated = Image.open(io.BytesIO(image_data))

        # Накладываем ватермарк
        watermark = await get_watermark()
        result = apply_watermark(generated, watermark)

        buffer = io.BytesIO()
        result.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        file = discord.File(buffer, filename=f"flux_{seed}.png")

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
        embed.set_footer(text="Pollinations.AI • Flux")

        await interaction.followup.send(embed=embed, file=file)

    except Exception as e:
        print(f"Ошибка: {e}")
        await interaction.followup.send(f"❌ Ошибка: `{str(e)[:250]}`")

if __name__ == "__main__":
    bot.run(TOKEN)
