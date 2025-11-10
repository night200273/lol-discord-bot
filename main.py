import random
import discord
from discord.ext import commands
from datetime import datetime
import os
from threading import Thread
from flask import Flask
import logging
from pathlib import Path
import asyncio
import twitchio
from twitchio.ext import commands as twitch_commands

# 載入 .env 文件（如果存在）
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

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
twitch_processed_users = set()  # 防止 Twitch 重複處理
twitch_bot = None  # Twitch Bot 全域變數

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
    # 檢查是否為 Twitch 使用者
    if isinstance(member, TwitchBot.TwitchUser):
        if member.is_subscriber:
            return "Twitch 訂閱者"
        elif member.is_follower:
            return "Twitch 追隨者"
        else:
            return "Twitch 觀眾"

    # 檢查 Discord 身分組
    for role in member.roles:
        # 檢查身分組名稱是否包含「訂閱」關鍵字
        if "訂閱" in role.name:
            return "訂閱"
    return "觀眾"

def is_allowed_channel(ctx):
    """檢查是否在允許的頻道中"""
    return ctx.channel.id == ALLOWED_CHANNEL_ID

# ======================
#  Twitch Bot 設定
# ======================
class TwitchBot(twitch_commands.Bot):
    """Twitch 聊天監聽 Bot"""

    class TwitchUser:
        """Twitch 觀眾虛擬使用者類別"""
        def __init__(self, name, is_subscriber=False, is_follower=False):
            self.display_name = f"[Twitch] {name}"
            self.name = name
            self.roles = []
            self.is_subscriber = is_subscriber  # 是否為訂閱者
            self.is_follower = is_follower      # 是否為追隨者

        def __eq__(self, other):
            if isinstance(other, TwitchBot.TwitchUser):
                return self.name == other.name
            return False

        def __hash__(self):
            return hash(f"twitch_{self.name}")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.discord_bot = None  # 儲存 Discord Bot 的引用

    async def event_ready(self):
        """Twitch 連線成功"""
        print(f"[Twitch] ✅ 已登入為 {self.nick}")
        print(f"[Twitch] 已連線至頻道：{os.getenv('TWITCH_CHANNEL', 'm0623lalala')}")

    async def event_message(self, message):
        """監聽 Twitch 聊天訊息"""
        # 忽略機器人本身的訊息
        if message.echo:
            return

        command = message.content.strip()
        user_name = message.author.name

        # 處理 !上車 指令
        if command == "!上車":
            print(f"[Twitch] 收到來自 {user_name} 的 !上車 指令")

            # 防止重複處理同一使用者
            if user_name in twitch_processed_users:
                print(f"[Twitch] 警告：{user_name} 已在處理中，忽略重複請求")
                return

            # 標記為已處理（30秒內不會再處理同一使用者）
            twitch_processed_users.add(user_name)

            # 延遲 30 秒移除使用者，允許下次請求
            async def remove_after_delay():
                await asyncio.sleep(30)
                twitch_processed_users.discard(user_name)

            asyncio.create_task(remove_after_delay())

            # 觸發 Discord 相關邏輯
            if self.discord_bot:
                await self.handle_twitch_ride(user_name, message)

        # 處理 !跳車 指令
        elif command == "!跳車":
            print(f"[Twitch] 收到來自 {user_name} 的 !跳車 指令")

            # 防止重複處理同一使用者
            if user_name in twitch_processed_users:
                print(f"[Twitch] 警告：{user_name} 已在處理中，忽略重複請求")
                return

            # 標記為已處理
            twitch_processed_users.add(user_name)

            # 延遲 30 秒移除使用者
            async def remove_after_delay():
                await asyncio.sleep(30)
                twitch_processed_users.discard(user_name)

            asyncio.create_task(remove_after_delay())

            # 觸發 Discord 相關邏輯
            if self.discord_bot:
                await self.handle_twitch_leave(user_name)

    async def handle_twitch_ride(self, user_name, message):
        """處理 Twitch 觀眾的上車請求"""
        global queue_enabled

        # 檢查上車系統是否開啟
        if not queue_enabled:
            print(f"[Twitch] 上車系統未開啟，忽略 {user_name} 的請求")
            return

        try:
            # 取得 Discord 頻道
            channel = self.discord_bot.get_channel(ALLOWED_CHANNEL_ID)
            if not channel:
                print(f"[Twitch] 錯誤：無法找到 Discord 頻道 {ALLOWED_CHANNEL_ID}")
                return

            # 獲取使用者身份信息
            is_subscriber = message.author.is_subscriber if hasattr(message.author, 'is_subscriber') else False
            is_follower = message.author.is_follower if hasattr(message.author, 'is_follower') else False

            # 建立一個虛擬的使用者物件以加入隊伍
            twitch_user = self.TwitchUser(user_name, is_subscriber=is_subscriber, is_follower=is_follower)

            # 檢查是否已在隊伍中
            if any(u.name == user_name if isinstance(u, self.TwitchUser) else False for u in queue):
                position = next((i + 1 for i, u in enumerate(queue) if isinstance(u, self.TwitchUser) and u.name == user_name), None)
                if position:
                    msg = f"🚗 Twitch 觀眾 **{user_name}** 已在排隊中！（第 {position} 位）"
                    # 使用 asyncio.run_coroutine_threadsafe 跨執行緒執行
                    asyncio.run_coroutine_threadsafe(
                        channel.send(msg),
                        self.discord_bot.loop
                    )
                    print(f"[Twitch] {user_name} 已在隊伍中（第 {position} 位）")
                return

            # 加入隊伍
            queue.append(twitch_user)
            position = len(queue)

            # 在 Discord 發送公告訊息
            announcement = f"🎮 Twitch 觀眾 **{user_name}** 從台上打了 !上車！"
            asyncio.run_coroutine_threadsafe(
                channel.send(announcement),
                self.discord_bot.loop
            )
            print(f"[Twitch] 已在 Discord 發送公告：{announcement}")

            # 根據身份生成不同的歡迎訊息
            status_icon = ""
            if is_subscriber:
                status_icon = "💝 (訂閱者)"
            elif is_follower:
                status_icon = "⭐ (追隨者)"

            msg = f"✅ Twitch 觀眾 **{user_name}** {status_icon} 成功上車，目前第 **{position} 位**"
            asyncio.run_coroutine_threadsafe(
                channel.send(msg),
                self.discord_bot.loop
            )
            print(f"[Twitch] {user_name} (訂閱:{is_subscriber}, 追隨:{is_follower}) 成功加入隊伍，目前第 {position} 位")

        except Exception as e:
            print(f"[Twitch] 錯誤：處理上車請求時失敗 - {e}")
            import traceback
            traceback.print_exc()

    async def handle_twitch_leave(self, user_name):
        """處理 Twitch 觀眾的跳車請求"""
        global queue_enabled

        # 檢查上車系統是否開啟
        if not queue_enabled:
            print(f"[Twitch] 上車系統未開啟，忽略 {user_name} 的跳車請求")
            return

        try:
            # 取得 Discord 頻道
            channel = self.discord_bot.get_channel(ALLOWED_CHANNEL_ID)
            if not channel:
                print(f"[Twitch] 錯誤：無法找到 Discord 頻道 {ALLOWED_CHANNEL_ID}")
                return

            # 從隊伍中尋找 Twitch 觀眾
            twitch_user_to_remove = None
            for u in queue:
                if isinstance(u, self.TwitchUser) and u.name == user_name:
                    twitch_user_to_remove = u
                    break

            if not twitch_user_to_remove:
                msg = f"❌ Twitch 觀眾 **{user_name}** 不在排隊名單中"
                asyncio.run_coroutine_threadsafe(
                    channel.send(msg),
                    self.discord_bot.loop
                )
                print(f"[Twitch] {user_name} 不在隊伍中")
                return

            # 從隊伍移除
            queue.remove(twitch_user_to_remove)
            msg = f"👋 Twitch 觀眾 **{user_name}** 已跳車。剩餘人數：{len(queue)}"
            asyncio.run_coroutine_threadsafe(
                channel.send(msg),
                self.discord_bot.loop
            )
            print(f"[Twitch] {user_name} 成功跳車，剩餘人數：{len(queue)}")

        except Exception as e:
            print(f"[Twitch] 錯誤：處理跳車請求時失敗 - {e}")
            import traceback
            traceback.print_exc()

