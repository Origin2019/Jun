import pdfplumber
import json

# 准备一个空的字典来存放最终数据
all_protocols = {}


def parse_isu_pdf(pdf_path, event_id, event_name):
    # 使用 pdfplumber 打开 PDF
    with pdfplumber.open(pdf_path) as pdf:
        # ISU 小分表通常在第一页或第二页，找到你的选手所在的区域
        page = pdf.pages[0]

        # pdfplumber 可以很精准地提取表格 (extract_tables)
        tables = page.extract_tables()

        # --- 这里需要你根据 ISU 的表格规律写具体的提取逻辑 ---
        # 比如遍历表格，找到 'Elements' 这一行，然后提取下面的 4A, 3A 数据
        # 提取完后，组装成字典:
        event_data = {
            "event_name": event_name,
            "total_score": "92.72",  # 提取的数值
            "elements": [
                # 提取的动作列表...
            ]
        }
        all_protocols[event_id] = event_data


# 处理你的本地 PDF 文件
parse_isu_pdf("owg2026_sp.pdf", "2026_owg_sp", "2026 米兰冬奥会 短节目")
parse_isu_pdf("owg2026_fs.pdf", "2026_owg_fs", "2026 米兰冬奥会 自由滑")

# 最后，将数据导出为你前端需要的 JSON 文件
with open("detailed_scores.json", "w", encoding="utf-8") as f:
    json.dump(all_protocols, f, ensure_ascii=False, indent=4)

print("JSON 数据生成完毕！可以扔给前端用了。")