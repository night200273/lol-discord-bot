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

# ======================
#  全域變數
# ======================
queue = []  # 排隊名單
AUTHORIZED_ROLES = ["慕笙寶寶", "💟保姆", "保姆"]
MAX_PLAYERS = 4
processed_messages = set()  # 防止重複處理
queue_enabled = False  # 上車系統開關（預設關閉）
ALLOWED_CHANNEL_ID = 1435699524084699247  # 指定頻道ID

# ======================
#  輔助函數
# ======================
def has_authority(member):
    """檢查是否為授權身分（支援模糊匹配）"""
    for role in member.roles:
        # 完全匹配
        if role.name in AUTHORIZED_ROLES:
            return True
        # 模糊匹配：檢查是否包含關鍵字
        if any(keyword in role.name for keyword in ["管理", "保姆", "慕笙"]):
            return True
    return False

def get_role_type(member):
    """判斷身份組（訂閱 or 觀眾）"""
    for role in member.roles:
        # 檢查身分組名稱是否包含「訂閱」關鍵字
        if "訂閱" in role.name:
            return "訂閱"
    return "觀眾"

def is_allowed_channel(ctx):
    """檢查是否在允許的頻道中"""
    return ctx.channel.id == ALLOWED_CHANNEL_ID

# ======================
#  Flask 路由
# ======================
@app.route('/')
def home():
    return "LOL 上車系統 Bot is running! ✅"

@app.route('/health')
def health():
    return {"status": "ok", "bot": str(bot.user) if bot.user else "connecting"}

