import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command('help')

    @commands.command(name='help', aliases=['h', '帮助', '菜单'])
    async def custom_help(self, ctx):
        embed = discord.Embed(
            title="🛠️ FF14 实用工具机器人 (FF14 Util) - 帮助手册",
            description="这里是所有可用指令的分类列表。尖括号 `< >` 代表必填项，方括号 `[ ]` 代表可选项。",
            color=0x2b2d31
        )

        # 1. 采集追踪器
        tracker_desc = (
            "`!add <材料>` - 添加到追踪列表 | `!list` - 查看列表\n"
            "`!start` - 启动追踪器面板 | `!stop` - 停止追踪"
        )
        embed.add_field(name="⛏️ 采集追踪器 (Tracker)", value=tracker_desc, inline=False)

        # 2. 房屋与市场
        house_desc = (
            "`!house [服务器] [参数...]` - 查询空地 (默认: 太阳海岸)\n"
            "`!price <物品名> [大区]` - 查询市场物价"
        )
        embed.add_field(name="🏡 房屋与市场 (Housing & Market)", value=house_desc, inline=False)

        # 3. 时尚、日历与查榜 (移除了 news)
        common_desc = (
            "`!fs` - 查看本周时尚品鉴作业 | `!fs time` - 倒计时\n"
            "`!cal next` - 查看近期节日或活动排期\n"
            "`!logs <服务器> <角色名>` - 查询 FFLogs 战绩"
        )
        embed.add_field(name="📅 时尚、日历与查榜", value=common_desc, inline=False)

        # 4. 艾欧泽亚娱乐
        fun_desc = (
            "`!draw` - 抽选你的每日占星运势 (别名: `!占星`)\n"
            "└ *每天 00:00 (澳洲时间) 刷新*"
        )
        embed.add_field(name="🔮 艾欧泽亚娱乐 (Fun)", value=fun_desc, inline=False)

        # 5. 管理员设置 (移除了 news 选项)
        admin_desc = (
            "**[全局频道绑定]**\n"
            "`!setchannel <模块>` - 绑定提醒 (模块: all, house, fs, cal)\n\n"
            "**[系统维护]**\n"
            "`!reload [模块名]` - 重载代码 (默认重载全部)\n\n"
            "**[内容配置]**\n"
            "`!fs update <文字>` - 更新作业 | `!cal setlink <URL>` - 绑定日历"
        )
        embed.add_field(name="⚙️ 管理员专属设置 (Admin)", value=admin_desc, inline=False)

        embed.set_footer(text="愿太阳神指引你的前路")
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))