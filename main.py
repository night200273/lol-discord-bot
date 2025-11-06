import random
import discord
from discord.ext import commands
from datetime import datetime
import os
from threading import Thread
from flask import Flask
import logging

# 關閉 Flask 的日誌輸出
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

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
    print(f"[Flask] 啟動網頁伺服器於端口 {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

@bot.event
async def on_ready():
    print(f"[Discord] Bot 登入成功: {bot.user}")
    print(f"[Discord] Bot ID: {bot.user.id}")
    print(f"[Discord] 已連接到 {len(bot.guilds)} 個伺服器")

@bot.event
async def on_message(message):
    # 印出所有訊息（除錯用）
    if message.author != bot.user:
        print(f"[訊息] {message.author}: {message.content}")
    await bot.process_commands(message)

@bot.command()
async def 抽(ctx):
    print(f"[指令] 收到抽獎指令，來自 {ctx.author}")
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
    print("[系統] 正在啟動 LOL Discord Bot...")
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

    import time
    time.sleep(2)  # 等待 Flask 啟動

    # 啟動 Discord Bot
    print("[Discord] 正在連接到 Discord Gateway...")
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[錯誤] 找不到 DISCORD_TOKEN 環境變數！")
    else:
        bot.run(token)
