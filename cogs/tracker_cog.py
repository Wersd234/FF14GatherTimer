import discord
from discord.ext import commands
import csv
import time
import datetime
from typing import List, Dict, Optional
from collections import defaultdict
from discord.ui import View, Button
import asyncio
import json
import os
import aiohttp

MAP_ID_MAP = {}
# 获取项目根目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
map_id_filepath = os.path.join(project_root, 'map_id.json')

if os.path.exists(map_id_filepath):
    try:
        with open(map_id_filepath, 'r', encoding='utf-8') as f:
            MAP_ID_MAP = json.load(f)
        print(f"🗺️ 成功加载地图 ID 映射表，共 {len(MAP_ID_MAP)} 个区域。")
    except Exception as e:
        print(f"❌ 读取 map_id.json 失败: {e}")
else:
    print(f"⚠️ 找不到 {map_id_filepath} 文件，外部地图精确跳转功能将受限。")

# --- 常量定义 ---
NORMAL_REFRESH_INTERVAL = 60
MEDIUM_THRESHOLD_SECONDS = 30
MEDIUM_REFRESH_INTERVAL = 5
URGENT_THRESHOLD_SECONDS = 10
URGENT_REFRESH_INTERVAL = 1
EORZEA_MULTIPLIER = 3600 / 175
LOOP_INTERVAL = 1.0
MAX_EMBED_FIELDS = 25
WATCHLIST_FILE = 'watchlists.json'
PING_FILE = 'pings.json'


class GatheringMapView(View):
    def __init__(self, grouped_events):
        super().__init__(timeout=None)
        count = 0
        for (region, coords), materials in grouped_events.items():
            if count >= 25: break

            x_str, y_str = "", ""
            try:
                coords_clean = coords.replace('[', '').replace(']', '').strip()
                if ',' in coords_clean:
                    x_str, y_str = [s.strip() for s in coords_clean.split(',')]
            except Exception:
                pass

            map_id = MAP_ID_MAP.get(region)

            if map_id and x_str and y_str:
                web_map_url = f"https://map.wakingsands.com/#f=mark&id={map_id}&x={x_str}&y={y_str}"
            elif map_id:
                web_map_url = f"https://map.wakingsands.com/#f=area&id={map_id}"
            else:
                web_map_url = "https://map.wakingsands.com/"

            btn = Button(
                style=discord.ButtonStyle.link,
                label=f"🎯 在肥肥咖啡查看：{region} ({coords})",
                url=web_map_url
            )
            self.add_item(btn)
            count += 1


