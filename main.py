import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import random
import io
import os
from urllib.parse import quote
from typing import Optional
from PIL import Image, ImageDraw

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN не найден!")

WATERMARK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watermark.png")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

_watermark_image = None

def get_watermark():
    global _watermark_image
    if _watermark_image is not None:
        return _watermark_image

    print(f"Ищем ватермарк: {WATERMARK_PATH}", flush=True)
    print(f"Файл существует: {os.path.exists(WATERMARK_PATH)}", flush=True)

    if not os.path.exists(WATERMARK_PATH):
        raise FileNotFoundError(f"watermark.png не найден: {WATERMARK_PATH}")

    img = Image.open(WATERMARK_PATH).convert("RGBA")
    print(f"Оригинал ватермарка: {img.size}, mode={img.mode}", flush=True)

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        print(f"После обрезки: {img.size}", flush=True)

    # Делаем почти полностью непрозрачным
    r, g, b, a = img.split()
    a = a.point(lambda p: 255 if p > 10 else 0)
    img = Image.merge("RGBA", (r, g, b, a))

    _watermark_image = img
    print(f"✅ Ватермарк готов: {img.size}", flush=True)
    return _watermark_image

def apply_watermark(base_image: Image.Image, watermark: Image.Image) -> Image.Image:
    base = base_image.convert("RGBA")
    print(f"Картинка: {base.size}", flush=True)

    # Красный квадрат для теста (потом уберём)
    draw = ImageDraw.Draw(base)
    draw.rectangle(
        [base.width - 130, base.height - 130, base.width - 20, base.height - 20],
        fill=(255, 0, 0, 220)
    )
    print("Красный квадрат нарисован", flush=True)

    # Ватермарк \~60% ширины
    target_width = int(base.width * 0.60)
    ratio = target_width / watermark.width
    target_height = int(watermark.height * ratio)
    wm = watermark.resize((target_width, target_height), Image.LANCZOS)
    print(f"Ватермарк масштабирован: {wm.size}", flush=True)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    padding = 15
    x = base.width - wm.width - padding
    y = base.height - wm.height - padding
    print(f"Позиция ватермарка: ({x}, {y})", flush=True)

    overlay.paste(wm, (x, y), wm)
    result = Image.alpha_composite(base, overlay)
    print("Ватермарк наложен", flush=True)
    return result.convert("RGB")

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}", flush=True)
    try:
        get_watermark()
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд", flush=True)
    except Exception as e:
        print(f"❌ Ошибка при старте: {e}", flush=True)

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

        print(f"Получена картинка: {len(image_data)} байт", flush=True)
        generated = Image.open(io.BytesIO(image_data))

        watermark = get_watermark()
        result = apply_watermark(generated, watermark)

        buffer = io.BytesIO()
        result.save(buffer, format="PNG")
        buffer.seek(0)

        file = discord.File(buffer, filename=f"flux_{seed}.png")

        embed = discord.Embed(
            title="Flux Generation",
            description=f"**Prompt:** {prompt}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Seed", value=f"`{seed}`", inline=True)
        embed.add_field(name="Enhance", value="✅ Включён", inline=True)
        embed.set_image(url=f"attachment://flux_{seed}.png")
        embed.set_footer(text="TEST WATERMARK")

        await interaction.followup.send(embed=embed, file=file)
        print("Картинка отправлена в Discord", flush=True)

    except Exception as e:
        print(f"❌ Ошибка: {e}", flush=True)
        await interaction.followup.send(f"❌ Ошибка: `{str(e)[:250]}`")

if __name__ == "__main__":
    bot.run(TOKEN)
