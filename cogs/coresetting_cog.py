import discord
from discord.ext import commands
import json
import os

# 定位到 Docker 持久化的 data 文件夹，防止重启丢失
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
DATA_DIR = os.path.join(project_root, 'data')

class CoreSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # 确保 data 目录存在
        os.makedirs(DATA_DIR, exist_ok=True)
        self.config_file = os.path.join(DATA_DIR, 'channels.json')

        # 启动时初始化默认结构（已移除 news）
        self.bot.broadcast_channels = {'house': None, 'fs': None, 'cal': None}

        # 加载本地配置
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    # 使用 get 确保即使 json 里有旧数据也不会报错，同时只提取需要的 3 个模块
                    self.bot.broadcast_channels = {
                        'house': saved_data.get('house'),
                        'fs': saved_data.get('fs'),
                        'cal': saved_data.get('cal')
                    }
            except Exception as e:
                print(f"读取 channels.json 失败: {e}")
        # 如果文件不存在，初始化已经在上面完成了

    def save_config(self):
        """将当前频道配置写入本地 JSON 文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.bot.broadcast_channels, f, ensure_ascii=False, indent=4)

    # 更新了 help 提示文本，移除了 news
    @commands.command(name='setchannel',
                      help='统一设置播报频道。用法: !setchannel [类型] (可选: all, house, fs, cal)')
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx, module: str = 'all'):
        module = module.lower()
        # 有效模块列表（已移除官网公告）
        valid_modules = {'house': '房屋追踪', 'fs': '时尚品鉴', 'cal': '活动日历'}

        channel_id = ctx.channel.id

        if module == 'all':
            for m in valid_modules.keys():
                self.bot.broadcast_channels[m] = channel_id
            self.save_config()
            await ctx.send(f"✅ 已将 **所有功能** 的自动播报频道绑定至 {ctx.channel.mention}")

        elif module in valid_modules:
            self.bot.broadcast_channels[module] = channel_id
            self.save_config()
            await ctx.send(f"✅ 已将 **{valid_modules[module]}** 的播报频道绑定至 {ctx.channel.mention}")

        else:
            # 更新了报错提示文本，移除了 news
            await ctx.send("❌ 未知的模块类型。请使用: `all`, `house`, `fs`, 或 `cal`。")

async def setup(bot):
    await bot.add_cog(CoreSettings(bot))