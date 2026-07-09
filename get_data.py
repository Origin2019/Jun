import json
import re
import os
import requests
import pdfplumber
import time
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 禁用 SSL 警告，保持控制台整洁
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

all_protocols = {}
PDF_CACHE_DIR = "pdf_cache"
os.makedirs(PDF_CACHE_DIR, exist_ok=True)

# 💡 建立带智能重试机制的会话，专治 ISU 服务器的强制断连 (HTTPSConnectionPool)
session = requests.Session()
retry = Retry(connect=5, backoff_factor=1)  # 失败后自动重试 5 次，每次间隔逐渐拉长
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)


def clean_text(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def download_pdf(url, filename):
    filepath = os.path.join(PDF_CACHE_DIR, filename)
    if os.path.exists(filepath):
        return filepath  # 已经下载过的直接用缓存

    print(f"正在下载 PDF: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf',
            'Referer': 'https://www.isu.org/',
            'Connection': 'keep-alive'
        }
        # 使用配置了重试机制的 session 进行请求
        response = session.get(url, headers=headers, timeout=20, verify=False)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath
    except Exception as e:
        print(f"❌ 下载失败 {url}: {e}")
        return None


def parse_isu_pdf(pdf_path, event_id, event_name):
    print(f"正在解析: {event_name} ({pdf_path})...")
    skater_data = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            for i, line in enumerate(lines):
                # 💡 精准定位只提取车俊焕 (Junhwan CHA)
                if ("JUNHWAN" in line.upper() or "JUN HWAN" in line.upper()) and "CHA" in line.upper() and "KOR" in line.upper():
                    tokens = line.split()
                    try:
                        idx = tokens.index("KOR")
                    except ValueError:
                        continue

                    if idx >= 2 and len(tokens) >= idx + 5:
                        rank = ""
                        if idx - 3 >= 0 and tokens[idx - 3].isdigit():
                            rank = tokens[idx - 3]
                        elif idx - 4 >= 0 and tokens[idx - 4].isdigit():
                            rank = tokens[idx - 4]

                        starting_num = tokens[idx + 1]
                        total_score = tokens[idx + 2]
                        tes = tokens[idx + 3]
                        pcs = tokens[idx + 4]
                        deductions = tokens[idx + 5] if (idx + 5 < len(tokens)) else "0.00"

                        skater_data = {
                            "event_name": event_name,
                            "rank": rank,
                            "name": "Junhwan CHA",
                            "nation": "KOR",
                            "starting_number": starting_num,
                            "total_segment_score": total_score,
                            "total_element_score": tes,
                            "total_component_score": pcs,
                            "total_deductions": deductions,
                            "elements": [],
                            "components": [],
                            "deductions_detail": "",
                        }

                        # 向下流式解析他这一段的具体动作分
                        extract_text_details(lines[i + 1:], skater_data)
                        all_protocols[event_id] = skater_data
                        print(f" -> 🎉 成功提取 {event_name} 中 Junhwan CHA 的完整数据！")
                        return

    if not skater_data:
        print(f" ⚠️ 在 {pdf_path} 中未找到 Junhwan CHA 的数据！")


def extract_text_details(lines, skater_data):
    mode = "search"

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue

        tokens = line_strip.split()

        # 遇到下一个选手的国家代码（非韩国）说明车俊焕的表格结束了
        if len(tokens) >= 6 and any(re.match(r"^[A-Z]{3}$", t) for t in tokens) and "CHA" not in line.upper():
            if any(re.match(r"^\d+\.\d+$", t) for t in tokens[-4:]):
                break

        if "JUDGES DETAILS PER SKATER" in line_strip or "printed:" in line_strip:
            continue

        if "Executed Elements" in line or "Base Value" in line:
            mode = "elements"
            continue
        elif "Program Components" in line or "Composition" in line or "Presentation" in line:
            mode = "components"
        elif "Deductions" in line:
            mode = "deductions"

        if mode == "elements":
            if tokens and tokens[0].isdigit():
                no = tokens[0]

                float_idx = -1
                for idx in range(1, len(tokens)):
                    # 容错匹配 Base Value（兼容紧贴着小数的 x）
                    if re.match(r"^-?\d+\.\d+[xX]?$", tokens[idx]):
                        float_idx = idx
                        break

                if float_idx != -1 and len(tokens) > float_idx:
                    name_parts = tokens[1:float_idx]

                    # 💡 修复 1：动作名称读到第一个空格就停，其余一律塞进 Info 里面
                    name = name_parts[0] if name_parts else ""
                    info = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

                    base_value = tokens[float_idx]
                    has_x = False

                    # 清理紧贴数字的 x, 并做标记
                    if base_value.lower().endswith('x'):
                        base_value = base_value[:-1]
                        has_x = True

                    # 💡 修复 2：动态偏移量，跳过作为独立字符串出现的 'x' 干扰
                    offset = 1
                    if float_idx + offset < len(tokens) and tokens[float_idx + offset].lower() == 'x':
                        offset += 1
                        has_x = True

                    if float_idx + offset < len(tokens):
                        goe = tokens[float_idx + offset]

                        # 极端情况下 x 也会在 GOE 后面，继续跳过
                        if float_idx + offset + 1 < len(tokens) and tokens[float_idx + offset + 1].lower() == 'x':
                            offset += 1
                            has_x = True

                        panel_score = tokens[-1]
                        judges = tokens[float_idx + offset + 1: -1]

                        skater_data["elements"].append({
                            "no": no,
                            "name": name,
                            "info": info,
                            "base_value": base_value,
                            "has_x": has_x,
                            "goe": goe,
                            "judges": judges,
                            "ref": "",
                            "panel_score": panel_score,
                        })

        elif mode == "components":
            comp_names = ["Composition", "Presentation", "Skating Skills", "Transitions", "Performance",
                          "Interpretation"]
            if any(cn.lower() in line_strip.lower() for cn in comp_names):
                comp_name = next(cn for cn in comp_names if cn.lower() in line_strip.lower())
                nums = [t for t in tokens if re.match(r"^-?\d+(\.\d+)?$", t)]
                if len(nums) >= 2:
                    factor = nums[0]
                    panel_score = nums[-1]
                    judges = nums[1:-1]
                    skater_data["components"].append({
                        "name": comp_name,
                        "factor": factor,
                        "judges": judges,
                        "ref": "",
                        "panel_score": panel_score,
                    })

        elif mode == "deductions":
            # 💡 修复：用正则强行抹除 "(Page X / Y)" 和 "(Score Score...)" 这类页脚/表头干扰
            clean_line = re.sub(r'\s*\([Pp]age.*?\)', '', line_strip)
            clean_line = re.sub(r'\s*\(Score.*?\)', '', clean_line)

            if "Deductions:" in clean_line:
                detail = clean_line.split("Deductions:")[-1].strip()
            elif len(tokens) > 1 and "0.00" not in clean_line:
                detail = clean_line.strip()


def process_all_competitions():
    try:
        with open("data/competitions.json", "r", encoding="utf-8") as f:
            competitions_data = json.load(f)
    except FileNotFoundError:
        print("未找到 competitions.json 文件！请确保它与脚本在同一目录下。")
        return

    for season_data in competitions_data:
        season_name = season_data.get("season", "")
        year_match = re.search(r"\d{4}", season_name)
        year_str = year_match.group(0) if year_match else "unknown"

        for event in season_data.get("events", []):
            event_name = event.get("name", "")
            segments = event.get("segments", {})

            for seg_key, seg_data in segments.items():
                protocol_url = seg_data.get("protocol_url")

                if not protocol_url or not protocol_url.lower().endswith(".pdf"):
                    continue

                url_parts = protocol_url.split('/')
                folder_name = url_parts[-2] if len(url_parts) >= 2 else "unknown"
                clean_folder = re.sub(r'[^a-zA-Z0-9]', '', folder_name).lower()

                protocol_id = f"{year_str}_{clean_folder}_{seg_key.lower()}"
                seg_data["protocol_id"] = protocol_id

                pdf_filename = f"{protocol_id}.pdf"
                local_pdf_path = download_pdf(protocol_url, pdf_filename)

                if local_pdf_path:
                    full_event_name = f"{season_name} {event_name} - {seg_key}"
                    try:
                        parse_isu_pdf(local_pdf_path, protocol_id, full_event_name)
                    except Exception as e:
                        print(f"❌ 解析出错 [{protocol_id}]: {e}")

                    # 即使有了重试机制，稍微慢一点也能防爬虫拦截
                    time.sleep(1.0)

    with open("data/detailed_scores.json", "w", encoding="utf-8") as f:
        json.dump(all_protocols, f, ensure_ascii=False, indent=4)
    print("\n✅ detailed_scores.json 导出成功！")

    with open("data/competitions.json", "w", encoding="utf-8") as f:
        json.dump(competitions_data, f, ensure_ascii=False, indent=4)
    print("✅ competitions.json 更新 protocol_id 成功！")


if __name__ == "__main__":
    print("🚀 开始批量抓取并解析小分表数据...")
    process_all_competitions()
    print("🎉 全部任务执行完毕！")