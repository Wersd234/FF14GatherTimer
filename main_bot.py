# main_bot.py (v4.3 - Docker Volume support)

import discord
from discord.ext import commands
import asyncio
import os

# --- 全局配置 ---
from dotenv import load_dotenv

load_dotenv() # Loads variables from the .env file

BOT_TOKEN = os.getenv('DISCORD_TOKEN') # Get the token securely

if BOT_TOKEN is None:
    raise ValueError("DISCORD_TOKEN not found. Make sure it's set in your .env file.")
COMMAND_PREFIX = "/"
script_dir = os.path.dirname(os.path.abspath(__file__))

# **核心修改: 为持久化数据创建一个专门的目录**
# Docker会将您电脑上的一个文件夹映射到这里的 /app/data
data_dir = os.path.join(script_dir, 'data')
os.makedirs(data_dir, exist_ok=True) # 如果 data 文件夹不存在，就创建它

BOT_CONFIG = {
    "CSV_FILENAME": os.path.join(script_dir, 'nodes.csv'),
    # **修改: 让json文件指向新的 data 目录**
    "WATCHLIST_FILE": os.path.join(data_dir, 'watchlists.json'),
    "PING_FILE": os.path.join(data_dir, 'pings.json'),
    "MANUAL_TIME_OFFSET_SECONDS": 0.0
}
# ... (后续代码与之前版本完全相同) ...
INITIAL_EXTENSIONS = ['cogs.tracker_cog']
intents = discord.Intents.default()
intents.message_content = True
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = BOT_CONFIG
    async def on_ready(self):
        print(f'机器人已登录: {self.user.name}\n------')
bot = MyBot(command_prefix=COMMAND_PREFIX, intents=intents)
@bot.command(name='reload')
@commands.is_owner()
async def reload_extension(ctx, extension_name: str):
    cog_name = f"cogs.{extension_name}"
    try:
        await bot.reload_extension(cog_name)
        await ctx.send(f"✅ 模块 `{extension_name}` 重载成功！")
    except Exception as e:
        await ctx.send(f"❌ 重载模块 `{extension_name}` 失败: \n```py\n{e}\n```")
async def main():
    async with bot:
        for extension in INITIAL_EXTENSIONS:
            try: await bot.load_extension(extension)
            except Exception as e: print(f'加载扩展 {extension} 失败. {e}')
        await bot.start(BOT_TOKEN)
if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or BOT_TOKEN == "":
        print("错误：请先在 main_bot.py 文件中填入你的机器人TOKEN！")
    else:
        asyncio.run(main())