class TrackerInstance:
    def __init__(self, bot, author, channel, all_nodes_data, manual_offset, user_watchlist, track_all, user_pings,
                 all_watchlists):
        self.bot, self.author, self.channel, self.all_nodes_data, self.manual_offset, self.user_watchlist, self.track_all, self.user_pings, self.all_watchlists = bot, author, channel, all_nodes_data, manual_offset, user_watchlist, track_all, user_pings, all_watchlists
        self.background_task = self.tracker_message = None
        self.monitored_nodes = []
        self.pinged_users_this_spawn = set()

        self.current_upcoming_events = []
        self.current_time_remaining = 0

    async def start(self):
        self._prepare_monitored_nodes()
        if not self.monitored_nodes:
            msg = f"**{self.author.display_name}**，你的关注列表为空，或列表中没有任何项目在追踪时间内。"
            if self.track_all: msg = "未能从CSV文件中加载任何有效的采集点数据。"
            await self.channel.send(msg)
            return False
        try:
            embed, view = self._build_first_embed()
            self.tracker_message = await self.channel.send(embed=embed, view=view)
            self.background_task = self.bot.loop.create_task(self.tracker_loop())
            return True
        except Exception as e:
            await self.channel.send(f"启动追踪器时发生错误: {e}")
            return False

    async def stop(self):
        if self.background_task: self.background_task.cancel()
        if self.tracker_message:
            try:
                await self.tracker_message.delete()
            except discord.errors.NotFound:
                pass

    def _prepare_monitored_nodes(self):
        initial_time = time.time() + self.manual_offset
        full_node_list = []
        for node_data in self.all_nodes_data:
            start_et_str = node_data.get('开始ET')
            if start_et_str and start_et_str.strip().isdigit():
                et_hour = int(start_et_str.strip())
                next_ts = self._get_next_occurrence_timestamp(et_hour, initial_time)
                if next_ts: full_node_list.append({'data': node_data, 'next_ts': next_ts, 'et_hour': et_hour})
        if self.track_all or not self.user_watchlist:
            self.monitored_nodes = full_node_list
        else:
            self.monitored_nodes = [n for n in full_node_list if n['data'].get('材料名CN') in self.user_watchlist]

    def _build_first_embed(self):
        initial_time = time.time() + self.manual_offset
        soonest_ts = min(node['next_ts'] for node in self.monitored_nodes)
        time_remaining = soonest_ts - initial_time

        # 容差改为 2.0，确保同时间的采集点都在一起
        upcoming_events = [n for n in self.monitored_nodes if abs(n['next_ts'] - soonest_ts) < 2.0]
        grouped_events = defaultdict(list)
        for event in upcoming_events:
            data = event['data']
            key = (data.get('地区CN', 'N/A'), data.get('具体坐标', 'N/A'))
            grouped_events[key].append(data.get('材料名CN', 'N/A'))

        embed = self._build_embed(upcoming_events, grouped_events, time_remaining)
        view = GatheringMapView(grouped_events)

        return embed, view

    async def tracker_loop(self):
        await self.bot.wait_until_ready()
        last_update_time = time.time()
        while not self.bot.is_closed():
            loop_start_time = time.time()
            now = loop_start_time + self.manual_offset
            if not self.monitored_nodes: await asyncio.sleep(LOOP_INTERVAL); continue

            # 👇 核心修复 1：强制跨越节点
            updated_any = False
            for node in self.monitored_nodes:
                # 提前 1 秒判定到达时间，避免 00:00 死锁
                if now >= node['next_ts'] - 1.0:
                    # now + 2 确保计算下一个时间时，基准点已经在这个节点之后了
                    node['next_ts'] = self._get_next_occurrence_timestamp(node['et_hour'], now + 2)
                    updated_any = True

            soonest_ts_after_update = min(n['next_ts'] for n in self.monitored_nodes)
            time_remaining = soonest_ts_after_update - now
            upcoming_events = [n for n in self.monitored_nodes if abs(n['next_ts'] - soonest_ts_after_update) < 2.0]

            self.current_upcoming_events = upcoming_events
            self.current_time_remaining = time_remaining

            should_update_display = False
            # 👇 核心修复 2：一旦有物品更迭了时间，强制刷新面板
            if updated_any:
                self.pinged_users_this_spawn.clear()
                should_update_display = True
            elif time_remaining <= URGENT_THRESHOLD_SECONDS:
                should_update_display = True
            elif time_remaining <= MEDIUM_THRESHOLD_SECONDS:
                if (now - last_update_time) >= MEDIUM_REFRESH_INTERVAL: should_update_display = True
            elif (now - last_update_time) >= NORMAL_REFRESH_INTERVAL:
                should_update_display = True

            if should_update_display:
                last_update_time = now
                grouped_events = defaultdict(list)
                for event in upcoming_events:
                    data = event['data']
                    key = (data.get('地区CN', 'N/A'), data.get('具体坐标', 'N/A'))
                    grouped_events[key].append(data.get('材料名CN', 'N/A'))

                embed = self._build_embed(upcoming_events, grouped_events, time_remaining)
                view = GatheringMapView(grouped_events)

                try:
                    if self.tracker_message:
                        await self.tracker_message.edit(embed=embed, view=view)
                except (discord.errors.NotFound, discord.errors.HTTPException):
                    self.tracker_message = await self.channel.send(embed=embed, view=view)

            processing_time = time.time() - loop_start_time
            sleep_duration = LOOP_INTERVAL - processing_time
            if sleep_duration > 0: await asyncio.sleep(sleep_duration)

    async def _check_and_send_pings(self, upcoming_events, time_remaining):
        for user_id_str, ping_time in self.user_pings.items():
            user_id = int(user_id_str)
            is_valid_ping = ping_time > 0
            not_pinged_yet = user_id not in self.pinged_users_this_spawn
            is_time_to_ping = ping_time >= time_remaining > ping_time - LOOP_INTERVAL
            if is_valid_ping and not_pinged_yet and is_time_to_ping:
                user_watchlist = self.all_watchlists.get(user_id_str, [])
                if not user_watchlist: continue
                items_to_ping_for = [event['data']['材料名CN'] for event in upcoming_events if
                                     event['data']['材料名CN'] in user_watchlist]
                if items_to_ping_for:
                    try:
                        message = f"<@{user_id}>，你关注的 **{', '.join(items_to_ping_for)}** 即将在 **{ping_time}** 秒后刷新！"
                        await self.channel.send(message, delete_after=ping_time + 5)
                        self.pinged_users_this_spawn.add(user_id)
                    except Exception as e:
                        print(f"发送提醒失败: {e}")

    def _get_next_occurrence_timestamp(self, et_hour: int, current_unix_time: float) -> Optional[float]:
        if not (0 <= et_hour < 24): return None
        target_et_total_minutes = et_hour * 60
        eorzea_total_seconds = current_unix_time * EORZEA_MULTIPLIER
        current_et_total_minutes = (eorzea_total_seconds // 60) % (24 * 60)

        # 👇 核心修复 3：使用取模解决死循环问题
        minute_diff = (target_et_total_minutes - current_et_total_minutes) % 1440
        if minute_diff < 1:  # 如果算出来的时间就是现在，强制把它推到明天的这个点！
            minute_diff += 1440

        seconds_to_wait = minute_diff * (175 / 60)
        return current_unix_time + seconds_to_wait

    def _build_embed(self, upcoming_events, grouped_events, time_remaining):
        title_suffix = f"(由 {self.author.display_name} 启动)"
        if self.track_all:
            title_suffix = "(追踪全部)"
        elif self.user_watchlist:
            title_suffix = f"(追踪 {self.author.display_name} 的列表)"
        embed = discord.Embed(title=f"FF14 采集点追踪器 {title_suffix}",
                              description=f"现实时间(LT): **{datetime.datetime.now().strftime('%H:%M:%S')}**\n艾欧泽亚(ET): **{self._get_current_eorzea_time()}**",
                              color=discord.Color.green())
        if not upcoming_events:
            embed.description += "\n\n当前没有你关注的项目即将刷新。"
            embed.color = discord.Color.greyple()
            return embed
        event_time_info = upcoming_events[0]['data']
        embed.add_field(name=f"下一个刷新: ET {event_time_info.get('开始ET', '?')}:00",
                        value=f"**现实时间剩余: {self._format_time_delta(time_remaining)}**", inline=False)
        grouped_items = list(grouped_events.items())
        if len(grouped_items) > MAX_EMBED_FIELDS - 1:
            display_items = grouped_items[:MAX_EMBED_FIELDS - 2]
            omitted_count = len(grouped_items) - len(display_items)
            for (region, coords), materials in display_items:
                embed.add_field(name=f"📍 {region} ({coords})", value=f"**材料**: {', '.join(materials)}", inline=False)
            embed.add_field(name="...", value=f"⚠️ **以及另外 {omitted_count} 个地点未显示**", inline=False)
        else:
            for (region, coords), materials in grouped_items:
                embed.add_field(name=f"📍 {region} ({coords})", value=f"**材料**: {', '.join(materials)}", inline=False)
        embed.set_footer(text=f"使用 !stop 停止")
        if time_remaining <= MEDIUM_THRESHOLD_SECONDS: embed.color = discord.Color.orange()
        if time_remaining <= URGENT_THRESHOLD_SECONDS: embed.color = discord.Color.red()

        return embed

    def _get_current_eorzea_time(self) -> str:
        unix_now = time.time() + self.manual_offset
        eorzea_total_seconds = int(unix_now * EORZEA_MULTIPLIER)
        total_e_minutes = eorzea_total_seconds // 60
        minute_of_day = total_e_minutes % (24 * 60)
        hour = minute_of_day // 60
        minute = minute_of_day % 60
        return f"{hour:02d}:{minute:02d}"

    def _format_time_delta(self, seconds: float) -> str:
        seconds = max(0, seconds)
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes:02d} 分 {remaining_seconds:02d} 秒"


