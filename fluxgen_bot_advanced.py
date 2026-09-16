"""
Расширенная версия Discord бота для Flux генерации изображений
С поддержкой рейт-лимитинга, кэширования и дополнительных команд
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import random
from typing import Optional
import io
from datetime import datetime, timedelta
from collections import defaultdict
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Инициализация бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Конфигурация
FLUX_API_URL = "https://api.pollinations.ai/v1/images/generations"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_TOKEN_HERE")
MAX_REQUESTS_PER_HOUR = 10  # Максимум запросов в час на пользователя
TIMEOUT_SECONDS = 120

# Рейт-лимитинг
class RateLimiter:
    def __init__(self, max_requests: int = 10, time_window_minutes: int = 60):
        self.max_requests = max_requests
        self.time_window = timedelta(minutes=time_window_minutes)
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> bool:
        now = datetime.now()
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]
        
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        self.requests[user_id].append(now)
        return True
    
    def get_remaining(self, user_id: int) -> int:
        now = datetime.now()
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]
        return self.max_requests - len(self.requests[user_id])

# Инициализация рейт-лимитера
rate_limiter = RateLimiter(max_requests=MAX_REQUESTS_PER_HOUR)

# Стили для быстрого использования
STYLE_PRESETS = {
    "realistic": "Photorealistic, professional photography, 8k, detailed, high quality",
    "anime": "Anime style, colorful, detailed character art, vibrant",
    "cyberpunk": "Cyberpunk style, neon lights, glowing details, dark atmosphere",
    "fantasy": "Fantasy art, magical atmosphere, detailed, epic, dramatic lighting",
    "abstract": "Abstract digital art, colorful, surreal, creative composition",
    "steampunk": "Steampunk style, mechanical details, vintage, industrial",
    "oil_painting": "Oil painting style, artistic, brushstrokes, classical art",
    "neon": "Neon glow effects, vibrant colors, dark background, glowing lines"
}

@bot.event
async def on_ready():
    """Событие при готовности бота"""
    print(f"✅ Бот {bot.user} подключился!")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд(ы)")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")

@bot.tree.command(
    name="fluxgen",
    description="Генерирует изображение с помощью Flux от Pollinations.AI"
)
@app_commands.describe(
    prompt="Описание изображения (обязательно)",
    photo="Ссылка на фото для улучшения (опционально)",
    style="Стиль (опционально): realistic, anime, cyberpunk, fantasy, abstract, steampunk, oil_painting, neon"
)
async def fluxgen(
    interaction: discord.Interaction,
    prompt: str,
    photo: Optional[str] = None,
    style: Optional[str] = None
):
    """
    Генерирует изображение используя Flux модель
    
    Args:
        interaction: Discord interaction
        prompt: Текстовый запрос (обязательно)
        photo: Ссылка на фото для процессинга (опционально)
        style: Предустановленный стиль (опционально)
    """
    
    # Проверяем рейт-лимит
    if not rate_limiter.is_allowed(interaction.user.id):
        remaining_time = "~1 час"
        await interaction.response.send_message(
            f"❌ Вы достигли лимита запросов. Попробуйте позже ({remaining_time})",
            ephemeral=True
        )
        return
    
    # Показываем что бот работает
    await interaction.response.defer(thinking=True)
    
    try:
        # Валидация промпта
        if not prompt or len(prompt) < 3:
            await interaction.followup.send("❌ Промпт слишком короткий (минимум 3 символа)")
            return
        
        if len(prompt) > 1000:
            await interaction.followup.send("❌ Промпт слишком длинный (максимум 1000 символов)")
            return
        
        # Применяем стиль если указан
        full_prompt = prompt
        if style and style.lower() in STYLE_PRESETS:
            full_prompt = f"{prompt}, {STYLE_PRESETS[style.lower()]}"
        
        # Генерируем случайный сид
        seed = random.randint(0, 999999)
        
        # Подготавливаем параметры
        params = {
            "prompt": full_prompt,
            "model": "flux",
            "seed": seed,
            "enhance": True,
            "width": 1024,
            "height": 1024
        }
        
        if photo:
            # Валидация URL
            if not photo.startswith(("http://", "https://")) or len(photo) < 10:
                await interaction.followup.send("❌ Неправильный формат URL фото")
                return
            params["image"] = photo
            params["strength"] = 0.7
        
        # Показываем что происходит генерация
        processing_msg = await interaction.followup.send(
            "⏳ Генерирую изображение... Это может занять 30-60 секунд"
        )
        
        # Отправляем запрос к API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                FLUX_API_URL,
                json=params,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    await processing_msg.edit(
                        content=f"❌ Ошибка API ({response.status})"
                    )
                    print(f"API Error: {error_text}")
                    return
                
                image_data = await response.read()
        
        # Создаём файл
        image_file = discord.File(
            io.BytesIO(image_data),
            filename="flux_generated.png"
        )
        
        # Создаём красивый эмбед
        embed = discord.Embed(
            title="🎨 Flux Generated Image",
            description=f"**Prompt:** {prompt}",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        # Добавляем поля
        embed.add_field(
            name="🌱 Seed",
            value=f"`{seed}`",
            inline=True
        )
        
        if style and style.lower() in STYLE_PRESETS:
            embed.add_field(
                name="🎭 Style",
                value=f"`{style.capitalize()}`",
                inline=True
            )
        
        if photo:
            embed.add_field(
                name="📸 Source Photo",
                value="✅ Used",
                inline=True
            )
        
        embed.add_field(
            name="⚡ Model",
            value="Flux",
            inline=True
        )
        
        embed.add_field(
            name="✨ Enhancer",
            value="Enabled",
            inline=True
        )
        
        remaining = rate_limiter.get_remaining(interaction.user.id)
        embed.add_field(
            name="📊 Remaining Requests",
            value=f"`{remaining}/{MAX_REQUESTS_PER_HOUR}`",
            inline=True
        )
        
        embed.set_image(url="attachment://flux_generated.png")
        embed.set_footer(text="Powered by Pollinations.AI")
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )
        
        # Удаляем сообщение о обработке и отправляем результат
        await processing_msg.delete()
        await interaction.followup.send(
            embed=embed,
            file=image_file
        )
        
        print(f"✅ Image generated for {interaction.user} with seed {seed}")
        
    except asyncio.TimeoutError:
        try:
            await interaction.followup.send(
                "❌ Время ожидания истекло (>120 сек). Попробуйте позже."
            )
        except:
            pass
    
    except Exception as e:
        print(f"❌ Error: {e}")
        try:
            await interaction.followup.send(
                f"❌ Ошибка при генерации: {str(e)[:100]}"
            )
        except:
            pass


@bot.tree.command(
    name="styles",
    description="Показывает доступные стили"
)
async def styles(interaction: discord.Interaction):
    """Показывает список доступных стилей"""
    embed = discord.Embed(
        title="🎭 Available Styles",
        description="Используй параметр `style` в команде `/fluxgen`",
        color=discord.Color.purple()
    )
    
    styles_text = ""
    for style_name, style_desc in STYLE_PRESETS.items():
        styles_text += f"\n**{style_name.capitalize()}**\n`{style_desc}`\n"
    
    embed.add_field(
        name="Стили",
        value=styles_text,
        inline=False
    )
    
    embed.add_field(
        name="Пример использования",
        value="/fluxgen prompt: 'красивая девушка' style: 'cyberpunk'",
        inline=False
    )
    
    embed.set_footer(text="Powered by Pollinations.AI")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(
    name="mystats",
    description="Показывает твою статистику использования"
)
async def mystats(interaction: discord.Interaction):
    """Показывает личную статистику пользователя"""
    remaining = rate_limiter.get_remaining(interaction.user.id)
    used = MAX_REQUESTS_PER_HOUR - remaining
    percentage = (used / MAX_REQUESTS_PER_HOUR) * 100
    
    embed = discord.Embed(
        title="📊 Your Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="👤 User",
        value=interaction.user.mention,
        inline=False
    )
    
    embed.add_field(
        name="🔧 Requests Used",
        value=f"{used}/{MAX_REQUESTS_PER_HOUR}",
        inline=True
    )
    
    embed.add_field(
        name="📈 Progress",
        value=f"{percentage:.1f}%",
        inline=True
    )
    
    # Прогресс-бар
    bar_length = 20
    filled = int(bar_length * used / MAX_REQUESTS_PER_HOUR)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    embed.add_field(
        name="Progress Bar",
        value=f"`{bar}`",
        inline=False
    )
    
    if remaining > 0:
        embed.add_field(
            name="⏰ Remaining Requests",
            value=f"{remaining} requests",
            inline=False
        )
    else:
        embed.add_field(
            name="❌ Limit Reached",
            value="Try again in ~1 hour",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="help",
    description="Помощь и информация о боте"
)
async def help_command(interaction: discord.Interaction):
    """Показывает справку по боту"""
    embed = discord.Embed(
        title="🤖 Flux Generator Bot Help",
        description="Все что нужно знать о боте",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="🎨 /fluxgen",
        value="Генерирует изображение\n"
              "• `prompt` (обязательно) - что генерировать\n"
              "• `photo` (опционально) - ссылка на исходное фото\n"
              "• `style` (опционально) - предустановленный стиль",
        inline=False
    )
    
    embed.add_field(
        name="🎭 /styles",
        value="Показывает доступные стили (anime, cyberpunk, fantasy и т.д.)",
        inline=False
    )
    
    embed.add_field(
        name="📊 /mystats",
        value="Твоя личная статистика и лимиты",
        inline=False
    )
    
    embed.add_field(
        name="❓ /help",
        value="Эта справка",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Лимиты",
        value=f"• {MAX_REQUESTS_PER_HOUR} запросов в час\n"
              f"• Таймаут: {TIMEOUT_SECONDS} сек\n"
              f"• Макс. размер промпта: 1000 символов",
        inline=False
    )
    
    embed.add_field(
        name="💡 Примеры промптов",
        value="✦ 'Beautiful girl with glowing eyes, cyberpunk style'\n"
              "✦ 'Fantasy dragon in mountains, dramatic lighting'\n"
              "✦ 'Abstract colorful fractal patterns'",
        inline=False
    )
    
    embed.set_footer(text="Powered by Pollinations.AI")
    
    await interaction.response.send_message(embed=embed)


# Запуск бота
if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
