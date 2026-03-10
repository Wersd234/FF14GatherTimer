import discord
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 移除 Discord 默认的 help 指令，使用我们自定义的炫酷版本
        self.bot.remove_command('help')

    @commands.command(name='help', aliases=['h', '帮助', '菜单'])
    async def custom_help(self, ctx):
        """显示机器人的所有可用指令"""

        embed = discord.Embed(
            title="🛠️ FF14 实用工具机器人 (FF14 Util) - 帮助手册",
            description="这里是所有可用指令的分类列表。尖括号 `< >` 代表必填项，方括号 `[ ]` 代表可选项。",
            color=0x2b2d31  # 匹配截图中的高级暗黑色调
        )

        # 1. 采集追踪器指令 (Tracker)
        tracker_desc = (
            "`!add <材料1, 材料2>` - 添加你想追踪的材料到关注列表\n"
            "`!remove <材料1, 材料2>` - 从关注列表移除材料\n"
            "`!list` - 查看你当前的关注列表\n"
            "`!start` - 启动追踪器面板 (只显示你关注的)\n"
            "`!start all` - 启动完整追踪器面板 (显示所有材料)\n"
            "`!stop` - 停止当前频道的追踪器\n"
            "`!ping <秒数>` - 设置刷新前的自动提醒时间 (输入 off 关闭)\n"
            "`!copy <@用户>` - 复制某人的关注列表到你自己的列表\n"
            "`!clear` - 清空你的关注列表"
        )
        embed.add_field(name="⛏️ 采集追踪器指令 (Tracker)", value=tracker_desc, inline=False)

        # 2. 市场物价查询 (Market)
        market_desc = (
            "`!price <物品名> [大区名]` - 查询最低物价与近期成交记录\n"
            "*(别名: `!mb <物品名> [大区名]`)*\n"
            "*(例: `!price 纯水` 或 `!price 纯水 陆行鸟`)*"
        )
        embed.add_field(name="💰 市场物价查询 (Market)", value=market_desc, inline=False)

        # 3. 时尚品鉴指南 (Fashion)
        fashion_desc = (
            "`!fs` - 查看本周最新的金蝶“时尚品鉴”满分作业与倒计时\n"
            "`!fs time` - 单独查看时尚品鉴的开放/结束倒计时\n"
            "*(注意：每周五固定时间会自动推送作业)*"
        )
        embed.add_field(name="👗 时尚品鉴指南 (Fashion)", value=fashion_desc, inline=False)

        # 4. 日历与活动 (Calendar)
        cal_desc = (
            "`!cal next` - 查看近期即将到来的节日或活动排期\n"
            "*(别名: `!cal 近期` 或 `!cal upcoming`)*"
        )
        embed.add_field(name="📆 日历与活动 (Calendar)", value=cal_desc, inline=False)

        # ==========================================
        # 5. [新加入] 高难查榜 (FFLogs)
        # ==========================================
        fflogs_desc = (
            "`!logs <服务器> <角色名>` - 查询玩家 FFLogs 国服最新零式战绩\n"
            "*(别名: `!fflogs`, `!log`)*\n"
            "*(例: `!logs 纯水 亚里沙` 或 `!logs 亚里沙 纯水`)*"
        )
        embed.add_field(name="⚔️ 高难查榜 (FFLogs)", value=fflogs_desc, inline=False)

        # 6. 管理员专属设置 (Admin)
        admin_desc = (
            "**[时尚品鉴设置]**\n"
            "`!fs setchannel` - 设定自动推送频道\n"
            "`!fs update <文字>` - 更新本周作业文本\n"
            "`!fs img <链接>` - 附加本周作业图片\n\n"
            "**[日历与节日提醒]**\n"
            "`!cal setchannel` - 设定日历提醒推送频道\n"
            "`!cal setlink <链接>` - 更新 iCloud/Google .ics 日历订阅链接\n"
            "`!cal test` - 立刻读取日历并测试今天的提醒"
        )
        embed.add_field(name="⚙️ 管理员专属设置 (Admin)", value=admin_desc, inline=False)

        # 底部小贴士 (完全还原你的原版提示)
        embed.set_footer(text="提示: 点击采集面板上的外链按钮可以直接跳转到网页地图哦！")

        # 尝试设置右上角的图标，如果机器人有头像则显示头像
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))