#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
import csv
import time
import datetime
import os
from typing import List, Dict, Optional
from collections import defaultdict
import asyncio

# --- 全局配置与状态变量 ---
# !!! 在这里填入你的机器人TOKEN !!!
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
COMMAND_PREFIX = "!"
CSV_FILENAME = 'nodes.csv'

# --- 常量定义 ---
# 手动时间校准（秒）。如果你的脚本比游戏慢2秒，就设置为2.0
MANUAL_TIME_OFFSET_SECONDS = 0.0
# 刷新逻辑
NORMAL_REFRESH_INTERVAL = 60
MEDIUM_THRESHOLD_SECONDS = 30
MEDIUM_REFRESH_INTERVAL = 5
URGENT_THRESHOLD_SECONDS = 10
URGENT_REFRESH_INTERVAL = 1
# 艾欧泽亚时间计算
EORZEA_MULTIPLIER = 3600 / 175
LOOP_INTERVAL = 1.0  # 内部高精度循环检测间隔

# --- Bot 设置 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)


# --- 机器人状态管理 ---
class TrackerState:
    """用于存储追踪器运行状态的类"""

    def __init__(self):
        self.background_task = None
        self.target_channel = None
        self.tracker_message = None
        self.monitored_nodes = []


state = TrackerState()


# --- 辅助与时间换算函数 ---
# (这些函数与之前的脚本完全相同)
def format_time_delta(seconds: float) -> str:
    seconds = max(0, seconds)
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    return f"{minutes:02d} 分 {remaining_seconds:02d} 秒"


def get_current_eorzea_time(offset: float) -> str:
    unix_now = time.time() + offset
    eorzea_total_seconds = int(unix_now * EORZEA_MULTIPLIER)
    total_eorzea_minutes = eorzea_total_seconds // 60
    minute_of_day = total_eorzea_minutes % (24 * 60)
    hour = minute_of_day // 60
    minute = minute_of_day % 60
    return f"{hour:02d}:{minute:02d}"


def get_next_occurrence_timestamp(et_hour: int, current_unix_time: float) -> Optional[float]:
    if not (0 <= et_hour < 24): return None
    target_et_total_minutes = et_hour * 60
    eorzea_total_seconds = current_unix_time * EORZEA_MULTIPLIER
    current_et_total_minutes = (eorzea_total_seconds // 60) % (24 * 60)
    minute_diff = target_et_total_minutes - current_et_total_minutes
    if minute_diff < 0: minute_diff += 24 * 60
    seconds_to_wait = minute_diff * (175 / 60)
    return current_unix_time + seconds_to_wait


def load_nodes_from_csv(filename: str) -> List[Dict]:
    try:
        with open(filename, mode='r', encoding='utf-8') as infile:
            return list(csv.DictReader(infile))
    except FileNotFoundError:
        return []


# --- 核心后台任务 ---
async def tracker_loop():
    """在后台运行的核心追踪循环"""
    await bot.wait_until_ready()
    last_update_time = 0

    while not bot.is_closed():
        loop_start_time = time.time()
        now = loop_start_time + MANUAL_TIME_OFFSET_SECONDS

        # 1. 更新节点时间
        for node in state.monitored_nodes:
            if now >= node['next_ts']:
                node['next_ts'] = get_next_occurrence_timestamp(node['et_hour'], now)

        if not state.monitored_nodes:
            await asyncio.sleep(1)
            continue

        soonest_ts = min(node['next_ts'] for node in state.monitored_nodes)
        time_remaining = soonest_ts - now

        # 2. 决定是否需要刷新Discord消息
        should_update_display = False
        if time_remaining <= URGENT_THRESHOLD_SECONDS:
            should_update_display = True
        elif time_remaining <= MEDIUM_THRESHOLD_SECONDS:
            if (now - last_update_time) >= MEDIUM_REFRESH_INTERVAL:
                should_update_display = True
        elif (now - last_update_time) >= NORMAL_REFRESH_INTERVAL:
            should_update_display = True

        if should_update_display:
            last_update_time = now

            upcoming_events = [node for node in state.monitored_nodes if node['next_ts'] == soonest_ts]
            grouped_events = defaultdict(list)
            for event in upcoming_events:
                node_data = event['data']
                location_key = (node_data.get('地区CN', 'N/A'), node_data.get('具体坐标', 'N/A'))
                grouped_events[location_key].append(node_data.get('材料名CN', 'N/A'))

            # 3. 创建或更新Discord消息
            embed = discord.Embed(
                title="FF14 采集点追踪器",
                description=f"现实时间(LT): **{datetime.datetime.now().strftime('%H:%M:%S')}**\n艾欧泽亚(ET): **{get_current_eorzea_time(MANUAL_TIME_OFFSET_SECONDS)}**",
                color=discord.Color.green()
            )
            event_time_info = upcoming_events[0]['data']
            embed.add_field(
                name=f"下一个刷新: ET {event_time_info.get('开始ET', '?')}:00",
                value=f"**现实时间剩余: {format_time_delta(time_remaining)}**",
                inline=False
            )
            for (region, coords), materials in grouped_events.items():
                embed.add_field(name=f"📍 {region} ({coords})", value=f"**材料**: {', '.join(materials)}", inline=False)

            embed.set_footer(text=f"使用 {COMMAND_PREFIX}stop 停止 | 下次刷新约在 {int(NORMAL_REFRESH_INTERVAL)} 秒后")
            if time_remaining <= MEDIUM_THRESHOLD_SECONDS:
                embed.color = discord.Color.orange()
            if time_remaining <= URGENT_THRESHOLD_SECONDS:
                embed.color = discord.Color.red()

            try:
                if state.tracker_message is None:
                    state.tracker_message = await state.target_channel.send(embed=embed)
                else:
                    await state.tracker_message.edit(embed=embed)
            except (discord.errors.NotFound, discord.errors.HTTPException):
                # 消息被删除或出现网络问题，尝试重新发送
                state.tracker_message = await state.target_channel.send(embed=embed)

        # 4. 自校准休眠
        processing_time = time.time() - loop_start_time
        sleep_duration = LOOP_INTERVAL - processing_time
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)


