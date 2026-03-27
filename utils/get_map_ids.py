import csv
import json
import urllib.request
import os


def update_map_ids(csv_filename='nodes.csv', json_filename='map_id.json'):
    print(f"1. 正在读取 {csv_filename}，提取所有的地图名称...")
    unique_regions = set()

    if not os.path.exists(csv_filename):
        print(f"❌ 找不到文件 {csv_filename}，请确保脚本和 CSV 在同一目录。")
        return

    try:
        with open(csv_filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                region = row.get('地区CN')
                if region:
                    unique_regions.add(region.strip())
    except Exception as e:
        print(f"❌ 读取 CSV 发生错误: {e}")
        return

    print(f"-> 成功提取 {len(unique_regions)} 个独一无二的地图名称。")

    print("\n2. 正在向 Cafemaker API 请求游戏底层地图数据 (这可能需要十几秒)...")
    # 注意：我们额外请求了 PlaceNameSub 和 TerritoryIntendedUse 用于智能过滤
    url = "https://cafemaker.wakingsands.com/Map?limit=3000&columns=ID,PlaceName.Name,PlaceNameSub.Name,TerritoryType.TerritoryIntendedUse"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            map_data = data.get('Results', [])
    except Exception as e:
        print(f"❌ API 请求失败: {e}")
        return

    print(f"-> 成功获取 {len(map_data)} 条地图底层数据，正在进行智能匹配...")

    # 建立 地区名 -> 最佳Map ID 的映射字典
    best_maps = {}

    for m in map_data:
        place = m.get('PlaceName')
        if not place: continue

        name = place.get('Name')
        if not name: continue

        map_id = m.get('ID')

        # 提取辅助信息用于评分
        sub_name = m.get('PlaceNameSub')
        sub_name_str = sub_name.get('Name') if sub_name else ""

        ttype = m.get('TerritoryType')
        intended_use = ttype.get('TerritoryIntendedUse') if ttype else 0

        # --- 核心：智能评分系统 ---
        score = 0
        if intended_use in [1, 8]:  # 1是主城, 8是野外
            score += 100
        if not sub_name_str:  # 没有子区域名（说明是主地图）
            score += 50

        # 优胜劣汰逻辑
        if name not in best_maps:
            best_maps[name] = {'id': map_id, 'score': score}
        else:
            current_best = best_maps[name]
            # 如果分数更高，或者分数相同但 ID 更小，则替换为最佳候选
            if score > current_best['score'] or (score == current_best['score'] and map_id < current_best['id']):
                best_maps[name] = {'id': map_id, 'score': score}

    print("\n3. 正在生成并覆写本地的 map_id.json...")

    final_dict = {}
    for region in sorted(unique_regions):
        match = best_maps.get(region)
        if match:
            final_dict[region] = match['id']
        else:
            final_dict[region] = None
            print(f"⚠️ 警告: 未在 API 中找到地图 [{region}]")

    # 直接将结果写入或覆写到 map_id.json 文件中
    try:
        # 获取当前脚本所在目录，确保输出位置正确
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(script_dir, json_filename)

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(final_dict, f, ensure_ascii=False, indent=4)
        print(f"✅ 更新成功！已自动将 {len(final_dict)} 个最精确的地图 ID 保存至 {json_filename}")
        print("💡 以后每次更新 nodes.csv 后，只需运行一次本脚本，重启机器人即可生效！")
    except Exception as e:
        print(f"❌ 保存 JSON 文件失败: {e}")


if __name__ == "__main__":
    update_map_ids()