import random
import discord
from discord.ext import commands
from datetime import datetime
import os

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[OK] 登入成功: {bot.user}")

@bot.command()
async def 抽(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        vc = ctx.author.voice.channel
        members = [m.display_name for m in vc.members if not m.bot]
        if len(members) < 2:
            await ctx.send("目前語音裡人太少。")
            return

        random.shuffle(members)
        half = len(members)//2
        red = members[:half]
        blue = members[half:]
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        msg = (f"LOL 分組結果 ({now})\n"
               f"紅隊: {', '.join(red)}\n"
               f"藍隊: {', '.join(blue)}")
        await ctx.send(msg)
    else:
        await ctx.send("請先進入語音頻道再使用 !抽 指令。")

bot.run(os.getenv("DISCORD_TOKEN"))
