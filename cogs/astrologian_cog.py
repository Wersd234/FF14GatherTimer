import discord
from discord.ext import commands
import random
import datetime
import json
import os
from zoneinfo import ZoneInfo

# 设置时区为墨尔本
TZ_AUSTRALIA = ZoneInfo("Australia/Melbourne")

# 定位持久化数据目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
DATA_DIR = os.path.join(project_root, 'data')
DRAW_DATA_FILE = os.path.join(DATA_DIR, 'daily_draw.json')


class AstrologianCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 卡池数据：图片建议使用官方图标链接或你自己的图库
        self.cards = [
            {
                "name": "太阳神之衡 (The Balance)",
                "desc": "🔥 **大吉**！今日输出爆表。无论是 Roll 点还是打本，你的伤害都将无可匹敌。",
                "advice": "宜：开荒、冲分、Roll 坐骑；忌：空蓝、断连击。",
                "color": discord.Color.red()
            },
            {
                "name": "世界树之干 (The Bole)",
                "desc": "🌳 **中吉**。稳如泰山。今日你将拥有钢铁般的防御，即便吃下机制也能屹立不倒。",
                "advice": "宜：带豆芽、练习机制；忌：乱拉怪、不点减伤。",
                "color": discord.Color.green()
            },
            {
                "name": "放浪神之箭 (The Arrow)",
                "desc": "🏹 **小吉**。极速如风。今日你的手感极佳，咏唱/战技速度飞快，效率拉满。",
                "advice": "宜：清 CD、挖宝；忌：由于延迟导致的卡顿。",
                "color": discord.Color.blue()
            },
            {
                "name": "长枪之矛 (The Spear)",
                "desc": "❄️ **小吉**。精准致命。今日你的直击暴击率大幅提升，满屏大数不是梦。",
                "advice": "宜：打极神、刷幻化；忌：断爆发、贪输出被炸死。",
                "color": discord.Color.dark_blue()
            },
            {
                "name": "河流之神 (The Ewer)",
                "desc": "💧 **平**。源远流长。虽然没有爆发，但你的资源和精神将非常充沛，适合稳定发育。",
                "advice": "宜：搓生产、刷友好部族；忌：激进冒险。",
                "color": discord.Color.teal()
            },
            {
                "name": "建筑神之塔 (The Spire)",
                "desc": "⚡ **平**。根基稳固。今日适合处理琐事，稳扎稳打地完成每一个小目标。",
                "advice": "宜：整理仓库、理符任务；忌：浮躁、半途而废。",
                "color": discord.Color.gold()
            },
            {
                "name": "奥秘之王 (Lord of Crowns)",
                "desc": "⚔️ **大吉**。霸者降临。近战职业的终极加持！今日你就是战场的主宰。",
                "advice": "宜：PVP、排随机本；忌：怂。",
                "color": discord.Color.purple()
            },
            {
                "name": "奥秘之妃 (Lady of Crowns)",
                "desc": "👑 **中吉**。母仪天下。奶妈/远程职业的福音。今日你将备受队友信赖，治疗量拉满。",
                "advice": "宜：社交、加部队、救场；忌：放生坦克。",
                "color": discord.Color.magenta()
            }
        ]
        self.user_data = self._load_data()

    def _load_data(self):
        if os.path.exists(DRAW_DATA_FILE):
            try:
                with open(DRAW_DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_data(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DRAW_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.user_data, f, ensure_ascii=False, indent=4)

    @commands.command(name='draw', aliases=['tarot', '占星', '抽卡', '运势'])
    async def daily_draw(self, ctx):
        """占星术士的每日运势抽卡（每天 0 点刷新）"""
        user_id = str(ctx.author.id)
        # 获取墨尔本当前的日期 (格式: YYYY-MM-DD)
        today = datetime.datetime.now(TZ_AUSTRALIA).strftime("%Y-%m-%d")

        # 检查今天是否已经抽过
        if user_id in self.user_data and self.user_data[user_id]['date'] == today:
            card_info = self.user_data[user_id]['card']
            await ctx.send(
                f"🔮 {ctx.author.mention}，你今天已经抽过牌了！\n你抽到的是：**{card_info['name']}**\n今日评价：{card_info['desc']}")
            return

        # 执行抽卡
        selected_card = random.choice(self.cards)

        # 记录数据
        self.user_data[user_id] = {
            'date': today,
            'card': {
                'name': selected_card['name'],
                'desc': selected_card['desc']
            }
        }
        self._save_data()

        # 构建 Embed 展示
        embed = discord.Embed(
            title=f"✨ {ctx.author.display_name} 的每日占星预言",
            description=f"你从奥秘卡组中抽中了：\n\n### **{selected_card['name']}**",
            color=selected_card['color'],
            timestamp=datetime.datetime.now(TZ_AUSTRALIA)
        )
        embed.add_field(name="📜 运势解析", value=selected_card['desc'], inline=False)
        embed.add_field(name="💡 艾欧泽亚指南", value=selected_card['advice'], inline=False)
        embed.set_footer(text="愿太阳神指引你的前路 | 每日 00:00 刷新")

        # 设置一个统一的占星术士图标作为缩略图
        embed.set_thumbnail(url="https://img.finalfantasyxiv.com/lds/h/X/zM7T2-f0S7-yW2R6v1V4-u5Z_o.png")

        await ctx.send(content=f"🔮 {ctx.author.mention} 屏气凝神，从卡组中抽出了一张牌...", embed=embed)


async def setup(bot):
    await bot.add_cog(AstrologianCog(bot))