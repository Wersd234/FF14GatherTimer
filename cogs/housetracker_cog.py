import discord
from discord.ext import commands, tasks
import aiohttp
import datetime
from zoneinfo import ZoneInfo

# 指定澳大利亚时区
TZ_AUSTRALIA = ZoneInfo("Australia/Melbourne")
# 每天当地时间 19:00 运行
RUN_TIME = datetime.time(hour=19, minute=0, tzinfo=TZ_AUSTRALIA)


class HousingTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://house.ffxiv.cyou/api/sales"
        self.server_mapping = {"太阳海岸": 1180}

        # --- 核心映射表 (严格对应 API 数值) ---
        self.area_map = {0: "海雾村", 1: "薰衣草苗圃", 2: "高脚孤丘", 3: "白银乡", 4: "穹顶皓天"}
        self.area_name_to_id = {v: k for k, v in self.area_map.items()}

        self.size_map = {0: "S", 1: "M", 2: "L"}
        self.size_name_to_id = {"S": 0, "M": 1, "L": 2}

        # 1: 仅限部队, 2: 仅限个人
        self.region_map = {1: "仅限部队", 2: "仅限个人"}
        self.region_name_to_id = {"部队": 1, "仅限部队": 1, "个人": 2, "仅限个人": 2}

        # 1: 先到先得, 2: 抽签
        self.purchase_map = {0: "不可购买", 1: "先到先得", 2: "抽签"}
        self.purchase_name_to_id = {"先到先得": 1, "抽签": 2}

        self.state_map = {0: "未知", 1: "可购买", 2: "结果公示期", 3: "准备中"}
        self.state_name_to_id = {"可购买": 1, "公示": 2, "公示期": 2, "结果公示": 2, "准备中": 3}

        self.daily_reminder.start()

    def cog_unload(self):
        self.daily_reminder.cancel()

    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command(name='house', help='查询空房。用法: !house [服务器] [参数...]')
    async def check_house(self, ctx, *args):
        server_name = "太阳海岸"
        filter_args = list(args)

        # 1. 提取服务器名
        for arg in list(filter_args):
            if arg in self.server_mapping:
                server_name = arg
                filter_args.remove(arg)
                break

        server_id = self.server_mapping.get(server_name)

        # 2. 解析过滤参数 (将中文全部转为数字 ID)
        f_area = f_size = f_region = f_purchase = f_state = None

        for arg in filter_args:
            arg_u = arg.strip().upper()
            if arg in self.area_name_to_id:
                f_area = self.area_name_to_id[arg]
            elif arg_u in self.size_name_to_id:
                f_size = self.size_name_to_id[arg_u]
            elif arg in self.region_name_to_id:
                f_region = self.region_name_to_id[arg]
            elif arg in self.purchase_name_to_id:
                f_purchase = self.purchase_name_to_id[arg]
            elif arg in self.state_name_to_id:
                f_state = self.state_name_to_id[arg]

        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                try:
                    headers = {'User-Agent': 'FF14HousingBot/1.2'}
                    async with session.get(self.api_url, params={'server': server_id}, headers=headers) as resp:
                        if resp.status != 200:
                            await ctx.send("❌ 无法获取房源数据，请稍后再试。")
                            return
                        data = await resp.json()

                        if not data:
                            await ctx.send(f"🏘️ **{server_name}** 当前没有在售房源。")
                            return

                        # --- 核心修复：强制类型转换并应用筛选 ---
                        filtered_results = []
                        for item in data:
                            # 统一从 API 中提取并转为整数
                            try:
                                i_area = int(item.get('Area', -1))
                                i_size = int(item.get('Size', -1))
                                i_region = int(item.get('RegionType', -1))
                                i_purchase = int(item.get('PurchaseType', -1))
                                i_state = int(item.get('State', -1))
                            except:
                                continue

                            # 逐项比对
                            if f_area is not None and i_area != f_area: continue
                            if f_size is not None and i_size != f_size: continue
                            if f_region is not None and i_region != f_region: continue
                            if f_purchase is not None and i_purchase != f_purchase: continue
                            if f_state is not None and i_state != f_state: continue

                            filtered_results.append(item)

                        if not filtered_results:
                            await ctx.send(f"❌ 在 **{server_name}** 没找到符合要求的房源。")
                            return

                        # 按价格从低到高排序
                        filtered_results.sort(key=lambda x: x.get('Price', 999999999))

                        embed = discord.Embed(title=f"🏡 {server_name} 精选房源", color=discord.Color.gold())

                        for item in filtered_results[:15]:  # 只展示前15条，避免消息过长
                            size_str = self.size_map.get(int(item['Size']), "未知")
                            area_str = self.area_map.get(int(item['Area']), "未知区域")
                            ward = int(item['Slot']) + 1
                            plot = int(item['ID'])
                            price = int(item['Price'])

                            reg_str = self.region_map.get(int(item['RegionType']), "未知限制")
                            pur_str = self.purchase_map.get(int(item['PurchaseType']), "未知方式")
                            state_str = self.state_map.get(int(item['State']), "未知")
                            part = item.get('Participate', 0)

                            details = f"💰 **{price:,}** Gil | {reg_str} | {pur_str}\n📊 状态: {state_str} (参与: {part}人)"
                            embed.add_field(name=f"[{size_str}房] {area_str} {ward}区 {plot}号", value=details,
                                            inline=False)

                        embed.set_footer(text=f"共找到 {len(filtered_results)} 处房源 | 数据有延迟，以游戏内为准")
                        await ctx.send(embed=embed)

                except Exception as e:
                    await ctx.send(f"⚠️ 发生错误: {e}")

    # ================= 定时提醒部分也同步更新逻辑 =================
    @tasks.loop(time=RUN_TIME)
    async def daily_reminder(self):
        channel_id = getattr(self.bot, 'broadcast_channels', {}).get('house')
        if not channel_id: return
        channel = self.bot.get_channel(channel_id)
        if not channel: return

        now = datetime.datetime.now(TZ_AUSTRALIA)
        tomorrow = (now + datetime.timedelta(days=1)).date()

        async with aiohttp.ClientSession() as session:
            for s_name, s_id in self.server_mapping.items():
                try:
                    async with session.get(self.api_url, params={'server': s_id}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            upcoming = []
                            for item in data:
                                et = item.get('EndTime', 0)
                                if et == 0: continue
                                dt = datetime.datetime.fromtimestamp(et, tz=TZ_AUSTRALIA)
                                if dt.date() == tomorrow:
                                    upcoming.append((item, dt))

                            if upcoming:
                                embed = discord.Embed(title=f"⏰ {s_name} 购房预警 (明日截止)",
                                                      color=discord.Color.red())
                                for item, dt in upcoming[:10]:
                                    size = self.size_map.get(int(item['Size']), "?")
                                    area = self.area_map.get(int(item['Area']), "未知")
                                    embed.add_field(
                                        name=f"[{size}房] {area} {int(item['Slot']) + 1}区 {item['ID']}号",
                                        value=f"⌛ 截止时间: 明天 {dt.strftime('%H:%M')}",
                                        inline=False
                                    )
                                await channel.send(embed=embed)
                except:
                    continue

    @daily_reminder.before_loop
    async def before_daily_reminder(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(HousingTracker(bot))