def run_web_server():
    """在背景執行 Flask 伺服器"""
    port = int(os.getenv("PORT", 10000))
    print(f"[Flask] 啟動網頁伺服器於端口 {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ======================
#  Discord Bot 事件
# ======================
@bot.event
async def on_ready():
    print(f"[Discord] ✅ Bot 登入成功: {bot.user}")
    print(f"[Discord] Bot ID: {bot.user.id}")
    print(f"[Discord] 已連接到 {len(bot.guilds)} 個伺服器")

    # 列出所有伺服器
    for guild in bot.guilds:
        print(f"[Discord] - 伺服器：{guild.name} (ID: {guild.id})")

@bot.event
async def on_message(message):
    # 印出所有訊息（除錯用）
    if message.author != bot.user:
        print(f"[訊息] {message.author}: {message.content}")
    await bot.process_commands(message)

# ======================
#  上車系統指令
# ======================
@bot.command()
async def 開始上車(ctx):
    """開啟上車系統（僅慕笙寶寶或保姆可用）"""
    if not is_allowed_channel(ctx):
        return

    if not has_authority(ctx.author):
        await ctx.send("⛔ 只有慕笙寶寶或保姆能開啟上車系統！")
        return

    global queue_enabled
    if queue_enabled:
        await ctx.send("⚠️ 上車系統已經開啟了！")
        return

    queue_enabled = True
    await ctx.send("🚀 上車系統已開啟！大家可以開始 !上車 囉～")
    print(f"[系統] {ctx.author.display_name} 開啟了上車系統")

@bot.command()
async def 停止上車(ctx):
    """關閉上車系統（僅慕笙寶寶或保姆可用）"""
    if not is_allowed_channel(ctx):
        return

    if not has_authority(ctx.author):
        await ctx.send("⛔ 只有慕笙寶寶或保姆能關閉上車系統！")
        return

    global queue_enabled
    if not queue_enabled:
        await ctx.send("⚠️ 上車系統已經是關閉狀態了！")
        return

    queue_enabled = False
    await ctx.send("🛑 上車系統已關閉！暫時無法上車")
    print(f"[系統] {ctx.author.display_name} 關閉了上車系統")

@bot.command()
async def 上車(ctx):
    """加入排隊名單"""
    if not is_allowed_channel(ctx):
        return

    # 檢查上車系統是否開啟
    if not queue_enabled:
        await ctx.send("⛔ 上車系統尚未開啟，請等待慕笙寶寶或保姆開啟！")
        return

    # 防止重複處理同一訊息
    msg_id = ctx.message.id
    if msg_id in processed_messages:
        print(f"[警告] 重複訊息被忽略: {msg_id}")
        return
    processed_messages.add(msg_id)

    user = ctx.author
    print(f"[指令-上車] {user.display_name} 執行上車指令 (訊息ID: {msg_id})")

    if user in queue:
        position = queue.index(user) + 1
        await ctx.send(f"🚗 {user.display_name} 已在排隊中！（第 {position} 位）")
        return

    queue.append(user)
    print(f"[指令-上車] {user.display_name} 成功加入，目前第 {len(queue)} 位")
    await ctx.send(f"✅ {user.display_name} 成功上車，目前第 **{len(queue)} 位**")

@bot.command()
async def 跳車(ctx):
    """離開排隊名單"""
    if not is_allowed_channel(ctx):
        return

    # 檢查上車系統是否開啟
    if not queue_enabled:
        await ctx.send("⛔ 上車系統尚未開啟！")
        return

    user = ctx.author
    if user not in queue:
        await ctx.send(f"❌ {user.display_name} 不在排隊名單中")
        return

    queue.remove(user)
    await ctx.send(f"👋 {user.display_name} 已跳車。剩餘人數：{len(queue)}")

@bot.command(name="排隊清單")
async def 排隊清單(ctx):
    """顯示目前排隊名單"""
    if not is_allowed_channel(ctx):
        return

    # 檢查上車系統是否開啟
    if not queue_enabled:
        await ctx.send("⛔ 上車系統尚未開啟！")
        return

    if not queue:
        await ctx.send("📭 目前沒有人排隊喔～")
        return

    msg = f"🚌 目前排隊共 {len(queue)} 人：\n"
    for i, member in enumerate(queue, start=1):
        role_type = get_role_type(member)
        # 除錯：印出該成員的所有身分組
        print(f"[除錯] {member.display_name} 的身分組：{[role.name for role in member.roles]}")
        # 前4位標記為即將上場
        mark = "🎮" if i <= MAX_PLAYERS else "🕓"
        msg += f"{mark} {i}. {member.display_name}（{role_type}）\n"

    await ctx.send(msg)

@bot.command(name="查車況")
async def 查車況(ctx):
    """查看當前上場4人和預備候補4人"""
    if not is_allowed_channel(ctx):
        return

    # 檢查上車系統是否開啟
    if not queue_enabled:
        await ctx.send("⛔ 上車系統尚未開啟！")
        return

    if not queue:
        await ctx.send("📭 目前沒有人排隊喔～")
        return

    # 當前上場：前4位
    current_players = queue[:MAX_PLAYERS]
    # 預備候補：第5-8位
    next_players = queue[MAX_PLAYERS:MAX_PLAYERS*2]

    msg = "🎮 **當前上場：**\n"
    if current_players:
        for i, member in enumerate(current_players, start=1):
            role_type = get_role_type(member)
            icon = "🔴" if role_type == "訂閱" else "⚪"
            msg += f"{icon} {i}. {member.display_name}（{role_type}）\n"
    else:
        msg += "（無）\n"

    msg += "\n🕓 **預備候補：**\n"
    if next_players:
        for i, member in enumerate(next_players, start=5):
            role_type = get_role_type(member)
            icon = "⚪"
            msg += f"{icon} {i}. {member.display_name}（{role_type}）\n"
    else:
        msg += "（無）\n"

    # 如果還有更多人在排隊中
    remaining = len(queue) - MAX_PLAYERS * 2
    if remaining > 0:
        msg += f"\n📋 還有 {remaining} 人在排隊中..."

    await ctx.send(msg)

@bot.command(name="換人")
async def 換人(ctx):
    """執行換人邏輯：前2訂閱優先 + 後2位依排隊順序"""
    if not is_allowed_channel(ctx):
        return

    # 除錯：印出使用者的身分組
    print(f"[除錯-換人] {ctx.author.display_name} 的身分組：{[role.name for role in ctx.author.roles]}")
    print(f"[除錯-換人] 權限檢查結果：{has_authority(ctx.author)}")

    if not has_authority(ctx.author):
        await ctx.send("⛔ 只有慕笙寶寶、管理員或保姆能使用這個指令！")
        return

    global queue
    if not queue:
        await ctx.send("⚠️ 目前沒有人排隊")
        return

    # 分離訂閱與觀眾
    subscribers = [m for m in queue if get_role_type(m) == "訂閱"]

    # 組出這一輪的上場名單
    new_round = []

    # 1. 優先取最多2位訂閱（依排隊順序）
    for member in queue:
        if len(new_round) < 2 and member in subscribers:
            new_round.append(member)

    # 2. 再依原排隊順序補滿4位（不論身份）
    for member in queue:
        if member not in new_round:
            new_round.append(member)
        if len(new_round) >= MAX_PLAYERS:
            break

    # 3. 移除前4位（已上場）
    queue = queue[MAX_PLAYERS:] if len(queue) > MAX_PLAYERS else []

    # 組出顯示訊息
    msg = "🎮 **本輪上場：**\n"
    for m in new_round:
        role_type = get_role_type(m)
        # 根據不同身分顯示不同圖示
        if role_type == "訂閱":
            icon = "🔴"
        else:
            icon = "⚪"
        msg += f"{icon} {m.display_name}（{role_type}）\n"

    if queue:
        msg += "\n🕓 **下一輪候補：**\n"
        msg += "、".join(m.display_name for m in queue)
    else:
        msg += "\n📭 所有人都已上場完畢"

    await ctx.send(msg)

@bot.command(name="清除")
async def 清除(ctx):
    """清除所有排隊名單"""
    if not is_allowed_channel(ctx):
        return

    if not has_authority(ctx.author):
        await ctx.send("⛔ 只有慕笙寶寶、管理員或保姆能清除名單")
        return

    global queue
    queue.clear()
    await ctx.send("🧹 已清除所有排隊名單")

@bot.command(name="查身份")
async def 查身份(ctx):
    """查看自己的所有身分組（除錯用）"""
    if not is_allowed_channel(ctx):
        return

    user = ctx.author
    roles = [role.name for role in user.roles]
    role_type = get_role_type(user)

    msg = f"🔍 **{user.display_name} 的身分資訊：**\n"
    msg += f"所有身分組：{', '.join(roles)}\n"
    msg += f"判定結果：{role_type}"

    await ctx.send(msg)
    print(f"[除錯] {user.display_name} 的身分組列表：{roles}")

# ======================
#  語音抽隊指令
# ======================
@bot.command(name="抽")
async def 抽(ctx):
    """從語音頻道隨機分組"""
    if not is_allowed_channel(ctx):
        return

    if not has_authority(ctx.author):
        await ctx.send("⛔ 只有慕笙寶寶、管理員或保姆能使用這個指令！")
        return

    print(f"[指令] 收到抽獎指令，來自 {ctx.author}")

    if ctx.author.voice and ctx.author.voice.channel:
        vc = ctx.author.voice.channel
        members = [m.display_name for m in vc.members if not m.bot]

        if len(members) < 2:
            await ctx.send("⚠️ 語音裡人太少，無法分組")
            return

        random.shuffle(members)
        half = len(members) // 2
        red = members[:half]
        blue = members[half:]
        now = datetime.now().strftime("%Y/%m/%d %H:%M")

        msg = (f"🔥 LOL 分組結果（{now}）\n"
               f"🔴 紅隊：{', '.join(red)}\n"
               f"🔵 藍隊：{', '.join(blue)}")
        await ctx.send(msg)
    else:
        await ctx.send("🎧 請先進入語音頻道再使用 !抽 指令")

# ======================
#  啟動程式
# ======================
if __name__ == "__main__":
    print("[系統] 正在啟動 LOL 上車系統 Bot...")

    # 在背景啟動網頁伺服器
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

    import time
    time.sleep(2)  # 等待 Flask 啟動

    # 啟動 Discord Bot（帶重試機制）
    print("[Discord] 正在連接到 Discord Gateway...")
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("[錯誤] 找不到 DISCORD_TOKEN 環境變數！")
    else:
        max_retries = 5
        retry_delay = 60  # 等待 60 秒後重試

        for attempt in range(max_retries):
            try:
                print(f"[Discord] 嘗試連接 (第 {attempt + 1}/{max_retries} 次)...")
                bot.run(token)
                break  # 如果成功連接，跳出循環
            except discord.errors.HTTPException as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    print(f"[警告] 遇到 Rate Limit 錯誤！")
                    if attempt < max_retries - 1:
                        print(f"[系統] 等待 {retry_delay} 秒後重試...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指數退避：每次等待時間加倍
                    else:
                        print("[錯誤] 已達到最大重試次數，放棄連接")
                        raise
                else:
                    print(f"[錯誤] Discord HTTP 錯誤：{e}")
                    raise
            except Exception as e:
                print(f"[錯誤] 啟動 Bot 時發生錯誤：{e}")
                raise
