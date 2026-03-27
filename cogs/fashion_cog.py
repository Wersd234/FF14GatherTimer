import discord
from discord.ext import commands, tasks
import json
import os
import datetime

# 获取项目根目录，将数据存入持久化文件
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
FASHION_FILE = os.path.join(project_root, 'data/fashion_data.json')


class FashionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self._load_data()
        self.auto_reminder.start()

    def cog_unload(self):
        self.auto_reminder.cancel()

    def _load_data(self):
        if os.path.exists(FASHION_FILE):
            try:
                with open(FASHION_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        # 默认数据结构 (移除了 channel_id，因为现在由 CoreSettings 管理)
        return {
            "guide_text": "本周作业尚未更新，请等待管理员上传！",
            "image_url": None,
            "last_updated": "未知"
        }

    def _save_data(self):
        temp_file = f"{FASHION_FILE}.tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, FASHION_FILE)
        except Exception as e:
            print(f"保存时尚品鉴数据失败: {e}")

    def _get_fashion_report_status(self):
        now = datetime.datetime.now(datetime.timezone.utc)

        days_to_tue = (1 - now.weekday()) % 7
        if days_to_tue == 0 and now.hour >= 8:
            days_to_tue = 7
        next_tue = (now + datetime.timedelta(days=days_to_tue)).replace(hour=8, minute=0, second=0, microsecond=0)

        days_to_fri = (4 - now.weekday()) % 7
        if days_to_fri == 0 and now.hour >= 8:
            days_to_fri = 7
        next_fri = (now + datetime.timedelta(days=days_to_fri)).replace(hour=8, minute=0, second=0, microsecond=0)

        if next_fri < next_tue:
            delta = next_fri - now
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return "⏳ **【准备期】评分尚未开放**", f"距离本周开放评分还有：**{delta.days}天 {hours}小时 {minutes}分钟**"
        else:
            delta = next_tue - now
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return "✅ **【进行中】可以去金蝶交作业啦！**", f"距离本期结束(周二)还有：**{delta.days}天 {hours}小时 {minutes}分钟**"

    # ================= 保持原有时区和时间不变 =================
    post_time = datetime.time(hour=9, minute=0, tzinfo=datetime.timezone.utc)

    @tasks.loop(time=post_time)
    async def auto_reminder(self):
        if datetime.datetime.now(datetime.timezone.utc).weekday() == 4:
            # 【核心修改】统一从 bot.broadcast_channels 读取 fs 的频道 ID
            channel_id = getattr(self.bot, 'broadcast_channels', {}).get('fs')
            if not channel_id:
                return  # 未设置频道则不发

            channel = self.bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title="👗 金蝶游乐场 - 时尚品鉴评分已开放！",
                    description="本周的时尚品鉴已经可以开始游玩评分啦！\n\n你可以使用 `!fs` 指令查看当前保存的满分/80分作业。\n*(如果作业还未更新，请耐心等待管理员搬运)*",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url="https://img.finalfantasyxiv.com/lds/h/W/m8XW7oI6J4LszP2t-oY2Z_LwE0.png")
                try:
                    await channel.send("📢 **【周末金蝶提醒】**", embed=embed)
                except Exception as e:
                    print(f"发送时尚品鉴自动提醒失败: {e}")

    @auto_reminder.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    @commands.group(name='fs', aliases=['fashion', '时尚品鉴'], invoke_without_command=True)
    async def fashion_group(self, ctx):
        status_title, status_desc = self._get_fashion_report_status()
        embed = discord.Embed(
            title="👗 本周时尚品鉴作业 (Fashion Report)",
            description=self.config["guide_text"],
            color=discord.Color.magenta()
        )
        embed.add_field(name=status_title, value=status_desc, inline=False)
        if self.config.get("image_url"):
            embed.set_image(url=self.config["image_url"])
        embed.set_footer(text=f"最后更新时间: {self.config['last_updated']}")
        await ctx.send(embed=embed)

    @fashion_group.command(name='time', aliases=['cd', '倒计时'])
    async def check_time(self, ctx):
        status_title, status_desc = self._get_fashion_report_status()
        embed = discord.Embed(title=status_title, description=status_desc, color=discord.Color.blue())
        await ctx.send(embed=embed)

    # 【核心修改】删除了原本的 @fashion_group.command(name='setchannel')

    @fashion_group.command(name='update')
    @commands.has_permissions(administrator=True)
    async def update_guide(self, ctx, *, text: str):
        self.config["guide_text"] = text
        self.config["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.config["image_url"] = None
        self._save_data()
        await ctx.send("✅ 本周作业已更新！使用 `!fs img <图片链接>` 可以附加图片。")
        await self.fashion_group(ctx)

    @fashion_group.command(name='img', aliases=['image'])
    @commands.has_permissions(administrator=True)
    async def set_image(self, ctx, url: str):
        if not url.startswith("http"):
            await ctx.send("❌ 请提供一个有效的图片 HTTP/HTTPS 链接。")
            return
        self.config["image_url"] = url
        self.config["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self._save_data()
        await ctx.send("✅ 图片已添加！")
        await self.fashion_group(ctx)


async def setup(bot):
    await bot.add_cog(FashionCog(bot))