import discord
from discord.ext import commands
import aiohttp
import urllib.parse
import json
import os

FFLOGS_CLIENT_ID = os.getenv('FFLOGS_CLIENT_ID')
FFLOGS_CLIENT_SECRET = os.getenv('FFLOGS_CLIENT_SECRET')

CN_SERVERS = [
    "红玉海", "神意之地", "拉诺西亚", "幻影群岛", "萌芽池", "宇宙和音", "沃仙曦染", "晨曦王座",
    "白银乡", "白金幻象", "神拳痕", "潮风亭", "旅人栈桥", "拂晓之间", "龙巢神殿", "梦羽宝境",
    "紫水栈桥", "延夏", "静语庄园", "摩杜纳", "海猫茶屋", "柔风海湾", "琥珀原",
    "水晶塔", "银泪湖", "太阳海岸", "伊修加德", "红茶川"
]


class FFLogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.token = None  # 用于缓存 OAuth2 Token

    async def get_fflogs_token(self):
        """获取 FFLogs V2 API 的 Access Token"""
        if not FFLOGS_CLIENT_ID or FFLOGS_CLIENT_ID == "YOUR_CLIENT_ID":
            return None

        token_url = "https://cn.fflogs.com/oauth/token"
        data = {"grant_type": "client_credentials"}
        auth = aiohttp.BasicAuth(FFLOGS_CLIENT_ID, FFLOGS_CLIENT_SECRET)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=data, auth=auth) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        self.token = response_data.get("access_token")
                        return self.token
        except Exception as e:
            print(f"获取 FFLogs Token 失败: {e}")
        return None

    def get_color_from_parse(self, parse_percent):
        """根据 Parse 评分返回颜色和标签"""
        if parse_percent is None: return discord.Color.light_gray(), "⚪ 无数据"
        p = float(parse_percent)
        if p >= 99: return 0xe268a8, "🌟 粉色 (99+)"  # 粉
        if p >= 95: return 0xff8000, "🟧 橙色 (95-98)"  # 橙
        if p >= 75: return 0xa335ee, "🟪 紫色 (75-94)"  # 紫
        if p >= 50: return 0x0070ff, "🟦 蓝色 (50-74)"  # 蓝
        if p >= 25: return 0x1eff00, "🟩 绿色 (25-49)"  # 绿
        return 0x666666, "🟫 灰色 (0-24)"  # 灰

    @commands.command(name='logs', aliases=['fflogs', 'log'])
    async def get_fflogs(self, ctx, *args):
        """生成 FFLogs 并在 Discord 直接显示评分"""
        if len(args) < 2:
            await ctx.send("❌ 格式错误：`!logs <服务器> <角色名>` (例: `!logs 幻影群岛 亚里沙 罗森博格`)")
            return

        server = args[0] if args[0] in CN_SERVERS else args[-1] if args[-1] in CN_SERVERS else args[0]
        char_name = " ".join(args[1:]) if server == args[0] else " ".join(args[:-1])

        loading = await ctx.send("⏳ 正在潜入 FFLogs 后台调取战斗记录...")

        # 1. 确保有 API Token
        if not self.token:
            await self.get_fflogs_token()
        if not self.token:
            await loading.edit(content="❌ **未配置 API Key** 或 Token 获取失败，请管理员检查代码中的 ID 和 Secret。")
            return

        # 2. 构建 GraphQL 查询请求 (获取当前最新零式的数据)
        graphql_query = """
        query($name: String!, $server: String!) {
          characterData {
            character(name: $name, serverSlug: $server, serverRegion: "CN") {
              hidden
              zoneRankings
            }
          }
        }
        """

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        payload = {
            "query": graphql_query,
            "variables": {"name": char_name, "server": server}
        }

        # 3. 发送请求获取数据
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://cn.fflogs.com/api/v2/client", headers=headers, json=payload) as resp:
                    if resp.status == 401:  # Token 过期，重试
                        await self.get_fflogs_token()
                        headers["Authorization"] = f"Bearer {self.token}"
                        async with session.post("https://cn.fflogs.com/api/v2/client", headers=headers,
                                                json=payload) as retry_resp:
                            data = await retry_resp.json()
                    else:
                        data = await resp.json()

            # 解析数据
            char_data = data.get("data", {}).get("characterData", {}).get("character")

            # 生成直达链接
            encoded_server = urllib.parse.quote(server)
            encoded_name = urllib.parse.quote(char_name)
            fflogs_url = f"https://cn.fflogs.com/character/cn/{encoded_server}/{encoded_name}"

            # 异常情况处理
            if not char_data:
                await loading.edit(
                    content=f"❌ **找不到角色**：在 FFLogs 国服中未查找到 **{char_name}** ({server}) 的记录。\n[🔗 点击此处手动核实页面]({fflogs_url})")
                return

            if char_data.get("hidden"):
                await loading.edit(
                    content=f"🔒 **记录已隐藏**：该玩家选择在 FFLogs 隐藏了自己的战斗数据。\n[🔗 点击前往页面]({fflogs_url})")
                return

            # 获取当前最高难度副本数据 (最新零式)
            zone_rankings = char_data.get("zoneRankings", {})
            best_avg = zone_rankings.get("bestPerformanceAverage")

            if best_avg is None:
                await loading.edit(
                    content=f"ℹ️ **无近期高难记录**：该玩家在当前版本可能还没有上传过零式过本数据。\n[🔗 点击前往页面]({fflogs_url})")
                return

            # 根据 Best Avg 计算面板颜色
            embed_color, grade_text = self.get_color_from_parse(best_avg)

            embed = discord.Embed(
                title=f"📊 {char_name} 的近期高难战绩",
                description=f"**🌍 服务器:** {server}\n**🏆 最佳平均表现:** {best_avg:.1f} ({grade_text})\n\n**各层详细表现：**",
                color=embed_color
            )

            # 遍历每个 Boss (M1S, M2S, etc.)
            rankings = zone_rankings.get("rankings", [])
            for fight in rankings:
                boss_name = fight.get("encounter", {}).get("name", "未知首领")
                percent = fight.get("rankPercent")
                if percent is None:
                    continue

                _, fight_grade = self.get_color_from_parse(percent)
                # 简化 Boss 名字显示，提取层数
                embed.add_field(name=f"⚔️ {boss_name}", value=f"**{percent:.1f}** [{fight_grade.split(' ')[1]}]",
                                inline=True)

            embed.add_field(name="\u200b", value=f"[🔗 >> 点击这里直达完整详情页面 <<]({fflogs_url})", inline=False)
            embed.set_thumbnail(url="https://assets.rpglogs.com/img/ff/favicon.png")
            embed.set_footer(text="数据基于当前版本的最高难度(通常为最新零式)。数据仅供参考，请理性查榜。")

            await loading.edit(content=None, embed=embed)

        except Exception as e:
            print(f"FFLogs 数据请求异常: {e}")
            await loading.edit(content="⚠️ **系统错误**：无法连接到 FFLogs 数据库，请稍后再试或检查服务器网络。")


async def setup(bot):
    await bot.add_cog(FFLogsCog(bot))