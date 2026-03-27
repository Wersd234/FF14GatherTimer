# main_bot.py (v4.3 - Docker Volume support)

import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()  # Loads variables from the .env file

BOT_TOKEN = os.getenv('DISCORD_TOKEN')  # Get the token securely

if BOT_TOKEN is None:
    raise ValueError("DISCORD_TOKEN not found. Make sure it's set in your .env file.")
COMMAND_PREFIX = "!"
script_dir = os.path.dirname(os.path.abspath(__file__))

# 为持久化数据创建一个专门的目录
# Docker会将您电脑上的一个文件夹映射到这里的 /app/data
data_dir = os.path.join(script_dir, 'data')
os.makedirs(data_dir, exist_ok=True)


# 获取项目根目录 (main_bot.py 所在的目录)
BASE_DIR = Path(__file__).resolve().parent

# 定义数据目录
DATA_DIR = BASE_DIR / "data"

# 示例：读取关注列表
# watchlist_path = DATA_DIR / "watchlists.json"

BOT_CONFIG = {
    "CSV_FILENAME": os.path.join(script_dir, 'data/nodes.csv'),
    "WATCHLIST_FILE": os.path.join(data_dir, 'data/watchlists.json'),
    "PING_FILE": os.path.join(data_dir, 'data/pings.json'),
    "MANUAL_TIME_OFFSET_SECONDS": 0.0
}

# 加入了新写的全局设置和房屋追踪模块
INITIAL_EXTENSIONS = [
    'cogs.tracker_cog',
    "cogs.fashion_cog",
    "cogs.market_cog",
    "cogs.holiday_cog",
    "cogs.help_cog",
    'cogs.fflogs_cog',
    'cogs.coresetting_cog',
    'cogs.housetracker_cog',
    'cogs.astrologian_cog'

]

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
async def reload_extension(ctx, extension_name: str = "all"):
    """热重载模块。用法: !reload (重载全部) 或 !reload fashion_cog (重载单个)"""
    if extension_name.lower() == "all":
        success_count = 0
        fail_count = 0

        # 遍历 main_bot.py 顶部的 INITIAL_EXTENSIONS 列表
        for extension in INITIAL_EXTENSIONS:
            try:
                await bot.reload_extension(extension)
                success_count += 1
            except Exception as e:
                print(f"重载 {extension} 失败: {e}")
                fail_count += 1

        msg = f"🔄 批量重载完成！成功: **{success_count}** 个，失败: **{fail_count}** 个。"
        if fail_count > 0:
            msg += "\n*(失败详情请查看后台控制台日志)*"
        await ctx.send(msg)

    else:
        # 重载单个指定的模块
        cog_name = f"cogs.{extension_name}"
        try:
            await bot.reload_extension(cog_name)
            await ctx.send(f"✅ 模块 `{extension_name}` 重载成功！")
        except Exception as e:
            await ctx.send(f"❌ 重载模块 `{extension_name}` 失败: \n```py\n{e}\n```")

async def main():
    async with bot:
        for extension in INITIAL_EXTENSIONS:
            try:
                await bot.load_extension(extension)
            except Exception as e:
                print(f'加载扩展 {extension} 失败. {e}')
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or BOT_TOKEN == "":
        print("错误：请先在 .env 文件中填入你的机器人TOKEN！")
    else:
        asyncio.run(main())