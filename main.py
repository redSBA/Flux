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

WATERMARK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watermark.png")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

_watermark_image = None

# Запрещённые слова (NSFW)
NSFW_WORDS = [
    "nsfw", "nude", "naked", "porn", "xxx", "sex", "hentai", "ero",
    "голая", "голый", "секс", "порн", "эротика", "сиськи", "грудь",
    "вагина", "пенис", "член", "трах", "ебл", "18+", "без одежды",
    "без белья", "обнажённ", "обнаженн", "pussy", "dick", "boobs",
    "tits", "ass", "fuck", "blowjob", "cum"
]

def get_watermark():
    global _watermark_image
    if _watermark_image is not None:
        return _watermark_image

    if not os.path.exists(WATERMARK_PATH):
        raise FileNotFoundError(f"watermark.png не найден: {WATERMARK_PATH}")

    img = Image.open(WATERMARK_PATH).convert("RGBA")

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Делаем непрозрачным
    r, g, b, a = img.split()
    a = a.point(lambda p: 255 if p > 10 else 0)
    img = Image.merge("RGBA", (r, g, b, a))

    _watermark_image = img
    print(f"✅ Ватермарк загружен: {img.size}")
    return _watermark_image

def apply_watermark(base_image: Image.Image, watermark: Image.Image) -> Image.Image:
    base = base_image.convert("RGBA")

    # \~55% ширины
    target_width = int(base.width * 0.55)
    ratio = target_width / watermark.width
    target_height = int(watermark.height * ratio)
    wm = watermark.resize((target_width, target_height), Image.LANCZOS)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
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
        get_watermark()
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

    # --- Анти-NSFW фильтр ---
    prompt_lower = prompt.lower()
    if any(word in prompt_lower for word in NSFW_WORDS):
        await interaction.followup.send(
            "❌ Этот промпт запрещён (NSFW).",
            ephemeral=True
        )
        return
    # ------------------------

    seed = random.randint(0, 999_999_999)

    params = {
        "model": "flux",
        "enhance": "true",
        "seed": str(seed),
        "nologo": "true",
        "safe": "true",       # защита от NSFW на стороне API
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
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    await interaction.followup.send(
                        f"❌ API ошибка ({resp.status}):\n```{text[:300]}```"
                    )
                    return
                image_data = await resp.read()

        generated = Image.open(io.BytesIO(image_data))
        result = apply_watermark(generated, get_watermark())

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
