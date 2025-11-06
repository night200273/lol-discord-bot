import random
import discord
from discord.ext import commands
from datetime import datetime
import os
from threading import Thread
from flask import Flask

# Discord Bot 設定
intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Flask 網頁伺服器（用於 Render 端口檢測）
app = Flask(__name__)

@app.route('/')
def home():
    return "LOL Discord Bot is running! ✅"

@app.route('/health')
def health():
    return {"status": "ok", "bot": str(bot.user) if bot.user else "connecting"}

def run_web_server():
    """在背景執行 Flask 伺服器"""
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

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

if __name__ == "__main__":
    # 在背景啟動網頁伺服器
    print("[啟動] 正在啟動網頁伺服器...")
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

    # 啟動 Discord Bot
    print("[啟動] 正在連接 Discord...")
    bot.run(os.getenv("DISCORD_TOKEN"))
