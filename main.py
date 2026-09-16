"""
Discord бот для Flux генерации - версия для Railway
Оптимизирован для облачного хостинга
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
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем токен ДО создания бота
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Проверяем токен
if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_TOKEN_HERE":
    print("❌ ОШИБКА: DISCORD_TOKEN не установлен!")
    print("Добавьте переменную окружения DISCORD_TOKEN в Railway")
    sys.exit(1)

print(f"✅ Токен найден: {DISCORD_TOKEN[:20]}...")

# Инициализация бота
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Конфигурация
FLUX_API_URL = "https://api.pollinations.ai/v1/images/generations"
MAX_REQUESTS_PER_HOUR = 10
TIMEOUT_SECONDS = 120

# Стили
STYLE_PRESETS = {
    "realistic": "Photorealistic, professional photography, 8k, detailed, high quality",
    "anime": "Anime style, colorful, detailed character art, vibrant",
    "cyberpunk": "Cyberpunk style, neon lights, glowing details, dark atmosphere",
    "fantasy": "Fantasy art, magical atmosphere, detailed, epic, dramatic lighting",
    "abstract": "Abstract digital art, colorful, surreal, creative composition",
}

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

rate_limiter = RateLimiter(max_requests=MAX_REQUESTS_PER_HOUR)

@bot.event
async def on_ready():
    """Событие при готовности бота"""
    print(f"\n{'='*50}")
    print(f"✅ BOT CONNECTED")
    print(f"{'='*50}")
    print(f"Bot: {bot.user}")
    print(f"ID: {bot.user.id}")
    print(f"Guilds: {len(bot.guilds)}")
    print(f"{'='*50}\n")
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s)")
        for cmd in synced:
            print(f"   - /{cmd.name}")
    except Exception as e:
        print(f"❌ Sync error: {e}")

@bot.event
async def on_error(event, *args, **kwargs):
    """Обработка ошибок"""
    print(f"❌ Error in {event}:")
    import traceback
    traceback.print_exc()

@bot.tree.command(
    name="fluxgen",
    description="Generate image with Flux"
)
@app_commands.describe(
    prompt="Image description (required)",
    photo="Photo URL to enhance (optional)",
    style="Style: realistic, anime, cyberpunk, fantasy, abstract"
)
async def fluxgen(
    interaction: discord.Interaction,
    prompt: str,
    photo: Optional[str] = None,
    style: Optional[str] = None
):
    """Generate image with Flux model"""
    
    # Проверяем рейт-лимит
    if not rate_limiter.is_allowed(interaction.user.id):
        await interaction.response.send_message(
            "❌ Rate limit reached. Try again in ~1 hour",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        # Валидация
        if not prompt or len(prompt) < 3:
            await interaction.followup.send("❌ Prompt too short (min 3 chars)")
            return
        
        if len(prompt) > 1000:
            await interaction.followup.send("❌ Prompt too long (max 1000 chars)")
            return
        
        # Применяем стиль
        full_prompt = prompt
        if style and style.lower() in STYLE_PRESETS:
            full_prompt = f"{prompt}, {STYLE_PRESETS[style.lower()]}"
        
        seed = random.randint(0, 999999)
        
        # Подготавливаем запрос
        params = {
            "prompt": full_prompt,
            "model": "flux",
            "seed": seed,
            "enhance": True,
            "width": 1024,
            "height": 1024
        }
        
        if photo:
            if not photo.startswith(("http://", "https://")) or len(photo) < 10:
                await interaction.followup.send("❌ Invalid photo URL")
                return
            params["image"] = photo
            params["strength"] = 0.7
        
        print(f"🎨 Generating for {interaction.user}: {prompt[:50]}...")
        
        # Отправляем запрос
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    FLUX_API_URL,
                    json=params,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"API Error: {response.status} - {error_text[:100]}")
                        await interaction.followup.send(
                            f"❌ API Error ({response.status})"
                        )
                        return
                    
                    image_data = await response.read()
            
            except asyncio.TimeoutError:
                await interaction.followup.send("❌ Timeout (>120s). Try again.")
                return
            except Exception as e:
                print(f"Request error: {e}")
                await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
                return
        
        # Создаём файл
        image_file = discord.File(
            io.BytesIO(image_data),
            filename="flux_generated.png"
        )
        
        # Эмбед
        embed = discord.Embed(
            title="🎨 Flux Generated Image",
            description=f"**Prompt:** {prompt}",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="🌱 Seed", value=f"`{seed}`", inline=True)
        
        if style and style.lower() in STYLE_PRESETS:
            embed.add_field(name="🎭 Style", value=f"`{style.capitalize()}`", inline=True)
        
        if photo:
            embed.add_field(name="📸 Source Photo", value="✅ Used", inline=True)
        
        remaining = rate_limiter.get_remaining(interaction.user.id)
        embed.add_field(
            name="📊 Remaining",
            value=f"`{remaining}/{MAX_REQUESTS_PER_HOUR}`",
            inline=True
        )
        
        embed.set_image(url="attachment://flux_generated.png")
        embed.set_footer(text="Powered by Pollinations.AI")
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.followup.send(embed=embed, file=image_file)
        print(f"✅ Generated successfully (seed: {seed})")
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        try:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
        except:
            pass

@bot.tree.command(name="styles", description="Show available styles")
async def styles(interaction: discord.Interaction):
    """Show available styles"""
    embed = discord.Embed(
        title="🎭 Available Styles",
        description="Use in /fluxgen with style parameter",
        color=discord.Color.purple()
    )
    
    for style_name, style_desc in STYLE_PRESETS.items():
        embed.add_field(
            name=f"**{style_name.capitalize()}**",
            value=f"`{style_desc[:80]}...`",
            inline=False
        )
    
    embed.set_footer(text="Example: /fluxgen prompt: 'girl' style: cyberpunk")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mystats", description="Your usage stats")
async def mystats(interaction: discord.Interaction):
    """Show user statistics"""
    remaining = rate_limiter.get_remaining(interaction.user.id)
    used = MAX_REQUESTS_PER_HOUR - remaining
    percentage = (used / MAX_REQUESTS_PER_HOUR) * 100
    
    embed = discord.Embed(
        title="📊 Your Statistics",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 User", value=interaction.user.mention, inline=False)
    embed.add_field(name="🔧 Used", value=f"{used}/{MAX_REQUESTS_PER_HOUR}", inline=True)
    embed.add_field(name="📈 Progress", value=f"{percentage:.1f}%", inline=True)
    
    bar_length = 20
    filled = int(bar_length * used / MAX_REQUESTS_PER_HOUR)
    bar = "█" * filled + "░" * (bar_length - filled)
    embed.add_field(name="Bar", value=f"`{bar}`", inline=False)
    
    if remaining > 0:
        embed.add_field(name="⏰ Remaining", value=f"{remaining} requests", inline=False)
    else:
        embed.add_field(name="❌ Limit Reached", value="Try again in ~1 hour", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="help", description="Help and info")
async def help_command(interaction: discord.Interaction):
    """Show help"""
    embed = discord.Embed(
        title="🤖 Flux Generator Bot",
        description="Generate images with Flux model",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="/fluxgen",
        value="Generate image\n• prompt (required)\n• photo (optional)\n• style (optional)",
        inline=False
    )
    
    embed.add_field(
        name="/styles",
        value="Show available styles",
        inline=False
    )
    
    embed.add_field(
        name="/mystats",
        value="Your usage statistics",
        inline=False
    )
    
    embed.add_field(
        name="Limits",
        value=f"• {MAX_REQUESTS_PER_HOUR} requests/hour\n• Timeout: {TIMEOUT_SECONDS}s",
        inline=False
    )
    
    embed.set_footer(text="Powered by Pollinations.AI")
    await interaction.response.send_message(embed=embed)

# Запуск бота
if __name__ == "__main__":
    print("🚀 Starting bot...")
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        sys.exit(1)
    