class TrackerManager:
    def __init__(self, bot, config):
        self.bot = bot
        self.csv_filename = config['CSV_FILENAME']
        self.watchlist_file = config['WATCHLIST_FILE']
        self.ping_file = config['PING_FILE']
        self.manual_offset = config['MANUAL_TIME_OFFSET_SECONDS']
        self.user_watchlists = {}
        self.user_pings = {}
        self.all_nodes_data = []
        self.active_trackers = {}
        self.all_item_names = []

    def load_data(self):
        if os.path.exists(self.watchlist_file):
            try:
                with open(self.watchlist_file, 'r', encoding='utf-8') as f:
                    self.user_watchlists = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self.user_watchlists = {}
        else:
            self.user_watchlists = {}
        print("用户关注列表已加载。")
        if os.path.exists(self.ping_file):
            try:
                with open(self.ping_file, 'r', encoding='utf-8') as f:
                    self.user_pings = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self.user_pings = {}
        else:
            self.user_pings = {}
        print("用户提醒设置已加载。")
        self.all_nodes_data = self._load_nodes_from_csv()
        if self.all_nodes_data:
            print(f"成功从 {self.csv_filename} 加载 {len(self.all_nodes_data)} 条数据。")
            item_names = set()
            for node in self.all_nodes_data:
                if '材料名CN' in node and node['材料名CN']:
                    item_names.add(node['材料名CN'])
            self.all_item_names = list(item_names)
            print(f"已加载 {len(self.all_item_names)} 个独一无二的材料名用于校验。")
        else:
            print(f"!!! 严重错误: 未能从 {self.csv_filename} 加载任何数据。!!!")

    def _safe_save_json(self, data, filename):
        temp_file = f"{filename}.tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(temp_file, filename)
        except Exception as e:
            print(f"!!!严重错误: 保存 {filename} 失败: {e}")
            if os.path.exists(temp_file): os.remove(temp_file)

    def add_to_watchlist(self, user_id, items_str):
        user_id_str = str(user_id)
        if user_id_str not in self.user_watchlists:
            self.user_watchlists[user_id_str] = []

        item_list = items_str.replace('，', ',').split(',')

        added = []
        already_exist = []
        not_found_in_csv = []

        user_current_list = self.user_watchlists[user_id_str]

        for item in item_list:
            clean_item = item.strip().strip('"').strip("'").strip()
            if not clean_item: continue

            if clean_item in user_current_list:
                already_exist.append(clean_item)
                continue

            if clean_item in self.all_item_names:
                user_current_list.append(clean_item)
                added.append(clean_item)
            else:
                not_found_in_csv.append(clean_item)

        if added:
            self._safe_save_json(self.user_watchlists, self.watchlist_file)

        response_parts = []
        if added:
            response_parts.append(f"✅ 已添加: **{', '.join(added)}**")
        if already_exist:
            response_parts.append(f"ℹ️ 已存在: **{', '.join(already_exist)}**")
        if not_found_in_csv:
            response_parts.append(f"❌ 物品不存在: **{', '.join(not_found_in_csv)}**")

        return "\n".join(response_parts) if response_parts else "请输入有效的材料名。"

    def _load_nodes_from_csv(self) -> List[Dict]:
        try:
            with open(self.csv_filename, mode='r', encoding='utf-8') as infile:
                return list(csv.DictReader(infile))
        except FileNotFoundError:
            return []

    def remove_from_watchlist(self, user_id, items_str):
        user_id_str = str(user_id)
        if user_id_str not in self.user_watchlists: return "❌ 你的关注列表是空的。"
        item_list = items_str.replace('，', ',').split(',')
        removed, not_found = [], []
        for item in item_list:
            clean_item = item.strip().strip('"').strip("'").strip()
            if not clean_item: continue
            if clean_item in self.user_watchlists[user_id_str]:
                self.user_watchlists[user_id_str].remove(clean_item)
                removed.append(clean_item)
            else:
                not_found.append(clean_item)
        if removed:
            if not self.user_watchlists[user_id_str]: del self.user_watchlists[user_id_str]
            self._safe_save_json(self.user_watchlists, self.watchlist_file)
        response = ""
        if removed: response += f"✅ 已移除: **{', '.join(removed)}**。\n"
        if not_found: response += f"❌ 找不到: **{', '.join(not_found)}**。"
        return response.strip()

    def get_watchlist(self, user_id):
        return self.user_watchlists.get(str(user_id), [])

    def clear_watchlist(self, user_id):
        uid_str = str(user_id)
        if uid_str in self.user_watchlists:
            del self.user_watchlists[uid_str]
            self._safe_save_json(self.user_watchlists, self.watchlist_file)

    def copy_watchlist(self, source_user_id, dest_user_id):
        source_id_str, dest_id_str = str(source_user_id), str(dest_user_id)
        source_list = self.get_watchlist(source_id_str)
        if not source_list: return "❌ 操作失败：目标用户没有设置关注列表，或列表为空。"
        if dest_id_str not in self.user_watchlists: self.user_watchlists[dest_id_str] = []
        dest_list = self.user_watchlists[dest_id_str]
        original_count = len(dest_list)
        merged_set = set(dest_list).union(set(source_list))
        self.user_watchlists[dest_id_str] = sorted(list(merged_set))
        items_added_count = len(self.user_watchlists[dest_id_str]) - original_count
        if items_added_count > 0:
            self._safe_save_json(self.user_watchlists, self.watchlist_file)
            return f"✅ 成功复制了 **{items_added_count}** 个新项目到你的关注列表。"
        else:
            return "ℹ️ 目标用户的关注项已全部在你的列表中，无需复制。"

    def set_ping_for_user(self, user_id, seconds):
        user_id_str = str(user_id)
        if seconds == -1 or str(seconds).lower() == 'off':
            if user_id_str in self.user_pings:
                del self.user_pings[user_id_str]
                self._safe_save_json(self.user_pings, self.ping_file)
                return "✅ 你的个人提醒功能已关闭。"
            return "ℹ️ 你尚未开启提醒功能。"
        self.user_pings[user_id_str] = seconds
        self._safe_save_json(self.user_pings, self.ping_file)
        return f"✅ 提醒设置成功！将在刷新前 **{seconds}** 秒 @ 你。"

    def get_ping_for_user(self, user_id):
        return self.user_pings.get(str(user_id), -1)

    async def start_tracker_for_channel(self, ctx, track_all=False):
        channel_id = ctx.channel.id
        if channel_id in self.active_trackers:
            await ctx.send("错误：这个频道已经有一个追踪器在运行了！");
            return
        if not self.all_nodes_data:
            await ctx.send("❌ 启动失败：机器人未能加载 `nodes.csv` 数据。");
            return
        user_watchlist = self.get_watchlist(ctx.author.id)
        instance = TrackerInstance(self.bot, ctx.author, ctx.channel, self.all_nodes_data, self.manual_offset,
                                   user_watchlist, track_all, self.user_pings, self.user_watchlists)
        if await instance.start():
            self.active_trackers[channel_id] = instance
            mode_text = "（追踪全部）" if track_all else f"（根据 **{ctx.author.display_name}** 的列表）"
            await ctx.send(f"✅ 追踪器已启动！{mode_text}", delete_after=10)

    async def stop_tracker_for_channel(self, ctx):
        channel_id = ctx.channel.id
        if channel_id in self.active_trackers:
            instance = self.active_trackers[channel_id]
            await instance.stop()
            del self.active_trackers[channel_id]
            await ctx.send("🛑 采集点追踪器已在此频道停止。")
        else:
            await ctx.send("错误：这个频道没有正在运行的追踪器。")

    # 👇 补充了刚才你代码里缺失的这个方法的定义，防止 !showcurrent 报错
    async def show_current_tracker_for_channel(self, ctx):
        if ctx.channel.id in self.active_trackers:
            await ctx.send("✅ 追踪器正在当前频道运行。使用 `!stop` 停止。")
        else:
            await ctx.send("ℹ️ 当前频道没有运行中的追踪器。")