async def run_twitch_bot():
    """在背景執行 Twitch Bot"""
    global twitch_bot
    try:
        print("[Twitch] 讀取環境變數...")
        twitch_username = os.getenv("TWITCH_USERNAME")
        twitch_token = os.getenv("TWITCH_TOKEN")
        twitch_channel = os.getenv("TWITCH_CHANNEL", "m0623lalala")
        twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
        twitch_client_secret = os.getenv("TWITCH_CLIENT_SECRET")

        print(f"[Twitch] USERNAME: {twitch_username}")
        print(f"[Twitch] TOKEN: {twitch_token[:20] if twitch_token else 'None'}...")
        print(f"[Twitch] CLIENT_ID: {twitch_client_id[:20] if twitch_client_id else 'None'}...")
        print(f"[Twitch] CHANNEL: {twitch_channel}")

        if not twitch_username or not twitch_token:
            print("[Twitch] ⚠️  缺少 TWITCH_USERNAME 或 TWITCH_TOKEN，Twitch 監聽已禁用")
            return

        if not twitch_client_id:
            print("[Twitch] ⚠️  缺少 TWITCH_CLIENT_ID，Twitch 監聽已禁用")
            return

        print("[Twitch] 建立 TwitchBot 實例...")
        twitch_bot = TwitchBot(
            token=twitch_token,
            client_id=twitch_client_id,
            client_secret=twitch_client_secret or "not_used",  # 監聽模式不需要
            bot_id=os.getenv("TWITCH_BOT_ID", "999999999"),  # 監聽模式用默認值
            nick=twitch_username,
            prefix="!",
            initial_channels=[twitch_channel]
        )

        # 將 Discord Bot 的引用傳遞給 Twitch Bot
        twitch_bot.discord_bot = bot

        print("[Twitch] 正在連接到 Twitch...")
        await twitch_bot.start()

    except Exception as e:
        print(f"[Twitch] ❌ 連接失敗：{e}")
        import traceback
        traceback.print_exc()

