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
    raise ValueError("DISCORD_TOKEN не найден! Добавь его в Variables на Railway.")

# Ссылка на ватермарк
WATERMARK_URL = "https://raw.githubusercontent.com/redSBA/Ai/refs/heads/main/%D0%91%D0%B5%D0%B7%20%D0%BD%D0%B0%D0%B7%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F1_20260901175659.png"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Кэш ватермарка (скачиваем один раз)
_watermark_image: Image.Image | None = None

async def get_watermark() -> Image.Image:
    global _watermark_image
    if _watermark_image is not None:
        return _watermark_image

    async with aiohttp.ClientSession() as session:
        async with session.get(WATERMARK_URL) as resp:
            if resp.status != 200:
                raise Exception(f"Не удалось скачать ватермарк: {resp.status}")
            data = await resp.read()
            _watermark_image = Image.open(io.BytesIO(data)).convert("RGBA")
            return _watermark_image

def apply_watermark(base_image: Image.Image, watermark: Image.Image) -> Image.Image:
    """Накладывает ватермарк в правый нижний угол"""
    base = base_image.convert("RGBA")
    
    # Масштабируем ватермарк примерно до 35% ширины картинки
    target_width = int(base.width * 0.35)
    ratio = target_width / watermark.width
    target_height = int(watermark.height * ratio)
    
    wm = watermark.resize((target_width, target_height), Image.Resampling.LANCZOS)
    
    # Позиция — правый нижний угол с отступом
    padding = int(base.width * 0.03)  # 3% отступа
    x = base.width - wm.width - padding
    y = base.height - wm.height - padding
    
    # Накладываем
    base.paste(wm, (x, y), wm)
    return base.convert("RGB")  # Discord лучше ест RGB/PNG без альфы

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user} (ID: {bot.user.id})")
    try:
        # Предзагружаем ватермарк
        await get_watermark()
        print("✅ Ватермарк загружен")
        
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} slash-команд")
    except Exception as e:
        print(f"❌ Ошибка при старте: {e}")

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

        # Открываем сгенерированную картинку
        generated = Image.open(io.BytesIO(image_data))
        
        # Получаем ватермарк и накладываем
        watermark = await get_watermark()
        result = apply_watermark(generated, watermark)

        # Сохраняем в буфер
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
        embed.set_footer(text="Pollinations.AI • Flux • Railway")

        await interaction.followup.send(embed=embed, file=file)

    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: `{str(e)[:300]}`")

if __name__ == "__main__":
    bot.run(TOKEN)
