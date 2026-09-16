"""
Discord Bot for Flux - Railway Stable Version
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

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN not set!")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

FLUX_API_URL = "https://api.pollinations.ai/v1/images/generations"
MAX_REQUESTS_PER_HOUR = 10
TIMEOUT_SECONDS = 120

STYLE_PRESETS = {
    "realistic": "Photorealistic, professional photography, 8k",
    "anime": "Anime style, colorful, detailed",
    "cyberpunk": "Cyberpunk style, neon lights",
    "fantasy": "Fantasy art, magical atmosphere",
    "abstract": "Abstract digital art, colorful",
}

class RateLimiter:
    def __init__(self, max_requests=10, time_window_minutes=60):
        self.max_requests = max_requests
        self.time_window = timedelta(minutes=time_window_minutes)
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id):
        now = datetime.now()
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]
        
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        self.requests[user_id].append(now)
        return True
    
    def get_remaining(self, user_id):
        now = datetime.now()
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]
        return self.max_requests - len(self.requests[user_id])

rate_limiter = RateLimiter(max_requests=MAX_REQUESTS_PER_HOUR)

@bot.event
async def on_ready():
    print(f"\n✅ BOT CONNECTED: {bot.user}\n")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands\n")
    except Exception as e:
        print(f"❌ Sync error: {e}\n")

@bot.tree.command(name="fluxgen", description="Generate image with Flux")
@app_commands.describe(
    prompt="Image description",
    photo="Photo URL (optional)",
    style="Style: realistic, anime, cyberpunk, fantasy, abstract"
)
async def fluxgen(interaction, prompt, photo=None, style=None):
    if not rate_limiter.is_allowed(interaction.user.id):
        await interaction.response.send_message(
            "❌ Rate limit reached. Try again in ~1 hour",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        if not prompt or len(prompt) < 3:
            await interaction.followup.send("❌ Prompt too short")
            return
        
        full_prompt = prompt
        if style and style.lower() in STYLE_PRESETS:
            full_prompt = f"{prompt}, {STYLE_PRESETS[style.lower()]}"
        
        seed = random.randint(0, 999999)
        
        params = {
            "prompt": full_prompt,
            "model": "flux",
            "seed": seed,
            "enhance": True,
            "width": 1024,
            "height": 1024
        }
        
        if photo:
            params["image"] = photo
            params["strength"] = 0.7
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                FLUX_API_URL,
                json=params,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
            ) as response:
                if response.status != 200:
                    await interaction.followup.send(f"❌ API Error ({response.status})")
                    return
                
                image_data = await response.read()
        
        image_file = discord.File(io.BytesIO(image_data), filename="flux.png")
        
        embed = discord.Embed(
            title="🎨 Flux Generated",
            description=f"**Prompt:** {prompt}",
            color=discord.Color.purple()
        )
        embed.add_field(name="🌱 Seed", value=f"`{seed}`", inline=True)
        if style and style.lower() in STYLE_PRESETS:
            embed.add_field(name="🎭 Style", value=f"`{style}`", inline=True)
        remaining = rate_limiter.get_remaining(interaction.user.id)
        embed.add_field(name="📊 Remaining", value=f"`{remaining}/{MAX_REQUESTS_PER_HOUR}`", inline=True)
        embed.set_image(url="attachment://flux.png")
        
        await interaction.followup.send(embed=embed, file=image_file)
        
    except Exception as e:
        try:
            await interaction.followup.send(f"❌ Error: {str(e)[:100]}")
        except:
            pass

@bot.tree.command(name="ping", description="Check status")
async def ping(interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! {latency}ms")

@bot.tree.command(name="styles", description="Show styles")
async def styles(interaction):
    embed = discord.Embed(title="🎭 Styles", color=discord.Color.purple())
    for name, desc in STYLE_PRESETS.items():
        embed.add_field(name=name.capitalize(), value=f"`{desc}`", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="Help")
async def help_cmd(interaction):
    embed = discord.Embed(title="🤖 Flux Bot", color=discord.Color.gold())
    embed.add_field(name="/fluxgen", value="Generate image", inline=False)
    embed.add_field(name="/styles", value="Show styles", inline=False)
    embed.add_field(name="/ping", value="Check status", inline=False)
    await interaction.response.send_message(embed=embed)

print("🚀 Starting bot...")
bot.run(DISCORD_TOKEN)
