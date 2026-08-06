import os
import json
import re
import io
import base64
import time
from datetime import datetime
import streamlit as st
from fpdf import FPDF
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# ==================== 1. 页面配置 ====================
st.set_page_config(
    page_title="KUKA 赛博软装与睡眠主理人",
    page_icon="🛋️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 侧边栏密码认证
if "sidebar_unlocked" not in st.session_state:
    st.session_state.sidebar_unlocked = False
SIDEBAR_PASSWORD = "920736"

# 方案微调：初始化当前报告存储
if "current_report" not in st.session_state:
    st.session_state.current_report = ""
if "report_history" not in st.session_state:
    st.session_state.report_history = []

# PDF报价单：存储客户表单数据
if "quote_form_data" not in st.session_state:
    st.session_state.quote_form_data = {}

# 防重复点击锁：标记查询是否正在执行中
if "query_in_progress" not in st.session_state:
    st.session_state.query_in_progress = False
if "guide_query_in_progress" not in st.session_state:
    st.session_state.guide_query_in_progress = False
if "trigger_guide_query" not in st.session_state:
    st.session_state.trigger_guide_query = False
if "refine_in_progress" not in st.session_state:
    st.session_state.refine_in_progress = False

# ==================== 2. 路径 ====================
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except Exception:
    BASE_DIR = os.getcwd()
MD_DB_DIR = os.path.join(BASE_DIR, "markdown_db")
if not os.path.exists(MD_DB_DIR):
    MD_DB_DIR = os.path.join(os.getcwd(), "markdown_db")
JSON_INDEX_PATH = os.path.join(MD_DB_DIR, "product_images.json")
QUERY_LOG_PATH = os.path.join(BASE_DIR, "query_log.jsonl")

CATEGORY_MAP = {"沙发": "沙发", "床": "床架", "床垫": "床垫", "配套": "配套"}

# 颜色色调分类规则（用于产品配色匹配墙面/地面颜色）
# 优先匹配长关键词，再匹配短关键词
_COLOR_TONE_RULES = [
    # 深色系
    (["曜石黑", "骑士黑", "星爵黑", "醇巧黑", "伯爵黑", "格调黑", "黑骑士", "黑武士",
      "深烟灰", "耀夜灰", "火山灰", "墨灰色", "松烟褐", "暮山褐", "烟墨棕", "暗夜棕",
      "暗驼棕", "深咖色", "午夜咖啡", "深棕色", "暗林绿", "松间绿", "暮夜紫", "高贵紫",
      "复古红", "浆果红棕", "红松鼠", "秋柿橘", "琥珀橙", "落日橙", "晴空蓝", "岛屿蓝",
      "曜钻蓝", "桃木褐棕", "岩岩褐", "深灰色", "星际黑", "松木棕", "琉璃棕", "栗壳棕",
      "栗子棕", "栗壳色", "榛果褐", "核桃", "胡桃", "可可棕", "布朗棕", "丹麦棕",
      "赫钻棕", "奶棕色", "暗夜", "耀夜", "暮山", "浆果", "烟霞栗", "暖栗色",
      "星云灰", "银河灰", "鹰翼灰", "雾色灰", "月光灰", "轻影灰", "霜禾灰",
      "深棕"], "深色系"),
    # 浅色系
    (["云石白", "云影白", "云月白", "月光白", "雪花石", "菊蕊白", "霜绒白", "流沙白",
      "柔空白", "沙滩白", "大麦白", "乳酪白", "梨花白", "栀子白", "奶钻白", "萄苔白",
      "韶粉白", "浅云白", "玉石色", "奶油白", "可可蛋奶", "鲜奶油", "燕麦拿铁",
      "朗姆奶咖", "米白色", "晨青云", "海豚灰", "象牙灰", "轻影灰", "霜禾灰",
      "蜜杏灰", "浅杏灰", "暖米灰", "雨雾灰", "杏灰色", "雾咖色", "沙丘色",
      "古巴砂色", "燕麦色", "暖山玉", "初蕊粉", "梦幻粉", "奶酪薄荷绿",
      "玛奇朵色", "宁和蓝", "岛屿蓝", "晴空蓝", "暖栗色", "大麦",
      "霜绒", "米色", "米白", "奶白", "奶油", "奶咖", "浅杏", "浅灰", "浅云",
      "流沙", "柔白", "云白", "雪花", "菊蕊", "象牙", "海豚", "晨青",
      "乳酪", "燕麦", "朗姆", "蜜杏", "沙丘", "沙滩", "鲜奶油",
      "雪花", "古巴", "纯白", "纯白"], "浅色系"),
]


def _classify_color_tone(color_names):
    """根据颜色名称列表判断整体色调，返回 '浅色系' 或 '深色系'（默认深色系）"""
    tones = _classify_color_tones(color_names)
    return tones[0] if tones else "深色系"


def _classify_color_tones(color_names):
    """返回产品可选的全部色调集合（浅色系/深色系可同时存在）。

    多色床架（同时有浅色与深色配色可选）会被归入多个色调，
    这样搜索"浅色的床"或"深色的床"都能命中它们。
    """
    if not color_names:
        return ["深色系"]
    text = " ".join(color_names)
    tones = []
    shallow_kws, _ = _COLOR_TONE_RULES[1]
    if any(kw in text for kw in shallow_kws):
        tones.append("浅色系")
    deep_kws, _ = _COLOR_TONE_RULES[0]
    if any(kw in text for kw in deep_kws):
        tones.append("深色系")
    if not tones:
        # 不含规则关键词，根据常见色名判断
        if "白" in text or "米" in text or "奶" in text:
            tones.append("浅色系")
        elif "黑" in text or "灰" in text or "棕" in text or "褐" in text or "咖" in text or "深" in text:
            tones.append("深色系")
        else:
            tones.append("深色系")
    return tones


# ==================== 3. 数据收集 ====================
def _log_query(event_type, data):
    """记录用户查询/操作到 query_log.jsonl 文件，用于后续高频问题分析"""
    import datetime
    record = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event_type": event_type,
        "data": data,
    }
    try:
        with open(QUERY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志写入失败不影响主流程


def _get_log_count():
    """返回 query_log.jsonl 的记录条数"""
    try:
        if os.path.exists(QUERY_LOG_PATH):
            with open(QUERY_LOG_PATH, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
    except Exception:
        pass
    return 0


# ==================== 4. 产品索引构建（解析 MD → 结构化数据）====================
def _extract_price_rows(text, category, max_rows=8):
    """提取MD文件中规格-价格行，返回 (display_rows, all_prices)
    display_rows: 格式化的显示行（沙发只保留组合规格）
    all_prices: 所有规格的真实价格列表（用于价格区间计算）
    
    按优先级依次尝试多种表格区域：
    1. ### 规格尺寸（沙发格式）
    2. ## 床架（床架格式，含所有 ### 配色型号: 下的表格）
    3. ## 床垫（床垫格式）
    4. ## 配套（配套格式）"""
    # 按品类优先级排列要尝试的章节模式
    section_patterns = [
        r'### 规格尺寸\s*\n(.*?)(?=\n###\s|\n##\s|\Z)',  # 沙发
        r'## 床架\s*\n(.*?)(?=\n##\s|\Z)',                # 床架
        r'## 床垫\s*\n(.*?)(?=\n##\s|\Z)',                # 床垫
        r'## 配套\s*\n(.*?)(?=\n##\s|\Z)',                # 配套
    ]
    
    for pattern in section_patterns:
        spec_match = re.search(pattern, text, re.DOTALL)
        if not spec_match:
            continue
        section_text = spec_match.group(1)
        
        display_rows = []
        all_prices = []
        for line in section_text.split('\n'):
            stripped = line.strip()
            if not stripped.startswith('|') or '---' in stripped or '|--' in stripped:
                continue
            parts = [p.strip() for p in stripped.split('|') if p.strip()]
            if len(parts) < 3:
                continue
            # 跳过表头行
            header_chars = ''.join(parts)
            if re.search(r'规格|尺寸|型号|成交价|色号|组件|项目', header_chars[:15]):
                continue
            # 从右往左找价格列：优先找含 ¥/￥/元 的列
            price_col = None
            for i in range(len(parts) - 1, -1, -1):
                cell = parts[i]
                if re.search(r'[¥￥]', cell) or re.search(r'元', cell):
                    if re.search(r'\d{3,}', cell):
                        price_col = i
                        break
            if price_col is None:
                # 无符号标记时，从右往左找纯数字列（不含字母/×/x/cm等）
                for i in range(len(parts) - 1, -1, -1):
                    cell = parts[i]
                    if re.search(r'[a-zA-Z×xXcm/\\\\]', cell):
                        continue
                    if re.search(r'\d{3,}', cell) and i >= 1:
                        # 确保前一列（尺寸列）包含字母或×则是组合规格行，不属于常规价格行
                        prev = parts[i - 1] if i >= 1 else ""
                        if re.search(r'[×xX]', prev):
                            continue  # 前一列是尺寸（含×），本列为长度而非价格
                        price_col = i
                        break
            if price_col is None:
                continue
            spec_name = parts[0]
            size_col = parts[1] if len(parts) >= 2 else ""
            raw_price = parts[price_col]
            price_clean = raw_price.replace('¥', '').replace('￥', '').replace('元', '').replace(',', '').strip()
            if re.match(r'^\d{3,}$', price_clean):
                price_val = int(price_clean)
                # 兜底：价格低于 500 的极可能是尺寸误识别，跳过
                if price_val < 500:
                    continue
                if price_val not in all_prices:  # 去重（同价不同配色）
                    all_prices.append(price_val)
                formatted = f"{spec_name} → {size_col}, ¥{price_val:,}"
                # 沙发只保留组合规格（含 + 号），床/床垫/配套保留所有规格
                if category != "沙发" or '+' in spec_name:
                    if formatted not in display_rows:  # 去重
                        display_rows.append(formatted)
                        if len(display_rows) >= max_rows:
                            break
        if display_rows:
            return display_rows, all_prices
    
    return [], []


def _parse_md_product(filepath, rel_path):
    """解析单个 md 文件，返回结构化产品字典"""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    folder = rel_path.split(os.path.sep)[0]
    category = CATEGORY_MAP.get(folder, folder)
    model = os.path.splitext(os.path.basename(filepath))[0]

    # 产品名称
    name_match = re.search(r'\*\*产品名称\*\*\s*:\s*(.+)', text)
    name = name_match.group(1).strip() if name_match else model

    # 产品线/系列（优先从文档读取，其次按型号前缀映射）
    series_match = re.search(r'\*\*产品线\*\*\s*:\s*(.+)', text)
    series = series_match.group(1).strip() if series_match else ""
    if not series:
        # 床垫等产品可能用"产品系列"字段
        series_match2 = re.search(r'\*\*产品系列\*\*\s*:\s*(.+)', text)
        series = series_match2.group(1).strip() if series_match2 else ""
    if not series:
        # 产品系列前缀映射表（床和床垫通用）
        SERIES_PREFIX_MAP = {
            "ZX": "智享系列",
            "YS": "悦尚系列",
            "JD": "经典系列",
            "HS": "惠尚系列",
            "ZW": "智享卧室系列",
            "BY": "百艳系列",
        }
        prefix = model.split('.')[0] if '.' in model else model[:2]
        series = SERIES_PREFIX_MAP.get(prefix.upper(), "")

    # 产品特点/卖点（取前 3 条）
    features = []
    in_features = False
    for line in text.split("\n"):
        if "产品特点" in line or "产品核心卖点" in line:
            in_features = True
            continue
        if in_features:
            if line.strip().startswith(("- ", "* ")):
                features.append(line.strip()[2:])
            elif line.strip() == "":
                continue  # 跳过空行，继续收集
            elif line.startswith("##"):
                if features:
                    break
            elif line.startswith("###"):
                continue  # 跳过子标题，继续收集下方的列表项

    # 核心卖点结构化数据（床垫用：按子章节分组）
    core_selling_points = []
    csp_oneliner = ""
    csp_match = re.search(r'## 产品核心卖点\s*\n(.*?)(?=\n##\s|\Z)', text, re.DOTALL)
    if csp_match:
        csp_content = csp_match.group(1).strip()
        # 提取一句话
        oneliner_match = re.search(r'\*\*一句话\*\*[:：](.+)', csp_content)
        csp_oneliner = oneliner_match.group(1).strip() if oneliner_match else ""
        # 提取各子章节（### 标题 + 描述 + 列表项）
        # 先按 ### 分割成各段
        sections_raw = re.split(r'\n###\s+', csp_content)
        for sec_raw in sections_raw[1:]:  # 跳过第一个（一句话所在的段）
            lines = sec_raw.strip().split('\n')
            if not lines:
                continue
            sec_title = lines[0].strip()
            items = []
            for line in lines[1:]:
                stripped = line.strip()
                if stripped.startswith(('- ', '* ')):
                    items.append(stripped[2:])
            if items:
                core_selling_points.append({"title": sec_title, "items": items})

    # 一句话价值塑造
    value_match = re.search(r'### 一句话价值塑造\s*\n+\s*(.+?)(?:\n|$)', text)
    tagline = value_match.group(1).strip() if value_match else ""

    # 产品故事/升级故事（床垫常用）
    product_story = ""
    story_match = re.search(r'## (?:产品故事|升级故事)\s*\n(.*?)(?=\n##\s|\Z)', text, re.DOTALL)
    if story_match:
        product_story = story_match.group(1).strip()
        # 去除 ** 粗体标记
        product_story = re.sub(r'\*\*([^*]+)\*\*', r'\1', product_story)

# 配色 & 色号 & 材质
    colors = []
    color_codes = []
    # 从「配色与材质」表提取（沙发等产品有）：色号 | 颜色名称 | 材质
    color_table = re.search(r'### 配色与材质\s*\n\|.+\n(\|.+\n?)+', text)
    if color_table:
        for line in color_table.group(0).split('\n'):
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 2 and not re.search(r'色号|颜色名称|材质|型号', ''.join(parts[:2])):
                # 跳过分隔线（如 |------|---------|------|）
                if any(p.replace('-','').strip() == '' for p in parts):
                    continue
                color_name = parts[1] if len(parts) >= 2 else ""
                material = parts[2] if len(parts) >= 3 else ""
                if color_name and color_name not in colors:
                    entry = f"{color_name}({material})" if material else color_name
                    colors.append(entry)
                if len(parts) >= 1:
                    color_codes.append(parts[0])
    # 从「配色型号:」标题提取（床类产品有）：### 配色型号: U652245/F652245-X 午夜咖啡（出样色）
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('### 配色型号:'):
            # 提取配色型号后面的颜色名称
            color_part = stripped.split('### 配色型号:')[1].strip()
            # 去掉色号部分（如 "U652245/F652245-X 午夜咖啡（出样色）"）
            name_match = re.search(r'(?:[A-Za-z0-9/_-]+)\s+(\S[^（(]*)', color_part)
            if name_match:
                color_name = name_match.group(1).strip()
                if color_name and color_name not in colors:
                    colors.append(color_name)
            # 提取色号
            code_match = re.search(r'### 配色型号:\s*([A-Za-z0-9_/-]+)', line)
            if code_match:
                code = code_match.group(1).strip()
                if code and code not in color_codes:
                    color_codes.append(code)

    # 色调分类
    color_tone = _classify_color_tone(colors)
    color_tones = _classify_color_tones(colors)

    # 价格：从规格价格表提取（精确可靠，替换旧的全文档正则）
    price_rows, table_prices = _extract_price_rows(text, category, max_rows=30)
    
    # 沙发：区分组合规格和单组件规格，最低价按组合规格计算
    combo_prices = []  # 组合规格价格（含"+"的规格，如"1左电动+1右电动"）
    single_price_rows = []  # 单组件规格行
    combo_price_rows = []  # 组合规格行
    if category == "沙发" and price_rows:
        for pr in price_rows:
            spec = pr.split(" → ")[0] if " → " in pr else pr
            # 判断是否为组合规格：包含 "+" 或 "小3双"/"3双"/"大3双"等组合描述
            if "+" in spec or re.search(r'\d双|组合|转角|贵妃', spec):
                combo_price_rows.append(pr)
                # 提取价格
                pm = re.search(r'¥([\d,]+)', pr)
                if pm:
                    combo_prices.append(int(pm.group(1).replace(',', '')))
            else:
                single_price_rows.append(pr)
    
    if category == "沙发" and combo_prices:
        min_price = min(combo_prices)
        max_price = max(combo_prices)
    else:
        min_price = min(table_prices) if table_prices else 0
        max_price = max(table_prices) if table_prices else 0

    # 沙发：提取所有长度（从规格尺寸表）
    lengths = []
    spec_section = re.search(r'### 规格尺寸\s*\n\|.+?\n(\|.+\n?)+', text)
    if spec_section:
        for line in spec_section.group(0).split("\n"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                # 尝试解析长度数值
                nums = re.findall(r'(\d{2,3})\s*(?:CM|cm|厘米)?', parts[-2] if len(parts) >= 2 else "")
                for n in nums:
                    v = int(n)
                    if 40 < v < 600:
                        lengths.append(v)

    # 床 / 配套：提取规格
    specs = []
    if category in ("床架", "配套"):
        spec_section = re.search(r'\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|', text)
        if spec_section:
            for line in text.split("\n"):
                if line.strip().startswith("|") and "实际成交价" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 3 and re.search(r'\d{3,}', parts[1]):
                        specs.append(parts[1])

    # 床身高度 & 适配床垫厚度（床架专用）
    bed_frame_height = 0
    bed_height_match = re.search(r'\*\*床身高度\*\*\s*:\s*(\d+)', text)
    if bed_height_match:
        bed_frame_height = int(bed_height_match.group(1))

    mattress_thickness = ""
    mt_match = re.search(r'\*\*适配床垫厚度\*\*\s*:\s*(.+)', text)
    if mt_match:
        mattress_thickness = mt_match.group(1).strip()

    # 设计风格（沙发/床架通用）
    design_style = ""
    ds_match = re.search(r'### 设计风格\s*\n+\s*(.+?)(?:\n|$)', text)
    if ds_match:
        design_style = ds_match.group(1).strip()
        # 清理尾部多余的描述文字（如末尾带句号的风格描述）
        design_style = re.sub(r'[。，].*$', '', design_style).strip()

    # 床脚高度（床架/沙发通用）
    bed_leg_height = 0
    blh_match = re.search(r'\*\*床脚高度\*\*\s*:\s*(\d+)', text)
    if blh_match:
        bed_leg_height = int(blh_match.group(1))

    # 床头柜搭配（床架专用）：从"建议搭配"章节提取
    nightstand_info = ""
    ns_match = re.search(r'## 建议搭配\s*\n(.*?)(?=\n##\s|\Z)', text, re.DOTALL)
    if ns_match:
        nightstand_info = ns_match.group(1).strip()
        # 去除 markdown 格式
        nightstand_info = re.sub(r'\*\*([^*]+)\*\*', r'\1', nightstand_info)
        nightstand_info = re.sub(r'^[-#*]\s+', '', nightstand_info, flags=re.MULTILINE)
        nightstand_info = nightstand_info.strip()

    # 排骨架/床架款式信息
    bed_frame_style = ""
    bfs_match = re.search(r'\*\*床架款式\*\*\s*:\s*(.+)', text)
    if bfs_match:
        bed_frame_style = bfs_match.group(1).strip()

    # 整体尺寸解析（沙发专用）：从 ### 尺寸详解 → **整体尺寸：** 表中提取
    # 如靠背高度、坐深、坐垫高度、扶手高度、沙发深度等
    sofa_dimensions = {}
    if category == "沙发":
        overall_table = re.search(r'\*\*整体尺寸：\*\*\s*\n\|.+\n(\|.+\n?)+', text)
        if not overall_table:
            overall_table = re.search(r'### 尺寸详解\s*\n\|.+\n\|.+\n(\|.+\n?)+', text)
        if overall_table:
            for line in overall_table.group(0).split('\n'):
                if not line.strip().startswith('|'):
                    continue
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2 and not re.search(r'项目|尺寸|组件|宽度', ''.join(parts[:2])):
                    dim_name = parts[0]
                    dim_val = re.search(r'(\d+)', parts[1])
                    if dim_val:
                        sofa_dimensions[dim_name] = int(dim_val.group(1))

    # 沙发组件尺寸（沙发专用）：从 ### 尺寸详解 → **组件尺寸：** 表中提取
    # 如 "3右A/3左A丨扶手翻折 → 186cm"
    sofa_components = {}
    all_spec_names = []
    if category == "沙发":
        # 解析组件尺寸表
        comp_table = re.search(r'\*\*组件尺寸：\*\*\s*\n\|.+\n(\|.+\n?)+', text)
        if comp_table:
            for line in comp_table.group(0).split('\n'):
                if not line.strip().startswith('|'):
                    continue
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2 and not re.search(r'组件|宽度|扶手高度|色号', ''.join(parts[:2])):
                    comp_name = parts[0]
                    comp_width = re.search(r'(\d+)', parts[1])
                    if comp_width:
                        comp_val = int(comp_width.group(1))
                        sofa_components[comp_name] = comp_val
                        all_spec_names.append(comp_name)
        # 解析规格尺寸表中的所有规格名（含单个和组合），用于搜索
        spec_section_raw = re.search(r'### 规格尺寸\s*\n\|.+?\n(\|.+\n?)+', text)
        if spec_section_raw:
            for line in spec_section_raw.group(0).split("\n"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts and re.search(r'规格|尺寸|型号|成交价|色号', ''.join(parts[:2])):
                    continue
                if parts:
                    all_spec_names.append(parts[0])

    # 床架外尺寸（床架专用）：从床架外尺寸(总长×总宽×头高)中提取
    # 如 "224×165×109" → 总长224cm, 床头尺寸(总宽)165cm, 床头高度(头高)109cm
    bed_total_length = 0   # 总长（床的长度）
    bed_head_width = 0     # 床头尺寸/总宽
    bed_head_height = 0    # 床头高度/头高
    if category == "床架":
        dims_list = []
        for line in text.split('\n'):
            if '×' not in line and 'x' not in line.lower():
                continue
            stripped = line.strip()
            if not stripped.startswith('|'):
                if '床架外尺寸' not in stripped and '外尺寸' not in stripped and '头高' not in stripped:
                    continue
                nums = re.findall(r'(\d+)\s*[×x]\s*(\d+)\s*[×x]\s*(\d+)', line.lower())
                for n in nums:
                    dims_list.append((int(n[0]), int(n[1]), int(n[2])))
                continue
            parts = [p.strip() for p in stripped.split('|') if p.strip()]
            if len(parts) < 2:
                continue
            size_col = parts[1]
            nums = re.findall(r'(\d+)\s*[×x]\s*(\d+)\s*[×x]\s*(\d+)', size_col.lower())
            for n in nums:
                l, w, h = int(n[0]), int(n[1]), int(n[2])
                if 50 <= h <= 200:  # 头高合理范围
                    dims_list.append((l, w, h))
        if dims_list:
            # 取第一个完整数据行
            bed_total_length = dims_list[0][0]
            bed_head_width = dims_list[0][1]
            bed_head_height = dims_list[0][2]

    # 材质（床垫/配套通用）：如 "Sanitized®抑菌防螨面料+乳胶+平衡支撑绵+六环精钢连锁簧+护边系统"
    material = ""
    material_match = re.search(r'\*\*材质\*\*\s*:\s*(.+)', text)
    if material_match:
        material = material_match.group(1).strip()

    # 产品配置（床垫专用）：含面料层/填充层/支撑层等
    product_config = ""
    product_config_lines = []
    config_match = re.search(r'\*\*产品配置\*\*:\s*\n((?:  .+\n?)+)', text)
    if config_match:
        raw_config = config_match.group(1).strip()
        product_config_lines = [l.strip() for l in raw_config.split('\n') if l.strip()]
        product_config = ' | '.join(product_config_lines)

    # 睡感等级（床垫专用）
    sleep_level = ""
    sleep_match = re.search(r'\*\*睡感等级\*\*\s*:\s*(.+)', text)
    if sleep_match:
        sleep_level = sleep_match.group(1).strip()

    # 床垫高度
    mattress_height = ""
    mh_match = re.search(r'\*\*床垫高度\*\*\s*:\s*(.+)', text)
    if mh_match:
        mattress_height = mh_match.group(1).strip()

    # 靠包类型（床架专用）：上下左右分段式/仅上下分段式/仅左右分段式/整体无分段/无床头
    headboard_type = ""
    hb_match = re.search(r'\*\*靠包类型\*\*\s*:\s*(.+)', text)
    if hb_match:
        headboard_type = hb_match.group(1).strip()

    # 三好（好看 / 好舒适 / 好品质）：提取纯文本用于关键词检索
    def _extract_section_text(text, section_name):
        """提取 ### section_name 章节的纯文本内容（去除markdown格式）"""
        pattern = rf'### {section_name}\s*\n(.*?)(?=\n###\s|\n##\s|\Z)'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return ""
        content = match.group(1).strip()
        # 去除 **粗体** 标记和 * 列表标记，保留纯文本
        content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
        content = re.sub(r'^[-*]\s+', '', content, flags=re.MULTILINE)
        return content.strip()

    def _extract_section_md(text, section_name):
        """提取 ### section_name 章节的原始 markdown 内容（用于展示）"""
        pattern = rf'### {section_name}\s*\n(.*?)(?=\n###\s|\n##\s|\Z)'
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    good_looks = _extract_section_md(text, "好看")
    good_comfort = _extract_section_md(text, "好舒适")
    good_quality = _extract_section_md(text, "好品质")
    good_looks_text = _extract_section_text(text, "好看")
    good_comfort_text = _extract_section_text(text, "好舒适")
    good_quality_text = _extract_section_text(text, "好品质")

    # 面料/填充/功能架（纯文本用于搜索）
    fabric_text = _extract_section_text(text, "面料")
    filling_text = _extract_section_text(text, "填充")
    frame_text = _extract_section_text(text, "功能架")

    return {
        "model": model,
        "name": name,
        "category": category,
        "series": series,
        "tagline": tagline[:80],
        "product_story": product_story,
        "features": features[:3],
        "core_selling_points": core_selling_points,
        "csp_oneliner": csp_oneliner,
"colors": colors,
        "color_codes": color_codes[:3],
        "color_tone": color_tone,
        "color_tones": color_tones,
        "min_price": min_price,
        "max_price": max_price,
        "lengths": sorted(set(lengths)),
        "specs": specs[:3],
        "bed_frame_height": bed_frame_height,
        "mattress_thickness": mattress_thickness,
        "price_rows": price_rows,
        "combo_price_rows": combo_price_rows if category == "沙发" else [],
        "single_price_rows": single_price_rows if category == "沙发" else [],
        "design_style": design_style,
        "sofa_dimensions": sofa_dimensions,
        "sofa_components": sofa_components,
        "all_spec_names": all_spec_names,
        "bed_head_height": bed_head_height,
        "bed_total_length": bed_total_length,
        "bed_head_width": bed_head_width,
        "material": material,
        "product_config": product_config,
        "product_config_lines": product_config_lines,
        "sleep_level": sleep_level,
        "mattress_height": mattress_height,
        "headboard_type": headboard_type,
        "bed_leg_height": bed_leg_height,
        "nightstand_info": nightstand_info,
        "bed_frame_style": bed_frame_style,
        "good_looks": good_looks,
        "good_comfort": good_comfort,
        "good_quality": good_quality,
        "good_looks_text": good_looks_text,
        "good_comfort_text": good_comfort_text,
        "good_quality_text": good_quality_text,
        "fabric_text": fabric_text,
        "filling_text": filling_text,
        "frame_text": frame_text,
    }


@st.cache_data(show_spinner=False, ttl=86400)
def build_product_index_v3(_version="v19_color_tones_multi"):
    """扫描所有 md 文件，构建可搜索的产品索引（_version 强制缓存刷新）"""
    index = {}
    if not os.path.exists(MD_DB_DIR):
        return index, ""
    for root, dirs, files in os.walk(MD_DB_DIR):
        for file in files:
            if not file.endswith(".md"):
                continue
            fp = os.path.join(root, file)
            rel = os.path.relpath(fp, MD_DB_DIR)
            try:
                p = _parse_md_product(fp, rel)
                index[p["model"]] = p
            except Exception:
                continue
    return index, ""


@st.cache_data(show_spinner=False, ttl=86400)
def load_images_v2():
    """仅加载图片索引"""
    imgs = {}
    if os.path.exists(JSON_INDEX_PATH):
        with open(JSON_INDEX_PATH, "r", encoding="utf-8") as f:
            imgs = json.load(f)
        for k, v in imgs.items():
            for key in ("catalog_images", "scene_images", "home_images", "real_images"):
                if key in v and v[key]:
                    v[key] = [os.path.join(BASE_DIR, p) if not os.path.isabs(p) else p for p in v[key]]
    return imgs


product_index, _ = build_product_index_v3()
images_db = load_images_v2()

# 加载卧室产品命名结构说明
NAMING_DOC_PATH = os.path.join(MD_DB_DIR, "床", "卧室产品命名结构.md")
BED_NAMING_GUIDE = ""
if os.path.exists(NAMING_DOC_PATH):
    with open(NAMING_DOC_PATH, "r", encoding="utf-8") as f:
        BED_NAMING_GUIDE = f.read()

# 命名问题关键词
NAMING_KEYWORDS = ["命名", "含义", "代表什么", "是什么意思", "怎么读", "编码", "货号", "FQ1", "PQ1", "Q1", "Q7", "F1",
                   "结构码", "面料码", "系列前缀", "齐边", "非齐边", "排骨条", "排骨架", "型号解释", "型号解读",
                   "怎么看的", "怎么看", "什么意思", "什么含义"]


def _is_naming_query(query):
    """判断用户是否在问产品命名/型号含义类问题
    如果包含具体产品型号（如 YS.B525PQ1），则走产品搜索+命名参考，不走纯命名路径"""
    q = query.lower()
    # 如果包含具体产品型号模式（字母+数字+字母数字），是产品搜索不是纯命名问题
    if re.search(r'[A-Za-z]{1,4}\.?\d{3,}[A-Za-z0-9]*', query):
        return False
    for kw in NAMING_KEYWORDS:
        if kw.lower() in q:
            return True
    return False


# ==================== 4. 预筛选函数（纯 Python，微秒级）====================
def _digit_fuzzy_match(terms, model):
    """数字模糊匹配：提取查询中的数字，与产品型号中的数字进行子串匹配
    例如 查询"815" → 型号"HS.B815PQ1"中的"B815" → 包含"815" 匹配成功
        查询"1018" → 型号"JD.M1018.H25"中的"1018" 匹配成功"""
    query_digits = set()
    for t in terms:
        query_digits.update(re.findall(r'\d+', t))
    model_digits = set(re.findall(r'\d+', model))
    for qd in query_digits:
        if len(qd) >= 2:  # 至少2位数字才有意义
            for md in model_digits:
                if len(md) < 2:  # 忽略单数字（如"1"），避免"6172"误匹配含"1"的型号
                    continue
                # 双向子串匹配："815" in "B815" 或 "B815" in "815"（后者处理极端情况）
                if qd in md or md in qd:
                    return True
    return False


def _match_style(user_style, product_style):
    """检查用户选择的风格是否匹配产品的设计风格
    例如：用户选"法式奶油风" → 产品标注"现代简约 / 原木 / 奶油风" → 匹配成功
         用户选"意式极简" → 产品标注"现代意式极简" → 匹配成功"""
    if not user_style or not product_style:
        return True
    # 将产品风格按 / 、 分隔为多个标签
    prod_tags = re.split(r'[/、,，]', product_style.lower())
    prod_tags = [t.strip() for t in prod_tags if t.strip()]
    
    # 定义用户风格 → 搜索关键词映射
    style_kw_map = {
        "现代简约": ["现代简约"],
        "温馨奶油": ["奶油"],
        "意式轻奢": ["意式", "轻奢"],
        "极简": ["极简"],
        "法式复古": ["法式", "复古", "中古"],
        "原木风": ["原木"],
        "中古风": ["中古"],
        "新中式": ["新中式", "中古"],
        "美式": ["美式"],
    }
    keywords = style_kw_map.get(user_style, [user_style.lower()])
    
    # 检查是否有任一关键词匹配任一产品标签
    for kw in keywords:
        for tag in prod_tags:
            if kw in tag:
                return True
    return False


def filter_candidates(index, category=None, max_price=None, sofa_length=None, style=None, keywords=None, min_candidates=8, fallback=True):
    """从产品索引中快速筛选候选产品
    关键词匹配策略（三级降级）：
    1. 先用关键词精确匹配，找到匹配的产品
    2. 如果不够 min_candidates 个且 fallback=True，再宽松补齐（同一品类下无需关键词的候选）
    3. 如果还不够，去掉预算限制补齐
    返回：候选产品列表 + 精简摘要文本（供 LLM 使用）
    
    fallback=False 时仅返回精确匹配结果，不自动补齐。"""
    candidates = []
    fallback_pool = []
    for model, p in index.items():
        # 品类拦截
        if category and p["category"] != category:
            continue
        # 预算拦截（仅排除所有规格都超预算的产品）
        if max_price and p["min_price"] > 0 and p["min_price"] > max_price:
            continue
        # 沙发长度拦截（背景墙的 70%~85%）
        if sofa_length and p["lengths"]:
            ok = any(sofa_length * 0.7 <= l <= sofa_length * 0.85 for l in p["lengths"])
            if not ok:
                continue
        # 风格拦截（沙发专用）
        if style and category == "沙发" and p.get("design_style"):
            if not _match_style(style, p["design_style"]):
                continue
        # 关键词匹配（含尺寸规格文本，用于更好搜索）
        match_keyword = True
        if keywords:
            terms = [t.strip().lower() for t in keywords.replace(",", " ").split() if len(t.strip()) >= 2]
            # 中文自然语言查询增强：从连续中文中提取数字 + 2字词
            raw_lower = keywords.lower()
            # 提取所有数字
            for num in re.findall(r'\d+', raw_lower):
                if num not in terms:
                    terms.append(num)
            # 提取中文2字滑动窗口（如"靠背"、"高度"、"沙发"）
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', raw_lower)
            for i in range(len(chinese_chars) - 1):
                bigram = chinese_chars[i] + chinese_chars[i+1]
                if bigram not in terms:
                    terms.append(bigram)
            if terms:
                # 扩充 haystack：整合所有已提取字段，无需手动添加关键词
                price_text = " ".join(p.get("price_rows", []))
                colors_text = " ".join(p.get("colors", []))
                codes_text = " ".join(p.get("color_codes", []))
                spec_names_text = " ".join(p.get("all_spec_names", []))
                component_text = ""
                if p.get("sofa_components"):
                    for cname, cwidth in p["sofa_components"].items():
                        component_text += f" {cname} {cwidth}cm"
                dims_text = ""
                if p.get("sofa_dimensions"):
                    for dk, dv in p["sofa_dimensions"].items():
                        dims_text += f" {dk} {dv}cm"
                haystack = (
                    f"{p['category']} {model} {p['name']} {p['series']} "
                    f"{p.get('design_style','')} {p.get('tagline','')} "
                    f"{colors_text} {codes_text} {price_text} {spec_names_text} {component_text} {dims_text} "
                    f"{' '.join(p.get('features',[]))} "
                    f"{p.get('mattress_thickness','')} "
                    f"{p.get('material','')} {p.get('product_config','')} "
                    f"{p.get('headboard_type','')} "
                    f"总长{p.get('bed_total_length',0)}cm 总宽{p.get('bed_head_width',0)}cm 头高{p.get('bed_head_height',0)}cm "
                    f"{p.get('color_tone','')} "
                    f"{p.get('good_looks_text','')} {p.get('good_comfort_text','')} {p.get('good_quality_text','')} "
                    f"{p.get('fabric_text','')} {p.get('filling_text','')} {p.get('frame_text','')} "
                ).lower()
                # 1) 直接子串匹配
                if any(t in haystack for t in terms):
                    pass
                else:
                    # 2) 数字模糊匹配
                    match_keyword = _digit_fuzzy_match(terms, model)
            else:
                match_keyword = True
        
        if match_keyword:
            candidates.append(p)
        else:
            fallback_pool.append(p)
        
        if len(candidates) >= min_candidates:
            break

    # 降级策略：仅当 fallback=True 时，关键词匹配不够时用品类/预算内产品补齐
    if fallback and len(candidates) < min_candidates and fallback_pool:
        need = min(min_candidates - len(candidates), len(fallback_pool))
        candidates.extend(fallback_pool[:need])

    # ------------------ 优化点 1：按最低价格升序排序 ------------------
    # 确保低价/性价比款排在最前面，防止 AI 产生"库里都是贵货"的先入为主错觉
    candidates.sort(key=lambda x: x.get("min_price", 0))
    # ---------------------------------------------------------------

    # 生成精简摘要文本（用 .get() 安全读取，兼容旧缓存）
    lines = []
    for p in candidates:
        line = f"- {p.get('model', '?')} {p.get('name', '?')} | {p.get('series', '')} | 价格区间: ¥{p.get('min_price', 0):,}~¥{p.get('max_price', 0):,}"
        if p.get("lengths"):
            line += f" | 可选长度(CM): {', '.join(str(l) for l in p['lengths'])}"
        if p.get("specs"):
            line += f" | 规格: {', '.join(p['specs'][:3])}"
        if p.get("colors"):
            colors_show = p["colors"]
            if any('(' in c or '（' in c for c in colors_show):
                line += f" | 颜色: {'/'.join(colors_show[:3])}"
            else:
                line += f" | 配色: {'/'.join(colors_show[:3])}"
        if p.get("color_tone"):
            line += f" | 色调: {p['color_tone']}"
        if p.get("bed_frame_height"):
            line += f" | 床身高度: {p['bed_frame_height']}cm"
        if p.get("mattress_thickness"):
            line += f" | 适配床垫厚度: {p['mattress_thickness']}"
        if p.get("headboard_type"):
            line += f" | 靠包类型: {p['headboard_type']}"
        if p.get("tagline"):
            line += f" | 卖点: {p['tagline']}"
        if p.get("design_style"):
            line += f" | 风格: {p['design_style']}"
        if p.get("features"):
            line += f" | 特点: {'; '.join(p['features'][:2])}"
        if p.get("material"):
            # 材质简短显示，不换行
            line += f" | 材质: {p['material'][:60]}"
        if p.get("price_rows"):
            # 只显示前3条价格，减少 token 量
            line += "\n    " + "\n    ".join(p["price_rows"][:3])
        if p.get("sofa_dimensions"):
            dims = p["sofa_dimensions"]
            parts = []
            for key in ["靠背高度", "坐深", "坐垫高度", "沙发深度"]:
                if key in dims:
                    parts.append(f"{key}: {dims[key]}cm")
            if parts:
                line += f" | {' '.join(parts)}"
        if p.get("sofa_components"):
            comps = p["sofa_components"]
            line += f" | 组件: {' '.join(f'{k}={v}cm' for k, v in list(comps.items())[:3])}"
        lines.append(line)

    summary = "\n".join(lines) if lines else "（无匹配产品）"
    return candidates, summary


# ==================== 5. 流式生成器 ====================
def _get_client(api_key):
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def stream_response(api_key, model, system_prompt, user_prompt, timeout=120):
    client = _get_client(api_key)
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        stream=True,
        temperature=0.2,
        timeout=timeout,
        max_tokens=16384
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            # 实时过滤 LLM 输出的 Markdown 删除线标记
            yield chunk.choices[0].delta.content.replace("~~", "")


# ==================== 5.5 PDF 报价单生成 ====================
def _img_to_base64(img_path):
    """将本地图片文件转为 base64 data URI"""
    if not img_path or not os.path.exists(img_path):
        return ""
    try:
        with open(img_path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(img_path)[1].lower().lstrip(".")
        if ext in ("jpg", "jpeg"):
            mime = "image/jpeg"
        elif ext == "png":
            mime = "image/png"
        elif ext == "webp":
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return ""


def _load_resized_image(img_path, max_width=800, quality=80):
    """加载并压缩图片，返回 PIL Image 对象，减小传输体积"""
    if not img_path or not os.path.exists(img_path):
        return None
    try:
        img = Image.open(img_path)
        # 只在宽度超过上限时缩放，避免放大
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        # 转换为 RGB 模式（兼容 PNG 透明通道）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        return img
    except Exception:
        return None


def _img_to_base64_thumb(img_path, max_width=300, quality=75):
    """生成图片缩略图的 base64 data URI，用于卡片内嵌"""
    if not img_path or not os.path.exists(img_path):
        return ""
    try:
        img = Image.open(img_path)
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception:
        return ""


def _get_product_image(model, images_db):
    """根据产品型号查找对应的 catalog 图片"""
    model_upper = model.upper()
    for folder_key, img_dict in images_db.items():
        if model_upper in folder_key.upper():
            imgs = img_dict.get("catalog_images", []) or img_dict.get("scene_images", [])
            if imgs:
                return imgs[0]
    return None


def _extract_recommended_models(report):
    """从 AI 报告文本中提取推荐的产品型号"""
    matched = set()
    for m in re.findall(r'[A-Za-z0-9.\-]+', report):
        m = m.strip().upper()
        # 模型号通常包含字母数字，长度 >= 4，且包含字母
        if len(m) >= 4 and re.search(r'[A-Z]', m):
            matched.add(m)
    return matched


def _extract_category_quantities(report):
    """从报告文本中提取每个品类的推荐数量（如"3张床"、"3个床垫"）"""
    quantities = {}
    # 常见软装品类关键词
    categories = ["床垫", "床", "沙发", "茶几", "餐桌", "餐椅", "电视柜", "衣柜", "床头柜", "书桌", "书椅", "边几", "斗柜", "装饰柜", "书柜", "酒柜"]
    # 按长度降序排序，避免"床垫"被"床"先匹配
    categories.sort(key=len, reverse=True)
    for cat in categories:
        # 匹配 "3张床垫", "3个床", "3组沙发" 等模式
        m = re.search(r'(\d+)\s*[张个组]' + re.escape(cat), report)
        if m:
            quantities[cat] = int(m.group(1))
            continue
        # 匹配 "床垫3张", "床3个" 等模式
        m = re.search(re.escape(cat) + r'\s*(\d+)\s*[张个组]', report)
        if m:
            quantities[cat] = int(m.group(1))
            continue
        # 匹配 "床×3", "床垫×3" 等模式
        m = re.search(re.escape(cat) + r'\s*[×xX]\s*(\d+)', report)
        if m:
            quantities[cat] = int(m.group(1))
    return quantities


def _format_candidates_summary(candidates_dict):
    """将候选产品字典（category → [product_dict]）格式化为与 filter_candidates 相同格式的摘要文本"""
    cat_names = {"沙发": "沙发", "床架": "床架", "床垫": "床垫", "配套": "配套"}
    parts = []
    for cat_key, cat_label in cat_names.items():
        products = candidates_dict.get(cat_key, [])
        if not products:
            parts.append(f"【{cat_label}候选】：（无匹配产品）")
            continue
        lines = []
        for p in products:
            line = f"- {p.get('model', '?')} {p.get('name', '?')} | {p.get('series', '')} | 价格区间: ¥{p.get('min_price', 0):,}~¥{p.get('max_price', 0):,}"
            if p.get("lengths"):
                line += f" | 可选长度(CM): {', '.join(str(l) for l in p['lengths'])}"
            if p.get("specs"):
                line += f" | 规格: {', '.join(p['specs'][:3])}"
            if p.get("colors"):
                colors_show = p["colors"]
                if any('(' in c or '（' in c for c in colors_show):
                    line += f" | 颜色: {'/'.join(colors_show[:3])}"
                else:
                    line += f" | 配色: {'/'.join(colors_show[:3])}"
            if p.get("color_tone"):
                line += f" | 色调: {p['color_tone']}"
            if p.get("bed_frame_height"):
                line += f" | 床身高度: {p['bed_frame_height']}cm"
            if p.get("mattress_thickness"):
                line += f" | 适配床垫厚度: {p['mattress_thickness']}"
            if p.get("headboard_type"):
                line += f" | 靠包类型: {p['headboard_type']}"
            if p.get("tagline"):
                line += f" | 卖点: {p['tagline']}"
            if p.get("design_style"):
                line += f" | 风格: {p['design_style']}"
            if p.get("features"):
                line += f" | 特点: {'; '.join(p['features'][:2])}"
            if p.get("material"):
                line += f" | 材质: {p['material'][:60]}"
            if p.get("price_rows"):
                line += "\n    " + "\n    ".join(p["price_rows"][:3])
            if p.get("sofa_dimensions"):
                dims = p["sofa_dimensions"]
                parts_d = []
                for key in ["靠背高度", "坐深", "坐垫高度", "沙发深度"]:
                    if key in dims:
                        parts_d.append(f"{key}: {dims[key]}cm")
                if parts_d:
                    line += f" | {' '.join(parts_d)}"
            if p.get("sofa_components"):
                comps = p["sofa_components"]
                line += f" | 组件: {' '.join(f'{k}={v}cm' for k, v in list(comps.items())[:3])}"
            lines.append(line)
        summary = "\n".join(lines) if lines else "（无匹配产品）"
        parts.append(f"【{cat_label}候选】：\n{summary}")
    return "\n\n".join(parts)


def _format_candidates_summary_compact(candidates_dict):
    """精简版候选产品摘要（仅型号/名称/价格/核心规格），用于微调 Prompt 避免超 token"""
    cat_names = {"沙发": "沙发", "床架": "床架", "床垫": "床垫", "配套": "配套"}
    parts = []
    for cat_key, cat_label in cat_names.items():
        products = candidates_dict.get(cat_key, [])
        if not products:
            parts.append(f"【{cat_label}】: 无")
            continue
        lines = []
        for p in products:
            line = f"- {p.get('model', '?')} {p.get('name', '?')} | ¥{p.get('min_price', 0):,}~¥{p.get('max_price', 0):,}"
            if p.get("lengths"):
                line += f" | 长度: {', '.join(str(l) for l in p['lengths'][:3])}cm"
            if p.get("specs"):
                line += f" | {', '.join(p['specs'][:2])}"
            if p.get("colors"):
                line += f" | {'/'.join(p['colors'][:2])}"
            if p.get("material"):
                line += f" | {p['material'][:30]}"
            lines.append(line)
        parts.append(f"【{cat_label}】({len(lines)}款):\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _get_recommended_products(candidates, report, images_db):
    """从候选产品中筛选出 AI 报告中推荐的产品，并分配正确数量"""
    recommended_models = _extract_recommended_models(report)
    category_quantities = _extract_category_quantities(report)
    products = []
    seen_models = set()
    # 统计每个品类有多少个产品被推荐
    for cat_name, cat_products in candidates.items():
        for p in cat_products:
            model = p.get("model", "").upper()
            if model in seen_models:
                continue
            seen_models.add(model)
            if model not in recommended_models:
                continue
            first_price = p.get("min_price", 0)
            price_rows = p.get("price_rows", [])
            if price_rows:
                m = re.search(r'[¥￥]\s*([\d,]+)', price_rows[0])
                if m:
                    first_price = int(m.group(1).replace(",", ""))
            specs = p.get("specs", [])
            spec_str = " / ".join(specs[:3]) if specs else ""
            comps = p.get("sofa_components", {})
            comp_str = "、".join(f"{k}={v}cm" for k, v in list(comps.items())[:4]) if comps else ""
            colors = p.get("colors", [])
            color_str = "、".join(colors[:3]) if colors else ""
            img_path = _get_product_image(model, images_db)
            # 根据报告文本确定该品类数量，默认为1
            qty = 1
            for cat_key, cat_qty in category_quantities.items():
                if cat_key in cat_name or cat_name in cat_key:
                    qty = cat_qty
                    break
            products.append({
                "model": p.get("model", ""),
                "name": p.get("name", ""),
                "series": p.get("series", ""),
                "category": cat_name,
                "price": first_price,
                "quantity": qty,
                "specs": spec_str,
                "components": comp_str,
                "colors": color_str,
                "material": p.get("material", ""),
                "features": p.get("features", [])[:2],
                "img_path": img_path,
            })
    # 如果 AI 报告中没提取到任何型号，回退：返回所有候选产品
    if not products:
        for cat_name, cat_products in candidates.items():
            for p in cat_products:
                model = p.get("model", "")
                if model in seen_models:
                    continue
                seen_models.add(model)
                first_price = p.get("min_price", 0)
                price_rows = p.get("price_rows", [])
                if price_rows:
                    m = re.search(r'[¥￥]\s*([\d,]+)', price_rows[0])
                    if m:
                        first_price = int(m.group(1).replace(",", ""))
                specs = p.get("specs", [])
                spec_str = " / ".join(specs[:3]) if specs else ""
                comps = p.get("sofa_components", {})
                comp_str = "、".join(f"{k}={v}cm" for k, v in list(comps.items())[:4]) if comps else ""
                colors = p.get("colors", [])
                color_str = "、".join(colors[:3]) if colors else ""
                img_path = _get_product_image(model, images_db)
                qty = 1
                for cat_key, cat_qty in category_quantities.items():
                    if cat_key in cat_name or cat_name in cat_key:
                        qty = cat_qty
                        break
                products.append({
                    "model": p.get("model", ""),
                    "name": p.get("name", ""),
                    "series": p.get("series", ""),
                    "category": cat_name,
                    "price": first_price,
                    "quantity": qty,
                    "specs": spec_str,
                    "components": comp_str,
                    "colors": color_str,
                    "material": p.get("material", ""),
                    "features": p.get("features", [])[:2],
                    "img_path": img_path,
                })
    return products


def _calculate_dynamic_budget(total_budget, need_sofa, need_chair, need_table, need_tv, need_dining, bedroom_count):
    """根据客户实际采购需求动态分配预算。

    权重分配逻辑：
    - 沙发作为客厅核心，占较大权重
    - 主卧床架+床垫次之
    - 次卧逐级递减
    - 配套产品权重最低

    示例：沙发+主卧+1次卧 → 沙发~40%, 主卧~35%, 次卧~18%, 配套~7%

    Returns:
        (sofa_budget, bed_budget, table_budget, bedroom_budgets)
        - bedroom_budgets: list of (label, amount) 用于提示词展示
    """
    # 不重复累计：一块钱只算一次
    has_table = need_table or need_tv or need_dining

    # 第一步：分配权重
    weights = {}
    if need_sofa:
        # 卧室多时沙发权重适当降低，给床品留更多预算
        sofa_weight = 40 if bedroom_count <= 2 else 35
        weights['沙发'] = sofa_weight
    if need_chair:
        weights['休闲椅'] = 8
    for i in range(bedroom_count):
        label = '主卧' if i == 0 else f'次卧{i}'
        # 主卧权重最高，次卧逐级递减，但保证最低15
        weight = 35 if i == 0 else (20 if i == 1 else 16)
        weights[label] = weight
    if has_table:
        weights['配套'] = 10

    if not weights:
        weights['沙发'] = 100

    # 第二步：按权重归一化分配
    total_weight = sum(weights.values())
    allocated = {k: int(total_budget * v / total_weight) for k, v in weights.items()}

    # 第三步：合并为品类预算
    sofa_budget = allocated.get('沙发', 0)
    bed_budget = sum(v for k, v in allocated.items() if k in ('主卧',) or k.startswith('次卧'))
    table_budget = allocated.get('配套', 0) + allocated.get('休闲椅', 0)

    # 第四步：各品类最小预算保障（确保筛选能出结果）
    min_sofa = 5000 if need_sofa else 0
    min_bed = 3000 * bedroom_count
    min_table = 3000 if has_table else 0
    total_min = min_sofa + min_bed + min_table

    if total_min >= total_budget:
        # 预算太少，全部按最小保障等比缩放
        scale = total_budget / max(total_min, 1)
        sofa_budget = int(min_sofa * scale)
        bed_budget = int(min_bed * scale)
        table_budget = int(min_table * scale)
    else:
        sofa_budget = max(sofa_budget, min_sofa)
        bed_budget = max(bed_budget, min_bed)
        table_budget = max(table_budget, min_table)

        # 确保总和不超预算
        total = sofa_budget + bed_budget + table_budget
        if total > total_budget:
            scale = total_budget / total
            sofa_budget = int(sofa_budget * scale)
            bed_budget = int(bed_budget * scale)
            table_budget = int(table_budget * scale)

    # 第五步：计算各卧室预算明细（用于提示词展示）
    bedroom_budgets = []
    total_bed_weight = sum(v for k, v in weights.items() if k in ('主卧',) or k.startswith('次卧'))
    for i in range(bedroom_count):
        label = '主卧' if i == 0 else f'次卧{i}'
        w = weights.get(label, 12)
        room_budget = int(bed_budget * w / total_bed_weight) if total_bed_weight > 0 else 0
        bedroom_budgets.append((label, room_budget))

    return sofa_budget, bed_budget, table_budget, bedroom_budgets


def _generate_quote_html():
    """根据当前 session_state 中的候选产品数据，生成报价单 HTML 字符串"""
    form = st.session_state.get("quote_form_data", {})
    candidates = st.session_state.get("quote_candidates", {})
    report = st.session_state.get("current_report", "")

    # 从 AI 报告中提取推荐产品
    products = _get_recommended_products(candidates, report, images_db)

    total_price = sum(p["price"] * p.get("quantity", 1) for p in products)
    now = datetime.now()
    doc_no = f"QU{now.strftime('%Y%m%d%H%M%S')}"

    style = form.get("style", "现代简约")
    wall_color = form.get("wall_color", "")
    floor_color = form.get("floor_color", "")
    room_width = form.get("room_width", "")
    sofa_wall_len = form.get("sofa_wall_len", "")
    budget = form.get("budget", 0)
    bedroom_detail = form.get("bedroom_detail", "")
    notes = form.get("notes", "")

    # 提取设计理念段落
    concept_text = report[:800].strip() if report else "根据客户需求与空间尺寸分析，为您量身定制全屋软装搭配方案。"
    concept_text = re.sub(r'#{1,6}\s*', '', concept_text)
    concept_text = re.sub(r'\*\*(.*?)\*\*', r'\1', concept_text)
    concept_text = concept_text[:600]

    # 生成产品表格行
    product_rows = ""
    for i, p in enumerate(products, 1):
        img_html = ""
        if p["img_path"]:
            b64 = _img_to_base64(p["img_path"])
            if b64:
                img_html = f'<img src="{b64}" style="width:60px;height:60px;object-fit:cover;border-radius:4px;" alt="{p["model"]}">'
            else:
                img_html = '<div class="img-placeholder">📦</div>'
        else:
            img_html = '<div class="img-placeholder">📦</div>'

        # 规格详细信息
        spec_detail = ""
        if p["specs"]:
            spec_detail += f'<span style="color:#64748b;">规格：{p["specs"]}</span><br>'
        if p["components"]:
            spec_detail += f'<span style="color:#64748b;">组件：{p["components"]}</span><br>'
        if p["colors"]:
            spec_detail += f'<span style="color:#64748b;">颜色：{p["colors"]}</span>'
        if p["features"]:
            feat_str = "；".join(p["features"])
            spec_detail = f'<span style="color:#64748b;">卖点：{feat_str}</span><br>' + spec_detail

        product_rows += f"""
        <tr>
            <td style="text-align: center;">{i}</td>
            <td style="text-align: center;">{img_html}</td>
            <td>
                <strong style="color:#0f172a;">{p['model']}</strong>
                <span style="color:#2563eb;font-size:10px;margin-left:4px;">{p['name']}</span>
                <br><span style="color:#94a3b8;font-size:10px;">{p['series']} · {p['category']}</span>
                <br>{spec_detail}
            </td>
            <td style="text-align: center;">{p.get('quantity', 1)}</td>
            <td style="text-align: right; font-weight: bold; color:#dc2626;">¥{p['price']:,}<br><small style="color:#94a3b8;font-weight:normal;">小计: ¥{p['price'] * p.get('quantity', 1):,}</small></td>
        </tr>"""

    # 卧室信息行
    bed_info = ""
    if bedroom_detail:
        bed_info = f"<span class='meta-label'>卧室配置：</span>{bedroom_detail}"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4 portrait;
        margin: 1.5cm;
        @bottom-right {{
            content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
            font-size: 10px;
            color: #94a3b8;
        }}
    }}
    body {{
        font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
        color: #1e293b;
        font-size: 11px;
        line-height: 1.5;
    }}
    .header-box {{
        display: flex;
        justify-content: space-between;
        border-bottom: 2px solid #2563eb;
        padding-bottom: 12px;
        margin-bottom: 16px;
    }}
    .brand-name {{ font-size: 20px; font-weight: bold; color: #2563eb; }}
    .doc-type {{ font-size: 12px; color: #64748b; text-align: right; }}
    .meta-grid {{
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 10px;
        margin-bottom: 16px;
    }}
    .meta-row {{ margin-bottom: 4px; }}
    .meta-label {{ color: #64748b; font-weight: bold; }}
    .concept-box {{
        margin-bottom: 16px;
        padding: 8px 12px;
        background: #fff;
        border-left: 3px solid #2563eb;
    }}
    .concept-title {{ font-size: 13px; font-weight: bold; color: #0f172a; margin-bottom: 4px; }}
    .quote-table {{
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        margin-bottom: 20px;
    }}
    .quote-table th {{
        background-color: #2563eb;
        color: #ffffff;
        padding: 8px;
        font-size: 11px;
    }}
    .quote-table td {{
        border-bottom: 1px solid #cbd5e1;
        padding: 8px;
        vertical-align: middle;
    }}
    tr {{ page-break-inside: avoid; }}
    thead {{ display: table-header-group; }}
    .img-placeholder {{
        width: 60px; height: 60px; background: #f1f5f9; border-radius: 4px;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto; font-size: 24px;
    }}
    .summary-section {{
        page-break-inside: avoid;
        margin-top: 20px;
    }}
    .total-price-box {{
        text-align: right;
        font-size: 14px;
        margin-bottom: 20px;
    }}
    .price-num {{ font-size: 20px; color: #dc2626; font-weight: bold; }}
    .signature-grid {{
        width: 100%;
        margin-top: 30px;
        border-top: 1px dashed #cbd5e1;
        padding-top: 15px;
    }}
</style>
</head>
<body>
    <div class="header-box">
        <div class="brand-name">KUKA HOME 软装定制</div>
        <div class="doc-type">全屋搭配设计方案 & 报价单<br><small>单号：{doc_no}</small></div>
    </div>

    <div class="meta-grid">
        <div class="meta-row">
            <span class="meta-label">装修风格：</span>{style} &nbsp;&nbsp;|&nbsp;&nbsp;
            <span class="meta-label">墙面颜色：</span>{wall_color} &nbsp;&nbsp;|&nbsp;&nbsp;
            <span class="meta-label">地面材质：</span>{floor_color}
        </div>
        <div class="meta-row">
            <span class="meta-label">空间尺寸：</span>客厅开间 {room_width}米 / 沙发背景墙 {sofa_wall_len}米 &nbsp;&nbsp;|&nbsp;&nbsp;
            <span class="meta-label">预算区间：</span>¥{budget:,} 元
        </div>
        {('<div class="meta-row">' + bed_info + '</div>') if bed_info else ''}
        {('<div class="meta-row"><span class="meta-label">备注：</span>' + notes + '</div>') if notes else ''}
    </div>

    <div class="concept-box">
        <div class="concept-title">空间搭配与设计理念</div>
        <p>{concept_text}</p>
    </div>

    <table class="quote-table">
        <thead>
            <tr>
                <th style="width: 6%;">序号</th>
                <th style="width: 12%;">产品图片</th>
                <th style="width: 52%;">产品名称 / 型号 / 规格 / 颜色</th>
                <th style="width: 8%;">数量</th>
                <th style="width: 22%;">成交价</th>
            </tr>
        </thead>
        <tbody>
            {product_rows if product_rows else '<tr><td colspan="5" style="text-align: center; color: #94a3b8;">暂无详细产品清单，请查看上方设计方案</td></tr>'}
        </tbody>
    </table>

    <div class="summary-section">
        <div class="total-price-box">
            <span>全屋选购打包优惠组合价：</span>
            <span class="price-num">¥{total_price:,}.00</span>
        </div>

        <table style="width: 100%; margin-top: 30px;">
            <tr>
                <td style="width: 50%;"><strong>设计师/导购签名：</strong>__________________</td>
                <td style="width: 50%;"><strong>客户确认签字：</strong>__________________</td>
            </tr>
        </table>

        <p style="color: #94a3b8; font-size: 9px; margin-top: 20px; text-align: center;">
            * 本方案报价有效期为 7 天。包含免费送货入户与专业安装服务。最终解释权归 KUKA HOME 官方授权门店所有。
        </p>
    </div>
</body>
</html>"""
    return html


def _generate_quote_pdf():
    """使用 fpdf2 生成报价单 PDF 并返回 bytes"""
    form = st.session_state.get("quote_form_data", {})
    candidates = st.session_state.get("quote_candidates", {})
    report = st.session_state.get("current_report", "")

    # 注册中文字体 - 优先使用纯 TTF 字体（TTC 集合字体子集化有问题）
    cjk_font_path = None
    # 方案1: 使用 simhei.ttf (黑体, 纯 TTF, 最稳定)
    if os.path.exists("C:/Windows/Fonts/simhei.ttf"):
        cjk_font_path = "C:/Windows/Fonts/simhei.ttf"
    # 方案2: 使用 simfang.ttf (仿宋, 纯 TTF)
    if not cjk_font_path and os.path.exists("C:/Windows/Fonts/simfang.ttf"):
        cjk_font_path = "C:/Windows/Fonts/simfang.ttf"
    # 方案3: 使用 msyh.ttc (微软雅黑, TTC, 需 uni=True)
    if not cjk_font_path and os.path.exists("C:/Windows/Fonts/msyh.ttc"):
        cjk_font_path = "C:/Windows/Fonts/msyh.ttc"
    # 方案4: 使用 simsun.ttc (宋体, TTC)
    if not cjk_font_path and os.path.exists("C:/Windows/Fonts/simsun.ttc"):
        cjk_font_path = "C:/Windows/Fonts/simsun.ttc"

    # 从 AI 报告中提取推荐产品
    recommended_products = _get_recommended_products(candidates, report, images_db)
    products = []
    for p in recommended_products:
        products.append({
            "model": p["model"],
            "name": p["name"],
            "series": p["series"],
            "category": p["category"],
            "price": p["price"],
            "quantity": p.get("quantity", 1),
            "specs": p["specs"],
        })

    total_price = sum(p["price"] * p["quantity"] for p in products)
    now = datetime.now()
    doc_no = f"QU{now.strftime('%Y%m%d%H%M%S')}"

    style = form.get("style", "现代简约")
    wall_color = form.get("wall_color", "")
    floor_color = form.get("floor_color", "")
    room_width = form.get("room_width", "")
    sofa_wall_len = form.get("sofa_wall_len", "")
    budget = form.get("budget", 0)
    bedroom_detail = form.get("bedroom_detail", "")
    notes = form.get("notes", "")

    concept_text = report[:600].strip() if report else "根据客户需求与空间尺寸分析，为您量身定制全屋软装搭配方案。"
    concept_text = re.sub(r'#{1,6}\s*', '', concept_text)
    concept_text = re.sub(r'\*\*(.*?)\*\*', r'\1', concept_text)
    concept_text = re.sub(r'\n+', ' ', concept_text)[:500]

    # 创建 PDF
    class QuotePDF(FPDF):
        def __init__(self, font_path):
            super().__init__()
            self.font_path = font_path
            if font_path:
                self.add_font("CJK", "", font_path)
                self.add_font("CJK", "B", font_path)

        def header(self):
            if self.font_path:
                self.set_font("CJK", "B", 16)
            else:
                self.set_font("Helvetica", "B", 16)
            self.set_text_color(37, 99, 235)
            self.cell(0, 10, "KUKA HOME  \u8f6f\u88c5\u5b9a\u5236\u62a5\u4ef7\u5355", new_x="LMARGIN", new_y="NEXT")
            if self.font_path:
                self.set_font("CJK", "", 8)
            else:
                self.set_font("Helvetica", "", 8)
            self.set_text_color(100, 116, 139)
            self.cell(0, 5, f"\u5355\u53f7: {doc_no}", new_x="LMARGIN", new_y="NEXT")
            self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
            self.ln(8)

        def footer(self):
            self.set_y(-15)
            if self.font_path:
                self.set_font("CJK", "", 8)
            else:
                self.set_font("Helvetica", "", 8)
            self.set_text_color(148, 163, 184)
            self.cell(0, 10, f"\u7b2c {self.page_no()} \u9875 / \u5171 {{nb}} \u9875", align="C")

    pdf = QuotePDF(cjk_font_path)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    def cjk(text="", bold=False, size=9):
        """使用 CJK 字体或 Helvetica 书写中文"""
        if cjk_font_path:
            pdf.set_font("CJK", "B" if bold else "", size)
        else:
            pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(30, 41, 59)

    # --- 客户信息区 ---
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, pdf.get_y(), 190, 28, style="DF")
    y_start = pdf.get_y() + 3
    pdf.set_xy(14, y_start)
    cjk(size=9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "\u88c5\u4fee\u98ce\u683c:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(50, 5, style, new_x="END")
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "\u5899\u9762\u989c\u8272:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(50, 5, wall_color, new_x="END")
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "\u5730\u9762\u6750\u8d28:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 5, floor_color, new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(14)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "\u7a7a\u95f4\u5c3a\u5bf8:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(50, 5, f"\u5ba2\u5385\u5f00\u95f4 {room_width}\u7c73 / \u80cc\u666f\u5899 {sofa_wall_len}\u7c73", new_x="END")
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "\u9884\u7b97\u533a\u95f4:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 5, f"\uffe5{budget:,} \u5143", new_x="LMARGIN", new_y="NEXT")

    if bedroom_detail:
        pdf.set_x(14)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(25, 5, "\u5367\u5ba4\u914d\u7f6e:", new_x="END")
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 5, bedroom_detail[:80], new_x="LMARGIN", new_y="NEXT")
    if notes:
        pdf.set_x(14)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(25, 5, "\u5907\u6ce8:", new_x="END")
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 5, notes[:80], new_x="LMARGIN", new_y="NEXT")

    pdf.ln(12)

    # --- 设计理念 ---
    cjk(bold=True, size=11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, "\u7a7a\u95f4\u642d\u914d\u4e0e\u8bbe\u8ba1\u7406\u5ff5", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(37, 99, 235)
    pdf.line(10, pdf.get_y(), 12, pdf.get_y())
    pdf.ln(2)
    cjk(size=9)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5, concept_text)
    pdf.ln(8)

    # --- 产品报价表 ---
    cjk(bold=True, size=11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, "\u4ea7\u54c1\u62a5\u4ef7\u660e\u7ec6", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # 表头
    col_w = [10, 50, 24, 22, 24]  # 序号, 产品名称/型号/规格, 数量, 单价, 小计
    headers = ["#", "\u4ea7\u54c1\u540d\u79f0 / \u578b\u53f7 / \u89c4\u683c", "\u6570\u91cf", "\u5355\u4ef7", "\u5c0f\u8ba1"]
    cjk(bold=True, size=8)
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C" if i != 1 else "L")
    pdf.ln()

    # 数据行
    cjk(size=8)
    fill = False
    for i, p in enumerate(products, 1):
        if pdf.get_y() > 260:
            pdf.add_page()
            # 重复表头
            cjk(bold=True, size=8)
            pdf.set_fill_color(37, 99, 235)
            pdf.set_text_color(255, 255, 255)
            for j, h in enumerate(headers):
                pdf.cell(col_w[j], 7, h, border=1, fill=True, align="C" if j != 1 else "L")
            pdf.ln()
            cjk(size=8)
            fill = False

        if fill:
            pdf.set_fill_color(248, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(30, 41, 59)

        subtitle = f"{p['model']} {p['name']}"
        if p['specs']:
            subtitle += f" ({p['specs']})"
        subtotal = p["price"] * p["quantity"]
        pdf.cell(col_w[0], 7, str(i), border=1, align="C", fill=True)
        pdf.cell(col_w[1], 7, subtitle[:30], border=1, fill=True)
        pdf.cell(col_w[2], 7, str(p["quantity"]), border=1, align="C", fill=True)
        pdf.cell(col_w[3], 7, f"\uffe5{p['price']:,}", border=1, align="R", fill=True)
        pdf.cell(col_w[4], 7, f"\uffe5{subtotal:,}", border=1, align="R", fill=True)
        pdf.ln()
        fill = not fill

    pdf.ln(5)

    # --- 总价 ---
    if cjk_font_path:
        pdf.set_font("CJK", "B", 14)
    else:
        pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(220, 38, 38)
    pdf.cell(0, 10, f"\u5408\u8ba1:  \uffe5{total_price:,}.00", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # --- 签署区 ---
    pdf.set_draw_color(203, 213, 225)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(10)

    cjk(size=9)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 7, "\u8bbe\u8ba1\u5e08/\u5bfc\u8d2d\u7b7e\u540d:  __________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "\u5ba2\u6237\u786e\u8ba4\u7b7e\u5b57:  __________________", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    cjk(size=7)
    pdf.set_text_color(148, 163, 184)
    pdf.multi_cell(0, 4, "* \u672c\u65b9\u6848\u62a5\u4ef7\u6709\u6548\u671f\u4e3a 7 \u5929\u3002\u5305\u542b\u514d\u8d39\u9001\u8d27\u5165\u6237\u4e0e\u4e13\u4e1a\u5b89\u88c5\u670d\u52a1\u3002\u6700\u7ec8\u89e3\u91ca\u6743\u5f52 KUKA HOME \u5b98\u65b9\u6388\u6743\u95e8\u5e97\u6240\u6709\u3002", align="C")

    # 输出
    return pdf.output()


# ==================== 6. CSS ====================
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    .main-header { font-size:2.2rem; font-weight:700; color:#1e293b; margin-bottom:0.5rem; }
    .sub-header { font-size:1.0rem; color:#64748b; margin-bottom:1.5rem; }
    div[data-testid="stExpander"] { background-color:#fff; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,0.04); }
    .stButton>button { width:100%; background:linear-gradient(135deg,#2563eb 0%,#1d4ed8 100%); color:#fff; border-radius:8px; border:none; padding:0.6rem 1rem; font-weight:600; font-size:1rem; box-shadow:0 4px 10px rgba(37,99,235,0.2); }
    .stButton>button:hover { background:linear-gradient(135deg,#1d4ed8 0%,#1e40af 100%); box-shadow:0 6px 15px rgba(37,99,235,0.3); }
    section[data-testid="stSidebar"] { background-color:#fff; border-right:1px solid #e2e8f0; }
    
    /* ===== 产品卡片样式 ===== */
    .pd-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin: 16px 0; }
    .pd-card { background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(15,23,42,0.06), 0 1px 3px rgba(15,23,42,0.04); border: 1px solid #e2e8f0; overflow: hidden; transition: all 0.2s ease; }
    .pd-card:hover { box-shadow: 0 8px 24px rgba(15,23,42,0.1), 0 2px 6px rgba(15,23,42,0.06); transform: translateY(-2px); }
    .pd-head { padding: 14px 16px 10px; border-bottom: 1px solid #f1f5f9; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .pd-cat { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #fff; }
    .pd-cat.sofa { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
    .pd-cat.bed { background: linear-gradient(135deg, #ec4899, #f472b6); }
    .pd-cat.mattress { background: linear-gradient(135deg, #10b981, #34d399); }
    .pd-cat.table { background: linear-gradient(135deg, #f59e0b, #fbbf24); color: #78350f; }
    .pd-model { font-size: 14px; font-weight: 700; color: #0f172a; }
    .pd-name { font-size: 13px; color: #64748b; }
    .pd-series { font-size: 11px; color: #94a3b8; margin-left: auto; }
    .pd-price { padding: 12px 16px; background: linear-gradient(135deg, #fef2f2, #fff1f2); border-bottom: 1px solid #fecaca; }
    .pd-price .pl { font-size: 11px; color: #94a3b8; margin-right: 6px; }
    .pd-price .pv { font-size: 22px; font-weight: 800; color: #dc2626; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; letter-spacing: -0.5px; }
    .pd-price .pv small { font-size: 13px; font-weight: 600; }
    .pd-body { padding: 12px 16px 16px; }
    .pd-info { font-size: 12px; color: #475569; line-height: 1.9; }
    .pd-info .k { color: #94a3b8; font-size: 11px; }
    .pd-info .v { color: #334155; font-weight: 500; }
    .pd-spec-tag { display: inline-block; padding: 2px 8px; background: #f1f5f9; color: #475569; border-radius: 4px; font-size: 11px; margin: 2px 4px 2px 0; }
    .pd-room-tag { display: inline-block; padding: 2px 8px; background: #eff6ff; color: #2563eb; border-radius: 4px; font-size: 11px; font-weight: 500; margin-right: 4px; }
    .pd-section-title { font-size: 12px; font-weight: 600; color: #0f172a; margin: 10px 0 6px; padding-bottom: 4px; border-bottom: 1px solid #f1f5f9; }
    .pd-price-table { width: 100%; border-collapse: collapse; font-size: 11px; margin: 6px 0; }
    .pd-price-table th { background: #f8fafc; color: #64748b; font-weight: 500; text-align: left; padding: 5px 8px; border-bottom: 1px solid #e2e8f0; }
    .pd-price-table td { padding: 4px 8px; border-bottom: 1px solid #f1f5f9; color: #475569; }
    .pd-price-table td.pd-td-price { color: #dc2626; font-weight: 600; text-align: right; }
    .pd-features { margin: 6px 0; font-size: 11px; color: #475569; line-height: 1.7; }
    .pd-features li { margin: 0; padding-left: 4px; list-style: none; position: relative; }
    .pd-features li::before { content: "✦"; color: #3b82f6; font-size: 9px; margin-right: 5px; }
    .pd-goods { display: flex; gap: 6px; margin: 8px 0 4px; flex-wrap: wrap; }
    .pd-good-tag { flex: 1; min-width: 70px; padding: 4px 6px; border-radius: 6px; font-size: 10px; text-align: center; font-weight: 500; }
    .pd-good-tag.g1 { background: #fef3c7; color: #92400e; }
    .pd-good-tag.g2 { background: #dcfce7; color: #166534; }
    .pd-good-tag.g3 { background: #dbeafe; color: #1e40af; }
    .pd-imgs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
    .pd-img-item { position: relative; border-radius: 6px; overflow: hidden; background: #f1f5f9; aspect-ratio: 4/3; }
    .pd-img-item img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .pd-img-label { position: absolute; bottom: 0; left: 0; right: 0; padding: 3px 6px; font-size: 10px; color: #fff; background: linear-gradient(transparent, rgba(0,0,0,0.6)); }
    .pd-img-placeholder { display: flex; align-items: center; justify-content: center; height: 100%; color: #cbd5e1; font-size: 10px; }
    .pd-tagline { font-size: 11px; color: #64748b; font-style: italic; margin: 4px 0 0; padding: 6px 8px; background: #f8fafc; border-left: 3px solid #3b82f6; border-radius: 0 4px 4px 0; line-height: 1.5; }
    .pd-price-range { font-size: 11px; color: #94a3b8; margin-top: 4px; }
    .pd-price-range strong { color: #dc2626; font-weight: 600; }
    .pd-more-specs { margin-top: 4px; }
    .pd-more-specs summary { list-style: none; cursor: pointer; font-size: 10px; color: #3b82f6; text-align: right; padding: 2px 4px; }
    .pd-more-specs summary::before { content: "▾ 查看更多规格"; }
    .pd-more-specs[open] summary::before { content: "▴ 收起"; }
    .pd-more-info { margin-top: 6px; }
    .pd-more-info summary { list-style: none; cursor: pointer; font-size: 11px; color: #3b82f6; text-align: center; padding: 6px 8px; background: #eff6ff; border-radius: 6px; font-weight: 500; }
    .pd-more-info summary::before { content: "▾ 查看更多信息"; }
    .pd-more-info[open] summary::before { content: "▴ 收起信息"; }
    .pd-good-content { font-size: 10px; color: #64748b; line-height: 1.6; margin-top: 4px; padding: 6px 8px; background: #f8fafc; border-radius: 4px; }
    .pd-good-content .gc-title { font-weight: 600; color: #334155; font-size: 11px; margin-bottom: 2px; }
    .pd-color-chip { display: inline-block; padding: 2px 6px; margin: 1px 3px 1px 0; font-size: 10px; border-radius: 3px; background: #f1f5f9; color: #475569; font-family: monospace; }
    .pd-color-chip .cn { font-family: inherit; color: #64748b; margin-left: 2px; }
    .pd-card-wrapper { background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(15,23,42,0.06), 0 1px 3px rgba(15,23,42,0.04); border: 1px solid #e2e8f0; overflow: hidden; margin-bottom: 16px; }
    .pd-card-wrapper:hover { box-shadow: 0 8px 24px rgba(15,23,42,0.1); }
    .pd-imgs-st { padding: 0 12px 12px; }
    .pd-imgs-label { font-size: 11px; color: #64748b; margin: 0 0 6px; font-weight: 500; }
</style>
""", unsafe_allow_html=True)


# ==================== 7. 侧边栏 ====================
# 默认值（侧边栏锁定时主页面仍可用）
try:
    _default_key = os.getenv("DEEPSEEK_API_KEY", "") or st.secrets.get("DEEPSEEK_API_KEY", "")
except Exception:
    _default_key = os.getenv("DEEPSEEK_API_KEY", "")
api_key = _default_key
model_name = "deepseek-v4-flash"

with st.sidebar:
    # ---- 密码锁 ----
    if not st.session_state.sidebar_unlocked:
        st.markdown("### 🔒 管理面板已锁定")
        pwd = st.text_input("请输入管理密码解锁", type="password", key="sidebar_pwd")
        if st.button("解锁", use_container_width=True):
            if pwd == SIDEBAR_PASSWORD:
                st.session_state.sidebar_unlocked = True
                st.rerun()
            else:
                st.error("密码错误")
    else:
        st.header("⚙️ DeepSeek API 设置")
        api_key = st.text_input("API Key（留空使用 secrets）", type="password", value=_default_key, placeholder="sk-...")
        model_name = st.selectbox("模型选择", ["deepseek-v4-flash", "deepseek-v4-pro"], index=0)
        st.divider()
        st.header("📊 数据库状态")
        st.success(f"✅ {len(product_index)} 个产品已索引\n({len(images_db)} 个图片映射)")
        cat_counts = {}
        for p in product_index.values():
            c = p["category"]
            cat_counts[c] = cat_counts.get(c, 0) + 1
        debug_lines = [f"{k}: {v}个" for k, v in sorted(cat_counts.items())]
        st.caption("📌 品类分布: " + " | ".join(debug_lines) if debug_lines else "⚠️ 索引为空")
        md_files_found = 0
        if os.path.exists(MD_DB_DIR):
            for root, dirs, files in os.walk(MD_DB_DIR):
                for f in files:
                    if f.endswith(".md"):
                        md_files_found += 1
        st.caption(f"📁 markdown_db: {'存在' if os.path.exists(MD_DB_DIR) else '不存在'} | .md文件数: {md_files_found}")
        st.divider()
        st.caption("💡 版本: `ai导购助手0.0.0.2`")

        st.divider()
        with st.expander("📊 查询数据导出"):
            st.caption(f"已记录 {_get_log_count()} 条查询")
            if st.button("📥 下载 query_log.jsonl"):
                if os.path.exists(QUERY_LOG_PATH):
                    with open(QUERY_LOG_PATH, "r", encoding="utf-8") as f:
                        st.download_button("点击下载", f.read(), file_name="query_log.jsonl", mime="application/jsonl")
                else:
                    st.info("暂无记录")


# ==================== 8. 顶部 Header ====================
st.markdown('<div class="main-header">🛋️ KUKA 赛博软装与睡眠主理人</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">基于空间几何计算与 DeepSeek AI 大模型的智能全屋配齐系统</div>', unsafe_allow_html=True)

# ==================== 9. Tab ====================
main_tab1, main_tab2 = st.tabs(["🏠 全屋 AI 软装与睡眠方案生成", "🔍 导购全品类速查助手"])


# =========================================================================
# Tab 1
# =========================================================================
with main_tab1:
    col_left, col_right = st.columns([1, 1.3], gap="large")

    with col_left:
        st.subheader("📋 空间需求与预算录入")

        with st.expander("🏠 1. 客厅环境与风格", expanded=True):
            style_pref = st.selectbox("装修风格偏好", ["现代简约", "温馨奶油", "意式轻奢", "极简", "法式复古", "原木风", "中古风", "新中式", "美式"])
            col_dim1, col_dim2 = st.columns(2)
            with col_dim1:
                room_width = st.number_input("客厅开间/视距 (米)", min_value=2.0, max_value=8.0, value=3.6, step=0.1)
            with col_dim2:
                sofa_wall_len = st.number_input("沙发背景墙长度 (米)", min_value=2.0, max_value=8.0, value=4.2, step=0.1)
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                wall_color = st.selectbox("墙面颜色", ["奶咖色", "奶油白", "米杏色", "太空灰", "纯白", "咖色护墙板"])
            with col_c2:
                floor_color = st.selectbox("地面材质", ["亮光灰色", "亮光白色", "哑光灰色", "哑光奶咖", "柔光奶咖", "暗色岩板", "胡桃色木纹砖"])

        with st.expander("🛒 2. 客厅与餐厨采购清单", expanded=True):
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                need_sofa = st.checkbox("🛋️ 沙发", value=False)
                need_chair = st.checkbox("🪑 单人休闲椅", value=False)
                need_table = st.checkbox("☕ 茶几", value=False)
            with col_c2:
                need_tv = st.checkbox("📺 电视柜", value=False)
                need_dining = st.checkbox("🍽️ 餐桌椅组合", value=False)

        with st.expander("🛏️ 3. 卧室配置与睡眠偏好", expanded=True):
            ROOM_TYPES = ["主卧", "儿子房", "女儿房", "老人房", "次卧/客卧"]
            MATTRESS_TYPES = [
                "高端护脊/独立弹簧（适合主卧/深睡释压）",
                "青少年/儿童护脊床垫（防脊柱弯曲/高支撑）",
                "硬挺护脊/天然棕榈（适合老人/习惯睡硬床）",
                "软硬适中/浮法乳胶层（微环境透气/全家通用）",
                "高性价比舒适床垫"
            ]
            selected_rooms = st.multiselect("选择配置的卧室：", options=ROOM_TYPES, default=[])
            bedroom_configs = []
            for r_name in selected_rooms:
                st.markdown(f"**📌 {r_name}**")
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    hb_limit = st.number_input(f"{r_name} 床头墙允许最大净宽 (米)", min_value=1.2, max_value=4.0, value=2.2 if r_name == "主卧" else 1.8, step=0.05, key=f"hb_{r_name}")
                    bed_spec = st.selectbox(f"{r_name} 床架规格", ["1.8米床 (180*200cm)", "1.5米床 (150*200cm)", "1.2米床 (120*200cm)"], key=f"bs_{r_name}")
                with col_b2:
                    need_mat = st.checkbox(f"为{r_name}选配床垫", value=True, key=f"mc_{r_name}")
                    def_idx = 0
                    if "儿子" in r_name or "女儿" in r_name: def_idx = 1
                    elif "老人" in r_name: def_idx = 2
                    elif "次卧" in r_name: def_idx = 4
                    mat_pref = st.selectbox(f"{r_name} 床垫类型", MATTRESS_TYPES, index=def_idx, key=f"mp_{r_name}") if need_mat else "不需要床垫"
                bedroom_configs.append({"room_name": r_name, "hb_limit": f"{hb_limit}米", "bed_spec": bed_spec, "mat_pref": mat_pref})

        with st.expander("💰 4. 预算与特殊需求", expanded=True):
            total_budget = st.number_input("全屋采购总预算 (元)", min_value=5000, max_value=500000, value=5000, step=1000)
            special_tags = st.multiselect(
                "特殊功能需求：",
                options=["电动零重力 / 智能功能沙发", "养宠家庭（防抓擦/防粘毛）", "有婴幼儿（防磕碰圆角）", "扫地机器人进出（离地>12cm）", "腰椎保护/偏硬支撑", "去电视化/自由组合模块"],
                default=[]
            )
            custom_notes = st.text_input("补充备注：", placeholder="例如：主卧想要头层牛皮床、床垫不要太厚等...")

        st.markdown("---")
        submit_btn = st.button("🚀 一键生成全屋 AI 搭配与睡眠方案", type="primary", use_container_width=True, disabled=st.session_state.query_in_progress)

    with col_right:
        st.subheader("✨ AI 搭配报告与推荐展示")

        if submit_btn:
            # 防止重复点击
            if st.session_state.query_in_progress:
                st.info("⏳ 正在检索中，请耐心等待...")
                st.stop()
            if not api_key.startswith("sk-"):
                st.error("❌ 请先配置 DeepSeek API Key（侧边栏或 secrets.toml）")
                st.stop()
            st.session_state.query_in_progress = True
            st.rerun()

        if st.session_state.query_in_progress:
            t_start = time.time()
            # 记录全屋搭配查询
            _log_query("full_plan", {
                "style": style_pref, "room_width": room_width, "sofa_wall_len": sofa_wall_len,
                "wall_color": wall_color, "floor_color": floor_color,
                "need_sofa": need_sofa, "need_chair": need_chair,
                "need_table": need_table, "need_tv": need_tv, "need_dining": need_dining,
                "bedroom_count": len(bedroom_configs),
                "bedroom_detail": [{"name": b["room_name"], "spec": b["bed_spec"], "mat": b["mat_pref"]} for b in bedroom_configs],
                "budget": total_budget, "special_tags": special_tags, "custom_notes": custom_notes,
            })

            # 保存表单数据到 session_state，供 PDF 报价单使用
            bed_detail_str = "; ".join(
                f"{b['room_name']}({b['bed_spec']},{b['mat_pref'][:20]})" for b in bedroom_configs
            ) if bedroom_configs else ""
            st.session_state.quote_form_data = {
                "style": style_pref,
                "wall_color": wall_color,
                "floor_color": floor_color,
                "room_width": room_width,
                "sofa_wall_len": sofa_wall_len,
                "budget": total_budget,
                "bedroom_detail": bed_detail_str,
                "notes": custom_notes,
                "special_tags": ", ".join(special_tags) if special_tags else "",
            }

            # ---- 预筛选：按品类+预算筛选候选产品 ----
            sofa_budget, bed_budget, table_budget, bedroom_budgets = _calculate_dynamic_budget(
                total_budget, need_sofa, need_chair, need_table, need_tv, need_dining, len(bedroom_configs)
            )

            sofa_wall_cm = sofa_wall_len * 100
            sofa_min = int(sofa_wall_cm * 0.7)
            sofa_max = int(sofa_wall_cm * 0.85)

            # ------------------ 优化点 2：按单个卧室预算精细化拦截 ------------------
            # 计算单个卧室的最大预算（例如主卧预算），防止把单价几万元的床混入候选库
            max_single_room_budget = max([amt for _, amt in bedroom_budgets], default=bed_budget)
            # 单张床架预算上限设为单卧室预算的 65%，单张床垫设为 55%
            single_bed_max = int(max_single_room_budget * 0.65) if bedroom_configs else bed_budget
            single_mat_max = int(max_single_room_budget * 0.55) if bedroom_configs else bed_budget

            sofa_candidates, sofa_summary = filter_candidates(
                product_index, category="沙发", max_price=sofa_budget, sofa_length=sofa_wall_cm, style=style_pref
            )
            bed_candidates, bed_summary = filter_candidates(
                product_index, category="床架", max_price=single_bed_max
            )
            mattress_candidates, mattress_summary = filter_candidates(
                product_index, category="床垫", max_price=single_mat_max
            )
            table_candidates, table_summary = filter_candidates(
                product_index, category="配套", max_price=table_budget
            )
            # ----------------------------------------------------------------------

            # 降级策略：某品类筛选无结果时适度放宽价格限制（1.5倍原品类预算，而非完全移除）
            _sofa_relaxed = False
            if "无匹配产品" in sofa_summary:
                sofa_candidates, sofa_summary = filter_candidates(
                    product_index, category="沙发", max_price=int(sofa_budget * 1.5), sofa_length=sofa_wall_cm, style=style_pref
                )
                sofa_summary += "\n（注：已适度放宽预算限制）"
                _sofa_relaxed = True
            _bed_relaxed = False
            if "无匹配产品" in bed_summary:
                bed_candidates, bed_summary = filter_candidates(
                    product_index, category="床架", max_price=int(single_bed_max * 1.5)
                )
                bed_summary += "\n（注：已适度放宽预算限制）"
                _bed_relaxed = True
            _mat_relaxed = False
            if "无匹配产品" in mattress_summary:
                mattress_candidates, mattress_summary = filter_candidates(
                    product_index, category="床垫", max_price=int(single_mat_max * 1.5)
                )
                mattress_summary += "\n（注：已适度放宽预算限制）"
                _mat_relaxed = True
            _table_relaxed = False
            if "无匹配产品" in table_summary:
                table_candidates, table_summary = filter_candidates(
                    product_index, category="配套", max_price=int(table_budget * 1.5)
                )
                table_summary += "\n（注：已适度放宽预算限制）"
                _table_relaxed = True

            # 保存候选产品到 session_state，供报价单使用
            st.session_state.quote_candidates = {
                "沙发": sofa_candidates,
                "床架": bed_candidates,
                "床垫": mattress_candidates,
                "配套": table_candidates,
            }

            # 标记哪些品类放宽了预算
            _relaxed_notes = []
            if _sofa_relaxed: _relaxed_notes.append("沙发")
            if _bed_relaxed: _relaxed_notes.append("床架")
            if _mat_relaxed: _relaxed_notes.append("床垫")
            if _table_relaxed: _relaxed_notes.append("配套")
            _relaxed_hint = f"（以下品类候选已适度放宽：{'、'.join(_relaxed_notes)}，请优先选择其中价格较低的产品）" if _relaxed_notes else ""

            # ------------------ 优化点 3：拆分具体卧室的床与床垫目标 ------------------
            bedroom_budget_lines = []
            for label, amount in bedroom_budgets:
                b_bed = int(amount * 0.55)
                b_mat = int(amount * 0.45)
                bedroom_budget_lines.append(f"  · {label}（床架+床垫）：总目标约 ¥{amount:,}（建议：床架约 ¥{b_bed:,}，床垫约 ¥{b_mat:,}）")
            # ------------------------------------------------------------------------

            system_prompt = f"""你是一位顶级的家居软装与健康睡眠主理人。**严格仅从下方精选候选产品中**为客户搭配方案，不得推荐列表之外的产品。

【精选沙发候选】：
{sofa_summary}

【精选床架候选】：
{bed_summary}

【精选床垫候选】：
{mattress_summary}

【精选配套候选】：
{table_summary}

【预算分配参考】（客户总预算：¥{total_budget:,}）：
- 🛋️ 沙发品类预算参考：约 ¥{sofa_budget:,}  {_relaxed_hint}
- 🛏️ 卧室品类细分目标（床架 + 床垫）：
{chr(10).join(bedroom_budget_lines) if bedroom_budget_lines else '  无卧室需求'}
- 🪑 配套（茶几/电视柜/餐桌椅）预算参考：约 ¥{table_budget:,}  {_relaxed_hint}

【打破价格偏见与匹配规则（重中之重）】：
        1. 🚫 **打破价格偏见（核心）**：
           - **绝对不要产生"一个卧室必须 8000 元"的预设错觉！**
           - 候选列表中包含大量 **¥2,000 左右的入门/性价比床架** 与 **¥1,500~¥2,500 的护脊床垫**。一个卧室（床架+床垫）完全可以在 **¥3,500 ~ ¥4,500** 内高性价比完成配置！
           - 对于次卧/老人房/儿童房或低预算需求，**必须优先选择候选列表中最低价格区间的 SKU**（如 2000 元床架 + 1800 元床垫），严禁因偏好中高端款而断定"超预算"。
        2. 💰 **严控总预算（最高优先级）**：
           - 推荐方案总价**必须**控制在预算的 **95%~100%** 之间（即 ¥{int(total_budget*0.95):,}~¥{total_budget:,}），**严格禁止超预算**！
           - 必须在输出中逐项列出每个产品的价格，并在最后计算累加总价，确认不超过 ¥{total_budget:,}。
        3. 🛏️ **必须为每个卧室配置床架+床垫**：客户选了卧室就必须推荐对应的床和床垫，不得遗漏。
        4. 📐 **沙发长度严格匹配**：沙发总长度必须在 **{sofa_min}~{sofa_max}cm** 之间。
        5. ⚠️ **价格必须使用候选产品中标注的真实价格**，不得自行编造。

【输出格式要求】：
- 产品推荐清单部分使用 **HTML 卡片** 形式呈现，**必须严格按照下方卡片模板的 CSS 类名和结构生成**
- **严禁嵌入任何 base64 图片或图片 data URI**，产品图片由系统自动在下方展示
- 除产品清单外的其余内容（分析、建议、汇总等）使用标准 Markdown 语法
- 价格必须使用候选产品中标注的真实价格，不得自行编造

【产品卡片 CSS 样式（自动注入页面，你只需使用以下类名）】：
.pd-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin: 16px 0; }}
.pd-card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(15,23,42,0.06), 0 1px 3px rgba(15,23,42,0.04); border: 1px solid #e2e8f0; overflow: hidden; transition: box-shadow 0.2s ease; }}
.pd-card:hover {{ box-shadow: 0 8px 24px rgba(15,23,42,0.1), 0 2px 6px rgba(15,23,42,0.06); }}
.pd-head {{ padding: 14px 16px 10px; border-bottom: 1px solid #f1f5f9; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.pd-cat {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #fff; }}
.pd-cat.sofa {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); }}
.pd-cat.bed {{ background: linear-gradient(135deg, #ec4899, #f472b6); }}
.pd-cat.mattress {{ background: linear-gradient(135deg, #10b981, #34d399); }}
.pd-cat.table {{ background: linear-gradient(135deg, #f59e0b, #fbbf24); color: #78350f; }}
.pd-model {{ font-size: 14px; font-weight: 700; color: #0f172a; }}
.pd-name {{ font-size: 13px; color: #64748b; }}
.pd-series {{ font-size: 11px; color: #94a3b8; margin-left: auto; }}
.pd-price {{ padding: 12px 16px; background: linear-gradient(135deg, #fef2f2, #fff1f2); border-bottom: 1px solid #fecaca; }}
.pd-price .pl {{ font-size: 11px; color: #94a3b8; margin-right: 6px; }}
.pd-price .pv {{ font-size: 22px; font-weight: 800; color: #dc2626; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; letter-spacing: -0.5px; }}
.pd-price .pv small {{ font-size: 13px; font-weight: 600; }}
.pd-body {{ padding: 12px 16px 16px; }}
.pd-info {{ font-size: 12px; color: #475569; line-height: 1.8; }}
.pd-info .k {{ color: #94a3b8; font-size: 11px; }}
.pd-info .v {{ color: #334155; font-weight: 500; }}
.pd-spec-tag {{ display: inline-block; padding: 2px 8px; background: #f1f5f9; color: #475569; border-radius: 4px; font-size: 11px; margin: 2px 4px 2px 0; }}
.pd-room-tag {{ display: inline-block; padding: 2px 8px; background: #eff6ff; color: #2563eb; border-radius: 4px; font-size: 11px; font-weight: 500; margin-right: 4px; }}

【产品卡片 HTML 模板（必须严格按此结构生成，类名不可更改）】：
<div class="pd-card">
    <div class="pd-head">
        <span class="pd-cat bed">床架</span>
        <span class="pd-model">ZX.B721FQ1</span>
        <span class="pd-name">朗悦</span>
        <span class="pd-series">智享系列</span>
    </div>
    <div class="pd-price">
        <span class="pl">成交价</span>
        <span class="pv">¥2,399 <small>起</small></span>
    </div>
    <div class="pd-body">
        <div class="pd-info">
            <div><span class="pd-room-tag">主卧</span> <span class="pd-spec-tag">201*151</span> <span class="pd-spec-tag">齐边排骨条</span></div>
            <div><span class="k">床身高</span> <span class="v">31cm</span> ｜ <span class="k">适配床垫</span> <span class="v">20-28cm</span></div>
            <div><span class="k">靠包</span> <span class="v">无床头</span> ｜ <span class="k">配色</span> <span class="v">黑武士、菊蕊白</span></div>
        </div>
    </div>
</div>

【卡片使用规则】：
1. 所有产品卡片必须包裹在 `<div class="pd-grid">...</div>` 容器中
2. 品类 class 对应：沙发用 pd-cat sofa、床架用 pd-cat bed、床垫用 pd-cat mattress、配套用 pd-cat table
3. 价格只有一个价位时直接显示（如 ¥2,599），有区间时显示"¥2,399 起"或"¥4,499 ~ ¥5,499"
4. 规格使用 span.pd-spec-tag 标签展示关键规格（如尺寸、款式等）
5. 如果是某个卧室的配置，加上 span.pd-room-tag 标签（如"主卧"、"次卧"）
6. 严禁在卡片中使用 <img> 标签或嵌入 base64 图片

【输出结构】：
一、空间尺寸与气场碰撞分析
二、全屋推荐产品清单与报价明细
    - 每个品类先用一行文字说明选择理由，然后用 HTML 卡片展示推荐产品
    - 卡片后附上 **逐项价格计算过程**，确认各品类在预算分配内、总价不超过 ¥{total_budget:,}
三、价格汇总与预算控制说明
四、科学睡眠理念与健康生活场景建议"""

            # 构造采购清单
            items_list = []
            if need_sofa: items_list.append("🛋️ 沙发")
            if need_chair: items_list.append("🪑 单人休闲椅")
            if need_table: items_list.append("☕ 茶几")
            if need_tv: items_list.append("📺 电视柜")
            if need_dining: items_list.append("🍽️ 餐桌椅组合")
            # 卧室配置自动加入采购清单
            for bd in bedroom_configs:
                items_list.append(f"🛏️ {bd['room_name']}(床架+床垫)")

            user_prompt = f"""客户需求：
- 风格：{style_pref}
- 客厅开间：{room_width}米，背景墙：{sofa_wall_len}米
- 墙面：{wall_color}，地面：{floor_color}
- **采购清单**：{'、'.join(items_list) if items_list else '无'}
- 总预算：¥{total_budget:,}（**总价不得超过预算¥{total_budget:,}**，严格禁止超预算）
- 品类预算分配参考：沙发约¥{sofa_budget:,}，床架+床垫约¥{bed_budget:,}，配套约¥{table_budget:,}
- 特殊需求：{'; '.join(special_tags)}
- 备注：{custom_notes if custom_notes else '无'}
- **卧室配置（必须为以下每个房间推荐床架+床垫）**：
{chr(10).join(f'  · {bd["room_name"]}: {bd["bed_spec"]}, 床垫需求: {bd["mat_pref"]}' for bd in bedroom_configs) if bedroom_configs else '  无卧室配置'}
"""

            # 记录候选产品筛选耗时
            t_after_filter = time.time()

            try:
                with st.status("🤖 AI 正在生成方案...", expanded=True) as status:
                    t_llm_start = time.time()
                    full_response = st.write_stream(stream_response(api_key, model_name, system_prompt, user_prompt))
                    t_llm_end = time.time()
                    filter_time = t_after_filter - t_start
                    llm_time = t_llm_end - t_llm_start
                    startup_time = t_after_filter - t_start
                    total_time = t_llm_end - t_start
                    status.update(label=f"✅ 方案生成完成（筛选 {startup_time:.1f}s + LLM {llm_time:.1f}s = 总计 {total_time:.1f}s）", state="complete")
                    st.caption(f"⏱️ 耗时明细：产品筛选 {filter_time:.1f}s → LLM 流式输出 {llm_time:.1f}s → 总耗时 {total_time:.1f}s")
                # 保存当前报告到 session_state，供后续微调使用
                st.session_state.current_report = full_response
                # 记录历史版本（安全初始化）
                st.session_state.setdefault("report_history", []).append(full_response)
            except Exception as e:
                st.error(f"❌ API 调用失败: {e}")
                st.session_state.query_in_progress = False
                st.stop()

            # 图集
            st.divider()
            st.subheader("🖼️ 推荐产品视觉预览")
            # 用候选产品列表精确匹配图片，而非从 AI 文本中模糊提取
            _all_candidates = st.session_state.get("quote_candidates", {})
            candidate_models = set()
            for cat_products in _all_candidates.values():
                for p in cat_products:
                    m = p.get("model", "")
                    if m and len(m) >= 4:
                        candidate_models.add(m.upper())

            display_count = 0
            for folder_key, img_dict in images_db.items():
                fk_upper = folder_key.upper()
                if any(m in fk_upper or fk_upper in m for m in candidate_models):
                    display_count += 1
                    with st.expander(f"📦 视觉预览：{folder_key}", expanded=False):
                        tab_cat, tab_scene, tab_home = st.tabs(["📦 规格/浏览图", "🏡 展厅/场景效果图", "📸 客户入户实景图"])
                        for tab_name, img_key in [("cat", "catalog_images"), ("scene", "scene_images"), ("home", "home_images")]:
                            with [tab_cat, tab_scene, tab_home][["cat", "scene", "home"].index(tab_name)]:
                                imgs = img_dict.get(img_key, []) or (img_dict.get("real_images", []) if img_key == "home_images" else [])
                                if imgs:
                                    # 只显示前3张，使用压缩图减少传输体积
                                    for i in range(0, min(len(imgs), 3), 3):
                                        cols = st.columns(3)
                                        for j, img_p in enumerate(imgs[i:i+3]):
                                            with cols[j]:
                                                resized = _load_resized_image(img_p, max_width=500)
                                                if resized:
                                                    st.image(resized, use_container_width=True)
                                                else:
                                                    st.image(img_p, use_container_width=True)
                                else:
                                    st.info({"cat": "暂无规格/浏览图", "scene": "暂无展厅/场景效果图", "home": "📸 暂无客户入户实景图"}[tab_name])

            if display_count == 0:
                st.info("💡 提示：未能根据方案自动匹配到本地图片。")

            # 解锁按钮，允许再次查询
            st.session_state.query_in_progress = False
        else:
            # 如果已有方案报告（例如微调后刷新页面），直接展示
            if st.session_state.current_report:
                st.markdown(st.session_state.current_report, unsafe_allow_html=True)
            else:
                st.info("👈 请在左侧填写客户的需求和预算。")

    # --- 方案微调区域（放在 if/else 外部，有报告时才显示） ---
        if st.session_state.current_report:
            # PDF 导出按钮
            col_pdf1, col_pdf2 = st.columns([1, 1])
            with col_pdf1:
                if st.button("📄 导出 PDF 报价单", key="export_pdf_btn", use_container_width=True):
                    with st.spinner("正在生成 PDF 报价单..."):
                        try:
                            pdf_bytes = _generate_quote_pdf()
                            st.download_button(
                                label="📥 点击下载报价单 PDF",
                                data=pdf_bytes,
                                file_name=f"KUKA_报价单_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                            )
                        except Exception as e:
                            st.error(f"PDF 生成失败: {e}")
                            st.info("💡 也可点击下方按钮预览 HTML 版报价单，再通过浏览器打印为 PDF")
                            html_preview = _generate_quote_html()
                            st.download_button(
                                label="📄 下载 HTML 报价单（可打印为 PDF）",
                                data=html_preview,
                                file_name=f"KUKA_报价单_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                                mime="text/html",
                                use_container_width=True,
                            )
            with col_pdf2:
                if st.button("👁️ 预览 HTML 报价单", key="preview_html_btn", use_container_width=True):
                    html_preview = _generate_quote_html()
                    st.download_button(
                        label="📥 下载 HTML 报价单",
                        data=html_preview,
                        file_name=f"KUKA_报价单_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                        mime="text/html",
                        use_container_width=True,
                    )

            st.divider()
            st.subheader("💬 对方案有不满意？告诉 AI 进行调整")
            edit_instruction = st.text_input(
                "输入修改要求",
                placeholder="例如：把客厅沙发换成更便宜的科技布款，主卧床垫预算提高到 6000",
                key="edit_instruction_input"
            )
            if st.button("🔄 重新微调方案", key="refine_btn", disabled=st.session_state.refine_in_progress):
                if not edit_instruction:
                    st.warning("请先输入修改要求")
                else:
                    st.session_state.refine_in_progress = True
                    if not api_key.startswith("sk-"):
                        st.error("❌ 请先配置 DeepSeek API Key")
                        st.session_state.refine_in_progress = False
                        st.stop()
                    # 记录微调查询
                    _log_query("refine_plan", {"instruction": edit_instruction})
                    # 从 session_state 获取候选产品数据和表单数据
                    _candidates = st.session_state.get("quote_candidates", {})
                    _form = st.session_state.get("quote_form_data", {})
                    _total_budget = _form.get("budget", 0)
                    # 安全检查：候选产品数据为空时给出明确提示
                    _has_products = any(len(v) > 0 for v in _candidates.values())
                    if not _has_products:
                        st.error("❌ 候选产品数据已丢失（可能页面已刷新）。请重新生成方案后再进行微调。")
                        st.session_state.refine_in_progress = False
                        st.stop()
                    # 计算沙发长度约束
                    _sofa_wall_cm = _form.get("sofa_wall_len", 0) * 100
                    _sofa_min = int(_sofa_wall_cm * 0.7)
                    _sofa_max = int(_sofa_wall_cm * 0.85)
                    # 生成候选产品摘要（精简版，避免超 token）
                    _candidates_text = _format_candidates_summary_compact(_candidates)
                    # 组装完整的微调 Prompt（必须包含候选产品数据，防止 AI 编造价格/型号）
                    edit_prompt = f"""你是一位顶级的家居软装与健康睡眠主理人。**严格仅从下方精选候选产品中**为客户搭配方案，不得推荐列表之外的产品。

{_candidates_text}

【预算参考】：客户总预算约 ¥{_total_budget:,}

以下是之前为客户生成的方案：
---
{st.session_state.current_report}
---

客户提出了以下修改意见：
"{edit_instruction}"

【关键规则（必须严格遵守）】：
1. 🚫 **严格仅使用上方列出的候选产品**，不得编造候选列表中不存在的产品型号、价格或规格。
2. ⚠️ **价格必须使用候选产品中标注的真实价格**，不得自行编造。任何候选产品未列出的价格均为无效。
3. 📐 **沙发长度约束**：如果涉及沙发，总长度必须在 {_sofa_min}~{_sofa_max}cm 之间。
4. 💰 **总价控制**：推荐方案总价不得超过预算 ¥{_total_budget:,}，必须在输出中逐项列出价格并累加确认。
5. 🔄 **预算调整规则**：客户要求调整预算分配时（如"主卧降到13000"），必须从候选产品中重新选择符合新预算的产品，而不是拒绝或返回空方案。候选产品中低价格区间的产品完全可以在新预算下完成搭配。
6. 输出格式与原方案一致，保留完整报告结构（尺寸分析、产品清单、价格汇总、睡眠建议等）。
7. **输出格式严格要求**：产品清单使用 HTML 卡片（类名：pd-card、pd-grid、pd-cat bed/sofa/mattress/table、pd-price、pv 红色成交价），禁止嵌入 base64 图片，其他内容用 Markdown。"""
                    try:
                        st.info("🤖 AI 正在根据您的意见调整方案...")
                        new_report = st.write_stream(stream_response(api_key, model_name, edit_prompt, f"客户修改意见：{edit_instruction}"))
                        st.session_state.current_report = new_report
                        st.session_state.setdefault("report_history", []).append(new_report)
                        st.success("✅ 方案已更新！")
                    except Exception as e:
                        st.error(f"❌ 微调失败: {e}")
                    finally:
                        st.session_state.refine_in_progress = False


# =========================================================================
# Tab 2：导购全品类速查助手（纯本地内存检索 / 毫秒级多维筛选）
# =========================================================================
with main_tab2:
    st.subheader("🔍 导购全品类速查助手（毫秒级本地多维检索）")
    st.caption("⚡ 不消耗大模型 Token | 0 秒极速响应 | 支持型号、尺寸、价格、风格、系列多维精准筛选")

    # --- 1. 初始化 Session State 状态（支持快捷按键与表单联动） ---
    if "f_kw" not in st.session_state: st.session_state.f_kw = ""
    if "f_cat" not in st.session_state: st.session_state.f_cat = "全部"
    if "f_max_p" not in st.session_state: st.session_state.f_max_p = 50000
    if "f_max_h" not in st.session_state: st.session_state.f_max_h = 0
    if "f_max_blen" not in st.session_state: st.session_state.f_max_blen = 0
    if "f_max_sofa_br" not in st.session_state: st.session_state.f_max_sofa_br = 0
    if "f_max_bw" not in st.session_state: st.session_state.f_max_bw = 0
    if "f_style" not in st.session_state: st.session_state.f_style = "全部"
    if "f_tone" not in st.session_state: st.session_state.f_tone = "全部"
    if "f_series" not in st.session_state: st.session_state.f_series = "全部"
    if "f_do_search" not in st.session_state: st.session_state.f_do_search = False
    if "f_auto_constraints" not in st.session_state: st.session_state.f_auto_constraints = []
    if "f_results" not in st.session_state: st.session_state.f_results = None
    if "f_search_ms" not in st.session_state: st.session_state.f_search_ms = 0.0

    # 系列选项（从产品索引中动态收集所有已有系列）
    _all_series = set()
    for _p in product_index.values():
        _s = _p.get("series", "")
        if _s: _all_series.add(_s)
    series_options = ["全部"] + sorted(_all_series)

    # --- 2. 快捷一键筛选按键栏 ---
    st.markdown("##### 💡 导购高频快捷按键：")
    col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
    
    if col_k1.button("📌 床头高度 < 110cm", use_container_width=True):
        st.session_state.f_cat = "床架"; st.session_state.f_max_h = 110
        st.session_state.f_max_blen = 0; st.session_state.f_max_sofa_br = 0
        st.session_state.f_max_bw = 0
        st.session_state.f_kw = ""; st.session_state.f_series = "全部"
        st.session_state.f_do_search = True; st.rerun()

    if col_k2.button("📌 床总长 < 215cm", use_container_width=True):
        st.session_state.f_cat = "床架"; st.session_state.f_max_blen = 215
        st.session_state.f_max_h = 0; st.session_state.f_max_sofa_br = 0
        st.session_state.f_max_bw = 0
        st.session_state.f_kw = ""; st.session_state.f_series = "全部"
        st.session_state.f_do_search = True; st.rerun()

    if col_k3.button("📌 沙发靠背 < 80cm", use_container_width=True):
        st.session_state.f_cat = "沙发"; st.session_state.f_max_sofa_br = 80
        st.session_state.f_max_h = 0; st.session_state.f_max_blen = 0
        st.session_state.f_max_bw = 0
        st.session_state.f_kw = ""; st.session_state.f_series = "全部"
        st.session_state.f_do_search = True; st.rerun()

    if col_k4.button("📌 价格 5000 元内", use_container_width=True):
        st.session_state.f_max_p = 5000; st.session_state.f_kw = ""
        st.session_state.f_max_sofa_br = 0; st.session_state.f_max_bw = 0
        st.session_state.f_series = "全部"; st.session_state.f_do_search = True
        st.rerun()

    if col_k5.button("🔄 重置所有筛选", use_container_width=True):
        st.session_state.f_kw = ""; st.session_state.f_cat = "全部"
        st.session_state.f_max_p = 50000; st.session_state.f_max_h = 0
        st.session_state.f_max_blen = 0; st.session_state.f_max_sofa_br = 0
        st.session_state.f_max_bw = 0
        st.session_state.f_style = "全部"; st.session_state.f_tone = "全部"
        st.session_state.f_series = "全部"
        st.session_state.f_auto_constraints = []
        st.session_state.f_do_search = False; st.session_state.f_results = None
        st.rerun()

    # --- 3. 多维组合筛选面板 ---
    with st.expander("🎛️ 多维组合筛选面板", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])
        with f_col1:
            search_kw = st.text_input(
                "🔍 搜索关键词 / 型号 / 面料 / 色号", 
                value=st.session_state.f_kw, 
                placeholder="例如: 815, 悬浮床, 奶油风, 独立弹簧, 0033", 
                key="input_search_kw"
            )
        with f_col2:
            cat_options = ["全部", "沙发", "床架", "床垫", "配套"]
            cat_idx = cat_options.index(st.session_state.f_cat) if st.session_state.f_cat in cat_options else 0
            sel_cat = st.selectbox("品类分类", cat_options, index=cat_idx, key="input_sel_cat")
        with f_col3:
            style_options = ["全部", "现代简约", "温馨奶油", "意式轻奢", "极简", "法式复古", "原木风", "中古风", "新中式", "美式"]
            style_idx = style_options.index(st.session_state.f_style) if st.session_state.f_style in style_options else 0
            sel_style = st.selectbox("风格偏好", style_options, index=style_idx, key="input_sel_style")
        with f_col4:
            tone_options = ["全部", "浅色系", "深色系"]
            tone_idx = tone_options.index(st.session_state.f_tone) if st.session_state.f_tone in tone_options else 0
            sel_tone = st.selectbox("色调归类", tone_options, index=tone_idx, key="input_sel_tone")

        f_col5, f_col6 = st.columns(2)
        with f_col5:
            sort_order = st.selectbox("结果排序方式", ["价格从低到高", "价格从高到低", "型号名称排序"], key="input_sort_order")
        with f_col6:
            series_idx = series_options.index(st.session_state.f_series) if st.session_state.f_series in series_options else 0
            sel_series = st.selectbox("产品系列", series_options, index=series_idx, key="input_sel_series")

        # --- 查询按钮 ---
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button("🔍 开始查询", type="primary", use_container_width=True):
                # 将表单值同步到 session_state
                st.session_state.f_kw = search_kw
                st.session_state.f_cat = sel_cat
                st.session_state.f_style = sel_style
                st.session_state.f_tone = sel_tone
                st.session_state.f_series = sel_series
                # 数值筛选统一通过自然语言搜索提取，面板中不手动设置
                st.session_state.f_max_p = 50000
                st.session_state.f_max_h = 0
                st.session_state.f_max_blen = 0
                st.session_state.f_max_sofa_br = 0
                st.session_state.f_max_bw = 0
                st.session_state.f_do_search = True
                st.rerun()

    # 可选：卧室产品命名结构解读
    if BED_NAMING_GUIDE:
        with st.expander("📖 查看《顾家床类产品型号与命名结构解读指南》", expanded=False):
            st.markdown(BED_NAMING_GUIDE)

    # --- 4. 纯 Python 毫秒级本地检索逻辑（仅当点击查询按钮后执行） ---
    if st.session_state.f_do_search:
        st.session_state.f_do_search = False
        t_search_start = time.time()

        # 从 session_state 读取筛选条件（确保与按钮/表单一致）
        _cat = None if st.session_state.f_cat == "全部" else st.session_state.f_cat
        _max_p = st.session_state.f_max_p if st.session_state.f_max_p < 50000 else None
        _style = None if st.session_state.f_style == "全部" else st.session_state.f_style
        _kw = st.session_state.f_kw
        _tone = st.session_state.f_tone
        _series = st.session_state.f_series
        _h_limit = st.session_state.f_max_h
        _blen_limit = st.session_state.f_max_blen
        _sofa_br_limit = st.session_state.f_max_sofa_br
        _bw_limit = st.session_state.f_max_bw
        _sofa_len_cm = 0
        _nl_color_tone = None
        _nl_color_keywords = []
        _nl_headboard_type = None
        _nl_headboard_exclude = None
        _nl_leg_style = None
        _nl_leg_min = 0
        _nl_leg_max = 0
        _sofa_seat_min = 0  # 坐垫高度下限（cm）

        # ====== 自然语言约束自动提取：从搜索文本中解析数值约束 ======
        # 当用户输入如"沙发靠背高度低于80cm的有哪些？"时，自动提取约束
        _constraint_extracted = False  # 标记是否从自然语言中提取了数值约束
        if _kw and _kw.strip():
            _kw_lower = _kw.lower()
            _kw_numbers = [int(n) for n in re.findall(r'\d+', _kw_lower) if int(n) > 0]

            # --- 品类自动识别 ---
            # 优先级：沙发 > 床垫 > 床架 > 配套
            if _cat is None:  # 仅当品类为"全部"时自动识别
                if "沙发" in _kw_lower:
                    _cat = "沙发"
                elif "床垫" in _kw_lower:
                    _cat = "床垫"
                elif any(kw in _kw_lower for kw in ["床架", "床长", "床总长", "床头", "床的长度", "床的", "床头宽度", "床头宽", "床宽度", "床"]):
                    _cat = "床架"
                elif "配套" in _kw_lower or "茶几" in _kw_lower or "餐桌" in _kw_lower:
                    _cat = "配套"

            # --- 0) 价格约束（元/万元/以内/以下/不超过/预算） ---
            if any(kw in _kw_lower for kw in ["元以内", "元以下", "元不超过", "元及以下", "万元以内", "万元以下", "万以内", "万以下", "预算", "价格", "块钱以内", "块以内", "元左右", "万元左右", "万左右", "左右"]):
                # 提取价格数值
                price_val = None
                # 万元模式：X万/Y万元
                wan_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:万|万元)\s*(?:以内|以下|不超过|及以下|左右)?', _kw_lower)
                if wan_match:
                    price_val = int(float(wan_match.group(1)) * 10000)
                else:
                    # 元模式：X元/X块
                    yuan_match = re.search(r'(\d+)\s*(?:元|块|块钱)\s*(?:以内|以下|不超过|及以下|左右)?', _kw_lower)
                    if yuan_match:
                        price_val = int(yuan_match.group(1))
                    else:
                        # "以内/以下/左右"前面的数字
                        for pat in [r'(\d+)\s*(?:元|块|块钱)?\s*(?:以内|以下|不超过|及以下|左右)',
                                    r'(?:低于|小于|不超过|不大于|预算)\s*(\d+)\s*(?:元|块|万|万元)?']:
                            m = re.search(pat, _kw_lower)
                            if m:
                                price_val = int(m.group(1))
                                # 如果是万级数字但没单位，且数值较小（<100），可能是万
                                if price_val < 100 and any(kw in _kw_lower for kw in ["万", "万元"]):
                                    price_val = price_val * 10000
                                break
                if price_val and price_val > 100:  # 合理价格范围下限
                    if "左右" in _kw_lower:
                        _max_p = int(price_val * 1.1)  # "X左右"允许价格上浮约10%
                    else:
                        _max_p = price_val
                    _constraint_extracted = True

            # --- 0b) 沙发长度/尺寸约束（米/长/总长/长度/尺寸/大小） ---
            # 仅当品类是沙发或查询中包含沙发相关词时提取
            _sofa_len_cm = 0
            if _cat == "沙发" or any(kw in _kw_lower for kw in ["沙发", "客厅"]):
                # 米单位：X米/X.X米
                mi_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:米|m)\s*(?:的|长|沙发|尺寸|大小|左右|以内)?', _kw_lower)
                if mi_match:
                    meters = float(mi_match.group(1))
                    if 1.0 <= meters <= 5.0:  # 合理沙发长度范围
                        _sofa_len_cm = int(meters * 100)
                        _constraint_extracted = True
                else:
                    # 厘米单位
                    cm_match = re.search(r'(\d+)\s*(?:cm|厘米)\s*(?:的|长|沙发|尺寸|大小|左右|以内)?', _kw_lower)
                    if cm_match:
                        val = int(cm_match.group(1))
                        if 100 <= val <= 500:
                            _sofa_len_cm = val
                            _constraint_extracted = True
                    else:
                        # "长度/长/总长"前面或后面的数字
                        if any(kw in _kw_lower for kw in ["长度", "总长", "长"]):
                            for pat in [r'(?:长度|总长|长)\s*(?:低于|小于|不超过|以内)?\s*(\d+)',
                                        r'(\d+)\s*(?:cm|厘米)?\s*(?:长度|总长|长)']:
                                m = re.search(pat, _kw_lower)
                                if m:
                                    val = int(m.group(1))
                                    if 100 <= val <= 500:
                                        _sofa_len_cm = val
                                        _constraint_extracted = True
                                        break

            # --- 1) 沙发靠背高度约束（靠背高度/沙发靠背/靠背高） ---
            if any(kw in _kw_lower for kw in ["靠背高度", "沙发靠背", "靠背高"]):
                for pat in [r'(?:低于|小于|<|≤|不大于|不超过|以内)\s*(\d+)',
                            r'(\d+)\s*(?:cm|厘米)\s*(?:以下|以内|及以下)',
                            r'(\d+)\s*(?:cm|厘米)?\s*(?:以下|以内|及以下)']:
                    m = re.search(pat, _kw_lower)
                    if m:
                        val = int(m.group(1))
                        if 20 <= val <= 150:
                            _sofa_br_limit = val
                            _constraint_extracted = True
                            break
                # 如果没找到"低于"类关键词，取第一个合理数字作为上限
                if _sofa_br_limit == 0 and _kw_numbers:
                    for n in _kw_numbers:
                        if 20 <= n <= 150:
                            _sofa_br_limit = n
                            _constraint_extracted = True
                            break

            # --- 1b) 沙发坐垫高度约束（坐垫高度，取"大于/高于/超过"下限） ---
            if "坐垫高度" in _kw_lower:
                for pat in [r'(?:大于|高于|超过|不小于|≥|>|不低于)\s*(\d+)',
                            r'(\d+)\s*(?:cm|厘米)?\s*(?:以上|及以上|起|以上)']:
                    m = re.search(pat, _kw_lower)
                    if m:
                        val = int(m.group(1))
                        if 20 <= val <= 70:
                            _sofa_seat_min = val
                            _constraint_extracted = True
                            break
                # 若没带"大于/以上"等关键词，但查询含坐垫高度和数字，取上限作为下限
                if _sofa_seat_min == 0 and _kw_numbers:
                    for n in _kw_numbers:
                        if 20 <= n <= 70:
                            _sofa_seat_min = n
                            _constraint_extracted = True
                            break

            # --- 2) 床头高度约束（床头高度/床头高/头高） ---
            if any(kw in _kw_lower for kw in ["床头高度", "床头高", "头高"]):
                for pat in [r'(?:低于|小于|<|≤|不大于|不超过|以内)\s*(\d+)',
                            r'(\d+)\s*(?:cm|厘米)\s*(?:以下|以内|及以下)',
                            r'(\d+)\s*(?:cm|厘米)?\s*(?:以下|以内|及以下)']:
                    m = re.search(pat, _kw_lower)
                    if m:
                        val = int(m.group(1))
                        if 20 <= val <= 200:
                            _h_limit = val
                            _constraint_extracted = True
                            break
                if _h_limit == 0 and _kw_numbers:
                    for n in _kw_numbers:
                        if 20 <= n <= 200:
                            _h_limit = n
                            _constraint_extracted = True
                            break

            # --- 3) 床总长度约束（床长/床长度/总长/床总长） ---
            if any(kw in _kw_lower for kw in ["床长", "床长度", "总长", "床总长"]):
                for pat in [r'(?:低于|小于|<|≤|不大于|不超过|以内)\s*(\d+)',
                            r'(\d+)\s*(?:cm|厘米)\s*(?:以下|以内|及以下)',
                            r'(\d+)\s*(?:cm|厘米)?\s*(?:以下|以内|及以下)']:
                    m = re.search(pat, _kw_lower)
                    if m:
                        val = int(m.group(1))
                        if 100 <= val <= 260:
                            _blen_limit = val
                            _constraint_extracted = True
                            break
                if _blen_limit == 0 and _kw_numbers:
                    for n in _kw_numbers:
                        if 100 <= n <= 260:
                            _blen_limit = n
                            _constraint_extracted = True
                            break

            # --- 4) 床头宽度约束（床头宽度/床头宽/宽度/床宽） ---
            if any(kw in _kw_lower for kw in ["床头宽度", "床头宽", "床宽度", "床的宽度"]):
                for pat in [r'(?:低于|小于|<|≤|不大于|不超过|以内)\s*(\d+)',
                            r'(\d+)\s*(?:cm|厘米)\s*(?:以下|以内|及以下)',
                            r'(\d+)\s*(?:cm|厘米)?\s*(?:以下|以内|及以下)']:
                    m = re.search(pat, _kw_lower)
                    if m:
                        val = int(m.group(1))
                        if 50 <= val <= 300:
                            _bw_limit = val
                            _constraint_extracted = True
                            break
                if _bw_limit == 0 and _kw_numbers:
                    for n in _kw_numbers:
                        if 50 <= n <= 300:
                            _bw_limit = n
                            _constraint_extracted = True
                            break

            # --- 5) 颜色/色系约束（深色/浅色/具体色名） ---
            _nl_color_tone = None  # "浅色系" 或 "深色系"
            _nl_color_keywords = []  # 具体颜色关键词列表
            # 先判断色系
            if any(kw in _kw_lower for kw in ["浅色", "浅色系", "亮色", "亮色系", "淡色", "白色", "米白", "奶白"]):
                _nl_color_tone = "浅色系"
                _constraint_extracted = True
            elif any(kw in _kw_lower for kw in ["深色", "深色系", "暗色", "暗色系", "黑色", "深灰", "深棕"]):
                _nl_color_tone = "深色系"
                _constraint_extracted = True
            # 提取具体颜色关键词（用于更精确匹配）
            color_keywords_list = ["黑", "白", "灰", "棕", "咖", "红", "蓝", "绿", "紫", "橙", "粉", "黄", "米色", "奶白", "奶油", "深灰", "浅灰"]
            for ck in color_keywords_list:
                if ck in _kw_lower:
                    _nl_color_keywords.append(ck)
                    _constraint_extracted = True

            # --- 6) 床头靠包类型约束（上下分段/左右分段/整体无分段/无床头） ---
            _nl_headboard_type = None  # 要匹配的靠包类型
            _nl_headboard_exclude = None  # 要排除的靠包类型
            if _cat == "床架" or "床" in _kw_lower or "床头" in _kw_lower or "靠包" in _kw_lower:
                if any(kw in _kw_lower for kw in ["上下分段", "只上下分段", "仅上下分段"]):
                    _nl_headboard_type = "仅上下分段式"
                    _constraint_extracted = True
                elif any(kw in _kw_lower for kw in ["左右分段", "只左右分段", "仅左右分段"]):
                    _nl_headboard_type = "仅左右分段式"
                    _constraint_extracted = True
                elif "整体" in _kw_lower and "分段" in _kw_lower:
                    _nl_headboard_type = "整体无分段"
                    _constraint_extracted = True
                # 排除型约束：不要左右分段
                if any(kw in _kw_lower for kw in ["不要左右分段", "不要左右分", "没有左右分段", "非左右分段"]):
                    _nl_headboard_exclude = "仅左右分段式"
                    _constraint_extracted = True
                if any(kw in _kw_lower for kw in ["不要上下分段", "不要上下分", "没有上下分段", "非上下分段"]):
                    _nl_headboard_exclude = "仅上下分段式" if not _nl_headboard_exclude else _nl_headboard_exclude
                    _constraint_extracted = True

            # --- 7) 床脚款式约束（高脚/矮脚/床脚高度） ---
            _nl_leg_style = None  # "高脚" 或 "矮脚"
            _nl_leg_min = 0  # 床脚最小高度
            _nl_leg_max = 0  # 床脚最大高度
            if any(kw in _kw_lower for kw in ["高脚", "高腿", "高床脚", "高床脚"]):
                _nl_leg_style = "高脚"
                _nl_leg_min = 15  # 15cm以上算高脚
                _constraint_extracted = True
            elif any(kw in _kw_lower for kw in ["矮脚", "矮腿", "矮床脚", "低脚", "低床脚"]):
                _nl_leg_style = "矮脚"
                _nl_leg_max = 14  # 14cm以下算矮脚
                _constraint_extracted = True
            # 带具体数值的床脚高度
            if "床脚" in _kw_lower or "床腿" in _kw_lower or "脚高" in _kw_lower:
                leg_match = re.search(r'(\d+)\s*(?:cm|厘米)?\s*(?:的)?(?:床脚|床腿|脚高)', _kw_lower)
                if not leg_match:
                    leg_match = re.search(r'(?:床脚|床腿|脚高).*?(\d+)\s*(?:cm|厘米)?', _kw_lower)
                if leg_match:
                    lval = int(leg_match.group(1))
                    if 5 <= lval <= 50:
                        _nl_leg_max = lval
                        _constraint_extracted = True

        # 如果从自然语言中提取了约束，将关键词简化为品类名
        # 避免完整中文句子（如"床头宽度小于150cm的床有哪些"）传入 filter_candidates 导致匹配失败
        if _constraint_extracted and _kw:
            # 检查是否包含自然语言特征（中文句式，非简单关键词）
            if any(pat in _kw for pat in ["有哪些", "的有哪些", "哪些", "低于", "小于", "不超过", "以内"]):
                _kw = _cat if _cat else ""

        # 过滤出符合条件的候选产品（fallback=False 只返回精确匹配，不补齐）
        matched_products, _ = filter_candidates(
            product_index,
            category=_cat,
            max_price=_max_p,
            sofa_length=_sofa_len_cm if _sofa_len_cm > 0 else None,
            style=_style,
            keywords=_kw,
            min_candidates=99999,
            fallback=False
        )

        # 二级精准属性过滤（色调、系列、床头高、床长、沙发靠背高）
        final_results = []
        for p in matched_products:
            if _tone != "全部" and _tone not in p.get("color_tones", [p.get("color_tone", "")]):
                continue
            if _series != "全部" and p.get("series", "") != _series:
                continue
            if _h_limit > 0:
                h_height = p.get("bed_head_height", 0)
                if h_height > 0 and h_height > _h_limit:
                    continue
            if _blen_limit > 0:
                b_len = p.get("bed_total_length", 0)
                if b_len > 0 and b_len > _blen_limit:
                    continue
            if _sofa_br_limit > 0:
                sofa_dims = p.get("sofa_dimensions", {})
                br = sofa_dims.get("靠背高度", 0)
                if br > 0 and br > _sofa_br_limit:
                    continue
            if _sofa_seat_min > 0:
                sofa_dims = p.get("sofa_dimensions", {})
                seat = sofa_dims.get("坐垫高度", 0)
                if seat > 0 and seat < _sofa_seat_min:
                    continue
            if _bw_limit > 0:
                bw = p.get("bed_head_width", 0)
                if bw > 0 and bw > _bw_limit:
                    continue
            # 颜色/色系过滤
            if _nl_color_tone and _nl_color_tone not in p.get("color_tones", [p.get("color_tone", "")]):
                continue
            # 具体颜色关键词过滤（产品颜色名中需包含关键词之一）
            if _nl_color_keywords:
                p_colors = p.get("colors", [])
                color_match = False
                for pc in p_colors:
                    pc_lower = pc.lower()
                    if any(ck in pc_lower for ck in _nl_color_keywords):
                        color_match = True
                        break
                if not color_match and p_colors:
                    continue
            # 靠包类型过滤
            if _nl_headboard_type and p.get("headboard_type") != _nl_headboard_type:
                continue
            if _nl_headboard_exclude and p.get("headboard_type") == _nl_headboard_exclude:
                continue
            # 床脚高度/款式过滤
            if _nl_leg_min > 0:
                leg_h = p.get("bed_leg_height", 0)
                if leg_h > 0 and leg_h < _nl_leg_min:
                    continue
            if _nl_leg_max > 0:
                leg_h = p.get("bed_leg_height", 0)
                if leg_h > 0 and leg_h > _nl_leg_max:
                    continue
            final_results.append(p)

        # 排序
        _sort = sort_order  # 使用当前表单的排序方式
        if _sort == "价格从低到高":
            final_results.sort(key=lambda x: x.get("min_price", 0))
        elif _sort == "价格从高到低":
            final_results.sort(key=lambda x: x.get("min_price", 0), reverse=True)
        elif _sort == "型号名称排序":
            final_results.sort(key=lambda x: x.get("model", ""))

        t_search_end = time.time()
        st.session_state.f_search_ms = (t_search_end - t_search_start) * 1000
        st.session_state.f_results = final_results

        # 持久化自然语言约束提取信息，供结果显示使用
        _auto_constraints = []
        if st.session_state.f_kw and st.session_state.f_kw.strip():
            _orig_cat = None if st.session_state.f_cat == "全部" else st.session_state.f_cat
            if _cat != _orig_cat:
                _auto_constraints.append(f"品类: {_cat}")
            if _max_p is not None and _max_p != st.session_state.f_max_p and _max_p > 0 and _max_p < 50000:
                _auto_constraints.append(f"价格 ≤ ¥{_max_p:,}")
            if _sofa_len_cm > 0:
                _auto_constraints.append(f"沙发长度 ≈ {_sofa_len_cm}cm（{_sofa_len_cm/100:.1f}米）")
            if _sofa_br_limit != st.session_state.f_max_sofa_br and _sofa_br_limit > 0:
                _auto_constraints.append(f"沙发靠背高度 ≤ {_sofa_br_limit}cm")
            if _sofa_seat_min > 0:
                _auto_constraints.append(f"坐垫高度 ≥ {_sofa_seat_min}cm")
            if _h_limit != st.session_state.f_max_h and _h_limit > 0:
                _auto_constraints.append(f"床头高度 ≤ {_h_limit}cm")
            if _blen_limit != st.session_state.f_max_blen and _blen_limit > 0:
                _auto_constraints.append(f"床总长度 ≤ {_blen_limit}cm")
            if _bw_limit != st.session_state.f_max_bw and _bw_limit > 0:
                _auto_constraints.append(f"床头宽度 ≤ {_bw_limit}cm")
            if _nl_color_tone:
                _auto_constraints.append(f"色系: {_nl_color_tone}")
            if _nl_color_keywords:
                _auto_constraints.append(f"颜色: {'/'.join(_nl_color_keywords)}")
            if _nl_headboard_type:
                _auto_constraints.append(f"靠包: {_nl_headboard_type}")
            if _nl_headboard_exclude:
                _auto_constraints.append(f"排除靠包: {_nl_headboard_exclude}")
            if _nl_leg_style:
                _auto_constraints.append(f"床脚款式: {_nl_leg_style}")
            if _nl_leg_max > 0 and not _nl_leg_style:
                _auto_constraints.append(f"床脚高度 ≤ {_nl_leg_max}cm")
        st.session_state.f_auto_constraints = _auto_constraints

        # 记录导购查询日志
        if _kw:
            _log_query("fast_local_search", {"kw": _kw, "cat": st.session_state.f_cat, "count": len(final_results)})

    # --- 5. 结果展示（精美卡片网格） ---
    if st.session_state.f_results is not None:
        final_results = st.session_state.f_results
        search_ms = st.session_state.f_search_ms

        st.markdown("---")
        st.markdown(f"### 📦 检索结果 (⚡ 共找到 **{len(final_results)}** 款产品，耗时 **{search_ms:.2f}** 毫秒)")

        # 显示自然语言约束自动提取反馈
        if st.session_state.get("f_auto_constraints"):
            st.info(f"🔍 从搜索文本自动识别约束: {' · '.join(st.session_state.f_auto_constraints)}")

        if not final_results:
            st.warning("⚠️ 没有找到符合条件的产品，请尝试调整筛选条件。")
        else:
            # 卡片网格：每行3列，使用 Streamlit columns + HTML 卡片内容
            cols_per_row = 3
            for row_idx in range(0, len(final_results), cols_per_row):
                row_products = final_results[row_idx:row_idx + cols_per_row]
                cols = st.columns(cols_per_row)
                
                for col_idx, p in enumerate(row_products):
                    with cols[col_idx]:
                        model = p.get("model", "")
                        name = p.get("name", "")
                        cat = p.get("category", "")
                        min_p = p.get("min_price", 0)
                        max_p = p.get("max_price", 0)
                        series = p.get("series", "")
                        tagline = p.get("tagline", "")
                        features = p.get("features", [])
                        good_looks = p.get("good_looks", "")
                        good_comfort = p.get("good_comfort", "")
                        good_quality = p.get("good_quality", "")
                        good_looks_text = p.get("good_looks_text", "")
                        good_comfort_text = p.get("good_comfort_text", "")
                        good_quality_text = p.get("good_quality_text", "")
                        colors = p.get("colors", [])
                        color_codes = p.get("color_codes", [])
                        price_rows = p.get("price_rows", [])
                        
                        # 品类 CSS 类
                        cat_class = {"沙发": "sofa", "床架": "bed", "床垫": "mattress", "配套": "table"}.get(cat, "bed")
                        series_display = series if series else "标准系列"
                        
                        # 价格显示
                        if min_p == 0 and max_p == 0:
                            price_main = '<span class="pl">价格</span><span class="pv">待询</span>'
                            price_range_html = ''
                        elif min_p == max_p:
                            price_main = f'<span class="pl">成交价</span><span class="pv">¥{min_p:,}</span>'
                            price_range_html = ''
                        else:
                            price_main = f'<span class="pl">成交价</span><span class="pv">¥{min_p:,} <small>起</small></span>'
                            price_range_html = f'<div class="pd-price-range">价格区间：<strong>¥{min_p:,} ~ ¥{max_p:,}</strong>（共{len(price_rows)}个规格）</div>'
                        
                        # 查找匹配图片
                        matching_img_dict = None
                        model_upper = model.upper()
                        for fk, idict in images_db.items():
                            if model_upper in fk.upper() or fk.upper() in model_upper:
                                matching_img_dict = idict
                                break
                        
                        # ===== 组装卡片 HTML 内容 =====
                        html_parts = []
                        html_parts.append('<div class="pd-card-wrapper">')
                        html_parts.append('<div class="pd-card" style="border:none;box-shadow:none;margin:0;">')
                        
                        # 头部
                        html_parts.append('<div class="pd-head">')
                        html_parts.append(f'<span class="pd-cat {cat_class}">{cat}</span>')
                        html_parts.append(f'<span class="pd-model">{model}</span>')
                        html_parts.append(f'<span class="pd-name">{name}</span>')
                        html_parts.append(f'<span class="pd-series">{series_display}</span>')
                        html_parts.append('</div>')
                        
                        # 价格条 + 价格区间
                        html_parts.append('<div class="pd-price">')
                        html_parts.append(price_main)
                        html_parts.append(price_range_html)
                        html_parts.append('</div>')
                        
                        # 正文开始
                        html_parts.append('<div class="pd-body">')
                        
                        # 一句话价值塑造
                        if tagline:
                            html_parts.append(f'<div class="pd-tagline">💬 {tagline}</div>')
                        elif cat == "床垫" and p.get("csp_oneliner"):
                            html_parts.append(f'<div class="pd-tagline">💬 {p["csp_oneliner"]}</div>')
                        
                        # ⭐ 核心卖点（放在规格前面）
                        if features:
                            html_parts.append('<div class="pd-section-title">⭐ 核心卖点</div>')
                            # 床垫/床架：显示结构化分章节卖点（完整显示不截断）
                            if cat in ("床垫", "床架") and p.get("core_selling_points"):
                                csp = p["core_selling_points"]
                                for section in csp:
                                    html_parts.append(f'<div style="font-weight:600;color:#333;margin:6px 0 3px;font-size:13px;">{section["title"]}</div>')
                                    html_parts.append('<ul class="pd-features" style="margin-top:2px;">')
                                    for item in section["items"]:
                                        # 去除 ** 标记，保留内容
                                        clean_item = re.sub(r'\*\*([^*]+)\*\*', r'\1', item)
                                        html_parts.append(f'<li style="font-size:12px;line-height:1.5;">{clean_item}</li>')
                                    html_parts.append('</ul>')
                            else:
                                # 沙发/配套：简单列表，最多3条，超长截断为32字
                                html_parts.append('<ul class="pd-features">')
                                for ft in features[:3]:
                                    ft_short = ft[:32] + "…" if len(ft) > 32 else ft
                                    html_parts.append(f'<li>{ft_short}</li>')
                                html_parts.append('</ul>')
                        
                        # 📋 规格与成交价明细表（沙发显示组合规格，其他品类显示全部）
                        display_price_rows = p.get("combo_price_rows", []) if cat == "沙发" and p.get("combo_price_rows") else price_rows
                        if display_price_rows:
                            html_parts.append('<div class="pd-section-title">📋 规格与成交价</div>')
                            html_parts.append('<table class="pd-price-table"><thead><tr><th>规格</th><th>尺寸</th><th style="text-align:right">成交价</th></tr></thead><tbody>')
                            
                            # 前4条显示
                            for pr in display_price_rows[:4]:
                                parts = pr.split(" → ", 1)
                                if len(parts) == 2:
                                    spec = parts[0]
                                    rest = parts[1]
                                    price_match = re.search(r'(.*), (¥[\d,]+)', rest)
                                    if price_match:
                                        size = price_match.group(1)
                                        price = price_match.group(2)
                                        html_parts.append(f'<tr><td>{spec}</td><td>{size}</td><td class="pd-td-price">{price}</td></tr>')
                                    else:
                                        html_parts.append(f'<tr><td>{spec}</td><td>{rest}</td><td class="pd-td-price">-</td></tr>')
                                else:
                                    html_parts.append(f'<tr><td colspan="3">{pr}</td></tr>')
                            
                            # 剩余规格放下拉里
                            if len(display_price_rows) > 4:
                                html_parts.append('</tbody></table>')
                                html_parts.append('<details class="pd-more-specs"><summary></summary>')
                                html_parts.append('<table class="pd-price-table" style="margin-top:0;"><tbody>')
                                for pr in display_price_rows[4:]:
                                    parts = pr.split(" → ", 1)
                                    if len(parts) == 2:
                                        spec = parts[0]
                                        rest = parts[1]
                                        price_match = re.search(r'(.*), (¥[\d,]+)', rest)
                                        if price_match:
                                            size = price_match.group(1)
                                            price = price_match.group(2)
                                            html_parts.append(f'<tr><td>{spec}</td><td>{size}</td><td class="pd-td-price">{price}</td></tr>')
                                        else:
                                            html_parts.append(f'<tr><td>{spec}</td><td>{rest}</td><td class="pd-td-price">-</td></tr>')
                                    else:
                                        html_parts.append(f'<tr><td colspan="3">{pr}</td></tr>')
                                html_parts.append('</tbody></table></details>')
                            else:
                                html_parts.append('</tbody></table>')
                            
                            # 沙发：下方提示有单组件规格
                            if cat == "沙发" and p.get("single_price_rows"):
                                single_count = len(p["single_price_rows"])
                                html_parts.append(f'<div style="font-size:10px;color:#94a3b8;margin-top:2px;">💡 另有 {single_count} 款单组件规格，可自由组合</div>')
                        
                        # 📐 产品信息
                        html_parts.append('<div class="pd-section-title">📐 产品信息</div>')
                        html_parts.append('<div class="pd-info">')
                        
                        if cat == "床架":
                            dims_items = []
                            if p.get("bed_head_height"):
                                dims_items.append(f'<span class="k">床头高</span> <span class="v">{p["bed_head_height"]}cm</span>')
                            if p.get("bed_total_length"):
                                dims_items.append(f'<span class="k">总长</span> <span class="v">{p["bed_total_length"]}cm</span>')
                            if p.get("bed_head_width"):
                                dims_items.append(f'<span class="k">床宽</span> <span class="v">{p["bed_head_width"]}cm</span>')
                            if dims_items:
                                html_parts.append("<div>" + " ｜ ".join(dims_items) + "</div>")
                            
                            extra_items = []
                            if p.get("bed_frame_height"):
                                extra_items.append(f'<span class="k">床身高</span> <span class="v">{p["bed_frame_height"]}cm</span>')
                            if p.get("bed_leg_height"):
                                extra_items.append(f'<span class="k">床脚高</span> <span class="v">{p["bed_leg_height"]}cm</span>')
                            if p.get("mattress_thickness"):
                                extra_items.append(f'<span class="k">适配床垫</span> <span class="v">{p["mattress_thickness"]}</span>')
                            if p.get("headboard_type"):
                                extra_items.append(f'<span class="k">靠包</span> <span class="v">{p["headboard_type"]}</span>')
                            if extra_items:
                                html_parts.append("<div>" + " ｜ ".join(extra_items) + "</div>")
                            # 设计风格 + 面料 + 床架款式
                            info_items = []
                            if p.get("design_style"):
                                info_items.append(f'<span class="k">设计风格</span> <span class="v">{p["design_style"]}</span>')
                            if p.get("fabric_text"):
                                fab_short = p["fabric_text"][:20] + "…" if len(p["fabric_text"]) > 20 else p["fabric_text"]
                                info_items.append(f'<span class="k">面料</span> <span class="v" title="{p["fabric_text"]}">{fab_short}</span>')
                            if p.get("bed_frame_style"):
                                info_items.append(f'<span class="k">床架款式</span> <span class="v">{p["bed_frame_style"]}</span>')
                            if info_items:
                                html_parts.append("<div>" + " ｜ ".join(info_items) + "</div>")
                        
                        elif cat == "沙发":
                            sofa_dims = p.get("sofa_dimensions", {})
                            if sofa_dims:
                                # 显示所有尺寸（靠背高度、坐深、坐垫高度等）
                                dim_items = []
                                for k, v in sofa_dims.items():
                                    dim_items.append(f'<span class="k">{k}</span> <span class="v">{v}cm</span>')
                                # 分两行显示
                                mid = (len(dim_items) + 1) // 2
                                html_parts.append("<div>" + " ｜ ".join(dim_items[:mid]) + "</div>")
                                if len(dim_items) > mid:
                                    html_parts.append("<div>" + " ｜ ".join(dim_items[mid:]) + "</div>")
                            if p.get("design_style"):
                                html_parts.append(f'<div><span class="k">风格</span> <span class="v">{p["design_style"]}</span></div>')
                            
                            # 沙发组件尺寸（单规格尺寸），超出部分可点击展开
                            sofa_comps = p.get("sofa_components", {})
                            if sofa_comps:
                                comps_list = list(sofa_comps.items())
                                comp_html = '<div style="margin-top:6px;"><span class="k" style="display:block;margin-bottom:2px;">组件尺寸</span>'
                                # 显示前5个
                                for ck, cv in comps_list[:5]:
                                    comp_html += f'<span class="pd-spec-tag">{ck}: {cv}cm</span>'
                                # 超出部分用 details 展开
                                if len(comps_list) > 5:
                                    more_count = len(comps_list) - 5
                                    comp_html += '<details class="pd-comp-more" style="display:inline-block;vertical-align:top;">'
                                    comp_html += f'<summary class="pd-spec-tag" style="cursor:pointer;list-style:none;">+{more_count}</summary>'
                                    comp_html += '<div style="margin-top:4px;">'
                                    for ck, cv in comps_list[5:]:
                                        comp_html += f'<span class="pd-spec-tag">{ck}: {cv}cm</span>'
                                    comp_html += '</div></details>'
                                comp_html += '</div>'
                                html_parts.append(comp_html)
                            
                            # 面料 / 填充（更详细显示，完整内容放查看更多）
                            fabric_text = p.get("fabric_text", "")
                            filling_text = p.get("filling_text", "")
                            if fabric_text or filling_text:
                                # 面料：分行显示更清晰
                                if fabric_text:
                                    fab_lines = [l.strip() for l in fabric_text.split('\n') if l.strip()]
                                    if fab_lines:
                                        fab_html = '<div style="margin-top:4px;"><span class="k" style="display:block;margin-bottom:2px;">面料</span>'
                                        for fl in fab_lines[:2]:
                                            clean_fl = re.sub(r'\*\*([^*]+)\*\*', r'\1', fl)
                                            fab_html += f'<div style="padding:1px 0;color:#555;font-size:12px;">{clean_fl}</div>'
                                        fab_html += '</div>'
                                        html_parts.append(fab_html)
                                # 填充：分行显示更清晰
                                if filling_text:
                                    fill_lines = [l.strip() for l in filling_text.split('\n') if l.strip()]
                                    if fill_lines:
                                        fill_html = '<div style="margin-top:4px;"><span class="k" style="display:block;margin-bottom:2px;">填充</span>'
                                        for fl in fill_lines[:2]:
                                            clean_fl = re.sub(r'\*\*([^*]+)\*\*', r'\1', fl)
                                            fill_html += f'<div style="padding:1px 0;color:#555;font-size:12px;">{clean_fl}</div>'
                                        fill_html += '</div>'
                                        html_parts.append(fill_html)
                        
                        elif cat == "床垫":
                            # 睡感等级（突出显示）
                            if p.get("sleep_level"):
                                html_parts.append(f'<div><span class="k">睡感等级</span> <span class="v">{p["sleep_level"]}</span></div>')
                            # 床垫高度
                            if p.get("mattress_height"):
                                html_parts.append(f'<div><span class="k">床垫高度</span> <span class="v">{p["mattress_height"]}</span></div>')
                            # 产品配置（分行显示，不截断）
                            config_lines = p.get("product_config_lines", [])
                            if config_lines:
                                cfg_html = '<div style="margin-top:4px;"><span class="k" style="display:block;margin-bottom:2px;">产品配置</span>'
                                for cl in config_lines:
                                    cfg_html += f'<div style="padding:2px 0;color:#555;">{cl}</div>'
                                cfg_html += '</div>'
                                html_parts.append(cfg_html)
                            elif p.get("product_config"):
                                html_parts.append(f'<div><span class="k">配置</span> <span class="v">{p["product_config"]}</span></div>')
                            # 材质
                            if p.get("material"):
                                mat_short = p["material"][:40] + "…" if len(p["material"]) > 40 else p["material"]
                                html_parts.append(f'<div><span class="k">材质</span> <span class="v" title="{p["material"]}">{mat_short}</span></div>')
                            # 床垫面料层/填充层信息
                            fabric_text = p.get("fabric_text", "")
                            filling_text = p.get("filling_text", "")
                            if fabric_text:
                                fab_short = fabric_text[:28] + "…" if len(fabric_text) > 28 else fabric_text
                                html_parts.append(f'<div><span class="k">面料层</span> <span class="v" title="{fabric_text}">{fab_short}</span></div>')
                            if filling_text:
                                fill_short = filling_text[:28] + "…" if len(filling_text) > 28 else filling_text
                                html_parts.append(f'<div><span class="k">填充层</span> <span class="v" title="{filling_text}">{fill_short}</span></div>')
                        
                        elif cat == "配套":
                            if p.get("material"):
                                html_parts.append(f'<div><span class="k">材质</span> <span class="v">{p["material"]}</span></div>')
                            if p.get("design_style"):
                                html_parts.append(f'<div><span class="k">风格</span> <span class="v">{p["design_style"]}</span></div>')
                        
                        # 配色（含色号）
                        if colors or color_codes:
                            color_html = '<div style="margin-top:4px;line-height:1.8;">'
                            if color_codes:
                                # 有色号时，显示色号+颜色名
                                for i, code in enumerate(color_codes[:4]):
                                    cn = colors[i] if i < len(colors) else ""
                                    # 从颜色名中提取纯中文名（去掉材质括号）
                                    cn_clean = re.sub(r'\(.*\)', '', cn).strip()
                                    color_html += f'<span class="pd-color-chip">{code}<span class="cn">{cn_clean}</span></span>'
                                if len(color_codes) > 4:
                                    color_html += f'<span class="pd-color-chip">+{len(color_codes)-4}</span>'
                            else:
                                color_str = "、".join(colors[:4])
                                if len(colors) > 4:
                                    color_str += f" 等{len(colors)}色"
                                color_html += f'<span class="k">配色</span> <span class="v">{color_str}</span>'
                            color_html += '</div>'
                            html_parts.append(color_html)
                        
                        html_parts.append('</div>')  # pd-info
                        
                        # 三好标签 + 查看更多信息（下拉）
                        has_any_good = good_looks or good_comfort or good_quality
                        has_extra_info = p.get("fabric_text") or p.get("filling_text") or p.get("frame_text") or p.get("product_config") or (cat == "床垫" and (p.get("product_story") or p.get("material"))) or (cat == "床架" and (p.get("nightstand_info") or p.get("bed_frame_style") or p.get("design_style") or p.get("bed_leg_height")))
                        if has_any_good or has_extra_info:
                            html_parts.append('<div class="pd-section-title">🌟 三好品质</div>')
                            html_parts.append('<div class="pd-goods">')
                            if good_looks:
                                html_parts.append('<span class="pd-good-tag g1">🎨 好看</span>')
                            if good_comfort:
                                html_parts.append('<span class="pd-good-tag g2">🛋️ 好舒适</span>')
                            if good_quality:
                                html_parts.append('<span class="pd-good-tag g3">🔧 好品质</span>')
                            html_parts.append('</div>')
                            
                            # 查看更多信息下拉（三好完整内容 + 面料/填充/功能架详情）
                            more_content_parts = []
                            
                            # 三好完整内容
                            if good_looks_text:
                                more_content_parts.append(f'<div class="gc-title">🎨 好看</div><div style="margin-bottom:8px;line-height:1.6;">{good_looks_text}</div>')
                            if good_comfort_text:
                                more_content_parts.append(f'<div class="gc-title">🛋️ 好舒适</div><div style="margin-bottom:8px;line-height:1.6;">{good_comfort_text}</div>')
                            if good_quality_text:
                                more_content_parts.append(f'<div class="gc-title">🔧 好品质</div><div style="margin-bottom:8px;line-height:1.6;">{good_quality_text}</div>')
                            
                            # 面料详情
                            if p.get("fabric_text"):
                                more_content_parts.append(f'<div class="gc-title">🧵 面料</div><div style="margin-bottom:8px;line-height:1.6;">{p["fabric_text"]}</div>')
                            
                            # 填充详情
                            if p.get("filling_text"):
                                more_content_parts.append(f'<div class="gc-title">☁️ 填充</div><div style="margin-bottom:8px;line-height:1.6;">{p["filling_text"]}</div>')
                            
                            # 功能架详情（沙发）
                            if p.get("frame_text"):
                                more_content_parts.append(f'<div class="gc-title">⚙️ 功能架</div><div style="margin-bottom:8px;line-height:1.6;">{p["frame_text"]}</div>')
                            
                            # 床垫专属：产品故事（上面卡片未展示的内容）
                            if cat == "床垫":
                                story = p.get("product_story", "")
                                if story:
                                    more_content_parts.append(f'<div class="gc-title">📖 产品故事</div><div style="margin-bottom:8px;line-height:1.6;">{story}</div>')
                                # 材质完整信息
                                if p.get("material"):
                                    more_content_parts.append(f'<div class="gc-title">🧱 完整材质</div><div style="margin-bottom:8px;line-height:1.6;">{p["material"]}</div>')
                            
                            # 床架专属：床头柜搭配 + 排骨架/床架款式详情
                            if cat == "床架":
                                if p.get("nightstand_info"):
                                    more_content_parts.append(f'<div class="gc-title">🛏️ 建议搭配·床头柜</div><div style="margin-bottom:8px;line-height:1.6;white-space:pre-line;">{p["nightstand_info"]}</div>')
                                if p.get("bed_frame_style"):
                                    more_content_parts.append(f'<div class="gc-title">🪵 床架款式/排骨架</div><div style="margin-bottom:8px;line-height:1.6;">{p["bed_frame_style"]}</div>')
                                if p.get("design_style"):
                                    more_content_parts.append(f'<div class="gc-title">🎨 设计风格</div><div style="margin-bottom:8px;line-height:1.6;">{p["design_style"]}</div>')
                                if p.get("bed_leg_height"):
                                    more_content_parts.append(f'<div class="gc-title">🦵 床脚高度</div><div style="margin-bottom:8px;line-height:1.6;">{p["bed_leg_height"]}cm</div>')
                            
                            # 单组件规格价目表（沙发）
                            if cat == "沙发" and p.get("single_price_rows"):
                                more_content_parts.append('<div class="gc-title">🧩 单组件规格与价格</div>')
                                more_content_parts.append('<table class="pd-price-table" style="margin-bottom:8px;"><thead><tr><th>组件</th><th>宽度</th><th style="text-align:right">价格</th></tr></thead><tbody>')
                                for spr in p["single_price_rows"][:8]:
                                    parts = spr.split(" → ", 1)
                                    if len(parts) == 2:
                                        spec = parts[0]
                                        rest = parts[1]
                                        pm = re.search(r'(.*), (¥[\d,]+)', rest)
                                        if pm:
                                            size = pm.group(1)
                                            price = pm.group(2)
                                            more_content_parts.append(f'<tr><td>{spec}</td><td>{size}</td><td class="pd-td-price">{price}</td></tr>')
                                        else:
                                            more_content_parts.append(f'<tr><td>{spec}</td><td>{rest}</td><td class="pd-td-price">-</td></tr>')
                                    else:
                                        more_content_parts.append(f'<tr><td colspan="3">{spr}</td></tr>')
                                more_content_parts.append('</tbody></table>')
                            
                            if more_content_parts:
                                html_parts.append('<details class="pd-more-info" style="margin-top:6px;"><summary></summary>')
                                html_parts.append('<div class="pd-good-content">')
                                html_parts.append("".join(more_content_parts))
                                html_parts.append('</div></details>')
                        
                        html_parts.append('</div>')  # pd-body
                        html_parts.append('</div>')  # pd-card
                        
                        # 图片区（用 Streamlit st.image 高清显示）
                        if matching_img_dict:
                            c_imgs = matching_img_dict.get("catalog_images", [])
                            s_imgs = matching_img_dict.get("scene_images", [])
                            
                            # 浏览图（最多3张）
                            display_c_imgs = c_imgs[:3] if c_imgs else []
                            
                            if display_c_imgs:
                                html_parts.append('<div class="pd-imgs-st">')
                                html_parts.append('<div class="pd-imgs-label">🖼️ 产品图</div>')
                                html_parts.append('</div>')
                            
                            html_parts.append('</div>')  # pd-card-wrapper
                            
                            st.markdown("".join(html_parts), unsafe_allow_html=True)
                            
                            # 用 st.image 显示高清浏览图
                            if display_c_imgs:
                                img_cols = st.columns(len(display_c_imgs))
                                for i, img_p in enumerate(display_c_imgs):
                                    with img_cols[i]:
                                        resized = _load_resized_image(img_p, max_width=400)
                                        if resized:
                                            st.image(resized, use_container_width=True, caption=f"浏览图{i+1}")
                                        else:
                                            st.image(img_p, use_container_width=True, caption=f"浏览图{i+1}")
                                
                                # 场景图（1张，放在浏览图下方）
                                if s_imgs:
                                    with st.expander("🏡 查看场景图", expanded=False):
                                        for sp in s_imgs[:2]:
                                            resized = _load_resized_image(sp, max_width=500)
                                            if resized:
                                                st.image(resized, use_container_width=True)
                                            else:
                                                st.image(sp, use_container_width=True)
                        else:
                            html_parts.append('</div>')  # pd-card-wrapper
                            st.markdown("".join(html_parts), unsafe_allow_html=True)
    else:
        st.info("👆 请设置筛选条件后点击「🔍 开始查询」按钮，或使用上方快捷按键一键检索。")