def run_twitch_in_thread():
    """在獨立執行緒中執行 Twitch Bot"""
    print("[Twitch] 正在初始化 Twitch Bot 執行緒...")
    try:
        # 為了避免事件循環衝突，強制建立新的事件循環
        import sys
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print("[Twitch] 執行緒已建立，正在連接...")
        loop.run_until_complete(run_twitch_bot())
        print("[Twitch] 執行緒運行中...")
        loop.run_forever()
    except KeyboardInterrupt:
        print("[Twitch] 執行緒被中斷")
    except Exception as e:
        print(f"[Twitch] 執行緒錯誤：{e}")
        import traceback
        traceback.print_exc()

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

        # 根據身分設定圖示
        if isinstance(member, TwitchBot.TwitchUser):
            if member.is_subscriber:
                icon = "💝"  # Twitch 訂閱者
            elif member.is_follower:
                icon = "⭐"  # Twitch 追隨者
            else:
                icon = "🟦"  # Twitch 普通觀眾
        else:
            # Discord 使用者
            if role_type == "訂閱":
                icon = "🔴"  # Discord 訂閱者
            else:
                icon = "⚪"  # Discord 普通觀眾

        # 前4位標記為即將上場
        mark = "🎮" if i <= MAX_PLAYERS else "🕓"
        msg += f"{mark}{icon} {i}. {member.display_name}（{role_type}）\n"

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

            # 根據身分設定圖示
            if isinstance(member, TwitchBot.TwitchUser):
                if member.is_subscriber:
                    icon = "💝"  # Twitch 訂閱者
                elif member.is_follower:
                    icon = "⭐"  # Twitch 追隨者
                else:
                    icon = "🟦"  # Twitch 普通觀眾
            else:
                # Discord 使用者
                icon = "🔴" if role_type == "訂閱" else "⚪"

            msg += f"{icon} {i}. {member.display_name}（{role_type}）\n"
    else:
        msg += "（無）\n"

    msg += "\n🕓 **預備候補：**\n"
    if next_players:
        for i, member in enumerate(next_players, start=5):
            role_type = get_role_type(member)

            # 根據身分設定圖示
            if isinstance(member, TwitchBot.TwitchUser):
                if member.is_subscriber:
                    icon = "💝"  # Twitch 訂閱者
                elif member.is_follower:
                    icon = "⭐"  # Twitch 追隨者
                else:
                    icon = "🟦"  # Twitch 普通觀眾
            else:
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

    # 在背景啟動 Twitch Bot
    twitch_thread = Thread(target=run_twitch_in_thread, daemon=True)
    twitch_thread.start()

    import time
    time.sleep(2)  # 等待 Flask 和 Twitch 啟動

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
