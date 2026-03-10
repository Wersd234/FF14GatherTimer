import discord
from discord.ext import commands
import aiohttp
import datetime
import urllib.parse


class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 国服大区拼音映射表
        self.dc_map = {
            "猫小胖": "MaoXiaoPang",
            "陆行鸟": "LuXingNiao",
            "莫古力": "MoGuli",
            "神意之地": "ShenYiJian",
            "豆豆柴": "DouDouChai"
        }
        self.default_dc = "DouDouChai"  # 默认大区：猫小胖 (你可以改成你所在的大区)

    async def _get_item_id_and_icon(self, item_name: str, session: aiohttp.ClientSession):
        """调用 Cafemaker API 将中文名转换为物品 ID"""
        # URL 编码处理中文字符
        safe_name = urllib.parse.quote(item_name)
        url = f"https://cafemaker.wakingsands.com/search?string={safe_name}&indexes=Item"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("Results", [])
                    if not results:
                        return None, None, None

                    # 取第一个匹配的结果
                    first_match = results[0]
                    item_id = first_match.get("ID")
                    exact_name = first_match.get("Name")
                    icon_path = first_match.get("Icon")

                    return item_id, exact_name, icon_path
        except Exception as e:
            print(f"搜索物品 ID 失败: {e}")
        return None, None, None

    async def _get_market_data(self, item_id: int, dc_name: str, session: aiohttp.ClientSession):
        """调用 Universalis API 获取物价数据"""
        # listings=5 表示只取最便宜的 5 个在售，entries=5 表示取最近 5 条成交记录
        url = f"https://universalis.app/api/v2/{dc_name}/{item_id}?listings=5&entries=5"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 404:
                    return "untradeable"  # 物品不可交易
        except Exception as e:
            print(f"获取物价失败: {e}")
        return None

    @commands.command(name='price', aliases=['mb', '物价', '查价'])
    async def price_command(self, ctx, item_name: str, dc_input: str = None):
        """
        查询物价指令。用法: !price 纯水 [大区名]
        例如: !price 纯水 或 !price 纯水 莫古力
        """
        # 确定要查询的大区
        target_dc = self.default_dc
        dc_display_name = "豆豆柴"

        if dc_input:
            if dc_input in self.dc_map:
                target_dc = self.dc_map[dc_input]
                dc_display_name = dc_input
            else:
                await ctx.send(f"⚠️ 未知的大区名: `{dc_input}`。支持的大区有: {', '.join(self.dc_map.keys())}")
                return

        # 发送正在查询的提示
        loading_msg = await ctx.send(f"🔍 正在查询 **{dc_display_name}** 大区的 `{item_name}` 物价，请稍候...")

        async with aiohttp.ClientSession() as session:
            # 1. 获取物品 ID
            item_id, exact_name, icon_path = await self._get_item_id_and_icon(item_name, session)

            if not item_id:
                await loading_msg.edit(content=f"❌ 找不到名为 `{item_name}` 的物品，请检查拼写是否完全正确。")
                return

            # 2. 获取市场数据
            market_data = await self._get_market_data(item_id, target_dc, session)

            if market_data == "untradeable":
                await loading_msg.edit(content=f"🛑 物品 **{exact_name}** (ID: {item_id}) 存在，但它是不可交易的物品。")
                return
            if not market_data:
                await loading_msg.edit(content=f"⚠️ 无法连接到 Universalis 市场 API，请稍后再试。")
                return

            # 3. 解析并构建 Embed
            listings = market_data.get('listings', [])
            history = market_data.get('recentHistory', [])

            embed = discord.Embed(
                title=f"💰 {exact_name} - {dc_display_name} 物价",
                url=f"https://universalis.app/market/{item_id}",
                color=discord.Color.gold()
            )

            # 如果有图标，加上小图标
            if icon_path:
                embed.set_thumbnail(url=f"https://cafemaker.wakingsands.com{icon_path}")

            # 解析在售列表
            if not listings:
                embed.add_field(name="📦 当前在售", value="当前大区没有任何出售记录。", inline=False)
            else:
                sell_text = ""
                for item in listings:
                    price = item.get('pricePerUnit', 0)
                    qty = item.get('quantity', 0)
                    world = item.get('worldName', '未知服务器')
                    hq_str = "✨(HQ) " if item.get('hq') else " "
                    sell_text += f"**{price:,}** 金币 x {qty} {hq_str} @ {world}\n"
                embed.add_field(name="📉 最低在售 (Top 5)", value=sell_text, inline=False)

            # 解析最近成交记录
            if not history:
                embed.add_field(name="📜 最近成交", value="近期没有成交记录。", inline=False)
            else:
                history_text = ""
                for item in history:
                    price = item.get('pricePerUnit', 0)
                    qty = item.get('quantity', 0)
                    world = item.get('worldName', '未知服务器')
                    hq_str = "✨(HQ) " if item.get('hq') else " "

                    # 转换时间戳为可视时间
                    ts = item.get('timestamp')
                    dt = datetime.datetime.fromtimestamp(ts)
                    time_str = dt.strftime('%m-%d %H:%M')

                    history_text += f"**{price:,}** 金币 x {qty} {hq_str} @ {world} `({time_str})`\n"
                embed.add_field(name="📜 最近成交记录", value=history_text, inline=False)

            embed.set_footer(text="数据来源: Universalis API | 价格可能有延迟")

            # 替换掉之前的 "正在查询" 消息
            await loading_msg.edit(content=None, embed=embed)


async def setup(bot):
    await bot.add_cog(MarketCog(bot))