# --- Cog 主体 ---
class TrackerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker_manager = TrackerManager(bot, bot.config)

    @commands.Cog.listener()
    async def on_ready(self):
        self.tracker_manager.load_data()

    @commands.command(name='start', aliases=['start_tracker'])
    async def start_command(self, ctx, mode: str = None):
        track_all = mode and mode.lower() == 'all'
        await self.tracker_manager.start_tracker_for_channel(ctx, track_all=track_all)

    @commands.command(name='stop', aliases=['stop_tracker'])
    async def stop_command(self, ctx):
        await self.tracker_manager.stop_tracker_for_channel(ctx)

    @commands.command(name='add')
    async def add_command(self, ctx, *, items_str: str):
        if not items_str: await ctx.send("请输入要添加的材料名！例如: `!add 火晶簇, 雷晶簇`"); return
        await ctx.send(self.tracker_manager.add_to_watchlist(ctx.author.id, items_str))

    @commands.command(name='remove')
    async def remove_command(self, ctx, *, items_str: str):
        if not items_str: await ctx.send("请输入要移除的材料名！例如: `!remove 火晶簇, 雷晶簇`"); return
        await ctx.send(self.tracker_manager.remove_from_watchlist(ctx.author.id, items_str))

    @commands.command(name='list', aliases=['watchlist'])
    async def list_command(self, ctx):
        watchlist = self.tracker_manager.get_watchlist(ctx.author.id)
        if not watchlist: await ctx.send("你的关注列表是空的。"); return
        embed = discord.Embed(title=f"{ctx.author.display_name} 的关注列表",
                              description="\n".join(f"- {item}" for item in watchlist), color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name='clear')
    async def clear_command(self, ctx):
        self.tracker_manager.clear_watchlist(ctx.author.id)
        await ctx.send("✅ 你的关注列表已清空。")

    @commands.command(name='copy')
    async def copy_command(self, ctx, source_user: discord.Member):
        if ctx.author.id == source_user.id: await ctx.send("🤔 您不能复制自己的列表。"); return
        result_message = self.tracker_manager.copy_watchlist(source_user_id=source_user.id, dest_user_id=ctx.author.id)
        await ctx.send(f"正在从 **{source_user.display_name}** 复制...\n{result_message}")

    @commands.command(name='ping')
    async def ping_command(self, ctx, seconds: Optional[str] = None):
        if seconds is None:
            current_ping = self.tracker_manager.get_ping_for_user(ctx.author.id)
            if current_ping != -1:
                await ctx.send(f"ℹ️ 你当前的提醒时间设置为 **{current_ping}** 秒。")
            else:
                await ctx.send("ℹ️ 你尚未设置提醒时间。使用 `!ping [秒数]` 来设置。")
            return
        try:
            if seconds.lower() != 'off':
                sec_val = int(seconds)
                if sec_val <= 0 and sec_val != -1:
                    await ctx.send("❌ 请输入一个大于0的秒数，或输入 `-1`/`off` 来关闭提醒。");
                    return
            else:
                sec_val = -1
            result_message = self.tracker_manager.set_ping_for_user(ctx.author.id, sec_val)
            await ctx.send(result_message)
        except ValueError:
            await ctx.send("❌ 无效的输入。请输入一个数字（秒数），例如 `!ping 60`。")

    @commands.command(name='showcurrent')
    async def showcurrent_command(self, ctx):
        await self.tracker_manager.show_current_tracker_for_channel(ctx)


async def setup(bot):
    await bot.add_cog(TrackerCog(bot))