# --- Discord Bot 命令 ---
@bot.event
async def on_ready():
    print(f'机器人已登录: {bot.user.name}')


@bot.command(name='start', aliases=['start_tracker'])
async def start_command(ctx):
    """在当前频道启动采集点追踪器。"""
    if state.background_task and not state.background_task.done():
        await ctx.send("追踪器已经在运行了！")
        return

    state.target_channel = ctx.channel
    state.tracker_message = None

    all_nodes = load_nodes_from_csv(CSV_FILENAME)
    if not all_nodes:
        await ctx.send(f"错误: 找不到或无法读取 `{CSV_FILENAME}`。请确保它和机器人在同一目录。")
        return

    initial_time = time.time() + MANUAL_TIME_OFFSET_SECONDS
    state.monitored_nodes = []
    for node_data in all_nodes:
        start_et_str = node_data.get('开始ET')
        if start_et_str and start_et_str.strip().isdigit():
            et_hour = int(start_et_str.strip())
            next_ts = get_next_occurrence_timestamp(et_hour, initial_time)
            if next_ts:
                state.monitored_nodes.append({'data': node_data, 'next_ts': next_ts, 'et_hour': et_hour})

    if not state.monitored_nodes:
        await ctx.send("CSV文件中没有有效的采集点数据。")
        return

    state.background_task = bot.loop.create_task(tracker_loop())
    await ctx.send(f"✅ 采集点追踪器已在 `#{ctx.channel.name}` 频道启动！")


@bot.command(name='stop', aliases=['stop_tracker'])
async def stop_command(ctx):
    """停止追踪器。"""
    if not (state.background_task and not state.background_task.done()):
        await ctx.send("追踪器当前未在运行。")
        return

    state.background_task.cancel()
    if state.tracker_message:
        try:
            await state.tracker_message.delete()
        except discord.errors.NotFound:
            pass

    state.tracker_message = None
    state.target_channel = None
    await ctx.send("🛑 采集点追踪器已停止。")


# --- 运行机器人 ---
if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("错误：请先在脚本第11行填入你的机器人TOKEN！")
    else:
        bot.run(BOT_TOKEN)