import discord
from discord.ext import commands, tasks
import aiohttp
import datetime
from icalendar import Calendar
import recurring_ical_events
import json
import os
from collections import defaultdict

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
HOLIDAY_CONFIG_FILE = os.path.join(project_root, 'data/holiday_config.json')


class HolidayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self._load_data()
        self.weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self.daily_holiday_check.start()

    def cog_unload(self):
        self.daily_holiday_check.cancel()

    def _load_data(self):
        if os.path.exists(HOLIDAY_CONFIG_FILE):
            try:
                with open(HOLIDAY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        # 默认配置 (移除了 channel_id，因为现在由 CoreSettings 管理)
        return {
            "calendar_url": "https://calendar.google.com/calendar/ical/up88drvlnnh2t77hbpqq8v33i2cngfh7%40import.calendar.google.com/public/basic.ics",
            "check_hour": 8,
            "check_minute": 0
        }

    def _save_data(self):
        temp_file = f"{HOLIDAY_CONFIG_FILE}.tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, HOLIDAY_CONFIG_FILE)
        except Exception as e:
            print(f"保存日历配置失败: {e}")

    async def fetch_and_parse_calendar(self):
        url = self.config.get("calendar_url")
        if not url or not url.startswith("http"):
            return "ERROR_INVALID_URL"

        now = datetime.datetime.now()
        today = now.date()
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status != 200:
                        return f"ERROR_{resp.status}"
                    ics_data = await resp.read()

            cal = Calendar.from_ical(ics_data)
            future_limit = today + datetime.timedelta(days=90)
            actual_events = recurring_ical_events.of(cal).between(today, future_limit)

            ongoing = []
            upcoming = defaultdict(list)
            seen = set()

            for component in actual_events:
                start_val = component.get('dtstart').dt
                end_val = component.get('dtend').dt if component.get('dtend') else start_val

                start_date = start_val.date() if isinstance(start_val, datetime.datetime) else start_val
                end_date = end_val.date() if isinstance(end_val, datetime.datetime) else end_val

                if not isinstance(end_val, datetime.datetime) and start_date != end_date:
                    end_date = end_date - datetime.timedelta(days=1)

                summary = str(component.get('summary', '未知事件'))
                description = str(component.get('description', '')).strip()

                identifier = f"{start_date}_{summary}"
                if identifier in seen:
                    continue
                seen.add(identifier)

                ev = {"start": start_date, "end": end_date, "title": summary, "desc": description}

                if start_date <= today <= end_date:
                    ongoing.append(ev)
                elif start_date > today:
                    upcoming[start_date].append(ev)

            sorted_dates = sorted(upcoming.keys())
            limited_upcoming = defaultdict(list)
            count = 0
            for d in sorted_dates:
                for ev in upcoming[d]:
                    if count >= 10: break
                    limited_upcoming[d].append(ev)
                    count += 1
                if count >= 10: break

            return {"ongoing": ongoing, "upcoming": limited_upcoming}
        except Exception as e:
            print(f"解析日历出错: {e}")
            return "ERROR_PARSE_FAILED"

    # ================= 保持原有时区和时间不变 =================
    @tasks.loop(minutes=1)
    async def daily_holiday_check(self):
        now = datetime.datetime.now()
        if now.hour == self.config["check_hour"] and now.minute == self.config["check_minute"]:
            # 【核心修改】统一从 bot.broadcast_channels 读取 cal 的频道 ID
            channel_id = getattr(self.bot, 'broadcast_channels', {}).get('cal')
            if not channel_id:
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                return

            events_data = await self.fetch_and_parse_calendar()

            if isinstance(events_data, dict) and events_data["ongoing"]:
                embed = discord.Embed(title="🎉 今天的活动与安排", color=discord.Color.brand_red())
                for ev in events_data["ongoing"]:
                    desc = ev["desc"] if ev["desc"] else "无详细描述"
                    embed.add_field(name=f"✨ {ev['title']}", value=desc, inline=False)
                embed.set_footer(text="📅 自动日历提醒")
                await channel.send("📢 **【日常提醒】**", embed=embed)

    @daily_holiday_check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.group(name='cal', invoke_without_command=True)
    async def cal_group(self, ctx):
        # 【核心修改】从帮助菜单中移除了 `!cal setchannel`
        help_text = (
            "**公共指令：**\n"
            "`!cal next` - 查看近期的所有活动排期\n\n"
            "**管理员指令：**\n"
            "`!cal setlink <URL>` - 设置谷歌 `.ics` 日历链接\n"
            "`!cal test` - 立刻测试今天的日历"
        )
        embed = discord.Embed(title="📅 日历模块帮助", description=help_text, color=discord.Color.blue())
        await ctx.send(embed=embed)

    @cal_group.command(name='next', aliases=['upcoming', '近期'])
    async def next_holidays(self, ctx):
        loading = await ctx.send("⏳ 正在获取日历数据...")
        events_data = await self.fetch_and_parse_calendar()

        if isinstance(events_data, str):
            if "INVALID_URL" in events_data:
                await loading.edit(
                    content="❌ **未绑定链接！** 请管理员先使用 `!cal setlink <你的谷歌日历ics链接>` 进行绑定。")
            else:
                await loading.edit(content=f"❌ **读取失败！** 错误代码: `{events_data}`")
            return

        ongoing = events_data["ongoing"]
        upcoming = events_data["upcoming"]

        embed = discord.Embed(title="📅 社区活动排期板", color=discord.Color.teal())

        if ongoing:
            ongoing_text = ""
            for ev in ongoing:
                if ev['start'] == ev['end']:
                    date_str = "[今天]"
                else:
                    date_str = f"[{ev['start'].strftime('%m/%d')} - {ev['end'].strftime('%m/%d')}]"

                ongoing_text += f"**{date_str}** ✨ **{ev['title']}**\n"
                if ev['desc']:
                    ongoing_text += f"└ *{ev['desc']}*\n"

            embed.add_field(name="🔥 正在进行中", value=ongoing_text, inline=False)

        if upcoming:
            embed.add_field(name="━━━━━━━━━━━━━━━━━\n⏳ 马上到来", value="\u200b", inline=False)

            today = datetime.datetime.now().date()
            for d, ev_list in upcoming.items():
                days_left = (d - today).days
                if days_left == 1:
                    time_str = "明天"
                elif days_left == 2:
                    time_str = "后天"
                else:
                    time_str = f"{days_left} 天后"

                date_header = f"📅 {d.month}月{d.day}日 ({self.weekdays[d.weekday()]}) - {time_str}"

                ev_text = ""
                for ev in ev_list:
                    ev_text += f"✨ **{ev['title']}**\n"
                    if ev['desc']:
                        ev_text += f"└ *{ev['desc']}*\n"

                embed.add_field(name=date_header, value=ev_text, inline=False)

        if not ongoing and not upcoming:
            embed.description = "ℹ️ 日历中目前没有任何正在进行或马上到来的活动。"

        await loading.edit(content=None, embed=embed)

    # 【核心修改】删除了原本的 @cal_group.command(name='setchannel')

    @cal_group.command(name='setlink')
    @commands.has_permissions(administrator=True)
    async def set_link(self, ctx, url: str):
        if not url.endswith('.ics'):
            await ctx.send("⚠️ 警告：这看起来不像是一个有效的 `.ics` 链接，但已为你保存。")
        self.config["calendar_url"] = url
        self._save_data()
        await ctx.send(f"✅ 谷歌日历链接已绑定！使用 `!cal next` 看看排版效果吧。")

    @cal_group.command(name='test')
    @commands.has_permissions(administrator=True)
    async def test_cal(self, ctx):
        await ctx.send("⏳ 正在测试读取...")
        events_data = await self.fetch_and_parse_calendar()

        if isinstance(events_data, str):
            await ctx.send(f"❌ 测试失败: `{events_data}`")
            return

        if events_data["ongoing"]:
            embed = discord.Embed(title="🎉 今天正在进行的活动", color=discord.Color.green())
            for ev in events_data["ongoing"]:
                desc = ev["desc"] if ev["desc"] else "无详细描述"
                embed.add_field(name=f"✨ {ev['title']}", value=desc, inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("ℹ️ 测试成功，链接可以正常访问，但今天没有任何活动。")


async def setup(bot):
    await bot.add_cog(HolidayCog(bot))