import os
import json
import re
import io
import base64
from datetime import datetime
import streamlit as st
from fpdf import FPDF
from openai import OpenAI
from dotenv import load_dotenv

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
if "trigger_query" not in st.session_state:
    st.session_state.trigger_query = False
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
      "蜜杏灰", "浅杏灰", "暖米灰", "深棕"], "深色系"),
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
    if not color_names:
        return "深色系"
    text = " ".join(color_names)
    # 先检查深色系
    for keywords, tone in _COLOR_TONE_RULES:
        if any(kw in text for kw in keywords):
            return tone
    # 包含 "色" 但不含上述关键词，根据常见色名判断
    if "白" in text or "米" in text or "奶" in text:
        return "浅色系"
    if "黑" in text or "灰" in text or "棕" in text or "褐" in text or "咖" in text or "深" in text:
        return "深色系"
    return "深色系"  # 默认深色


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
    all_prices: 所有规格的真实价格列表（用于价格区间计算）"""
    display_rows = []
    all_prices = []
    for line in text.split('\n'):
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
            all_prices.append(price_val)
            formatted = f"{spec_name} → {size_col}, ¥{price_val:,}"
            # 沙发只保留组合规格（含 + 号），床/床垫/配套保留所有规格
            if category != "沙发" or '+' in spec_name:
                display_rows.append(formatted)
                if len(display_rows) >= max_rows:
                    break
    return display_rows, all_prices


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

    # 产品线/系列
    series_match = re.search(r'\*\*产品线\*\*\s*:\s*(.+)', text)
    series = series_match.group(1).strip() if series_match else ""

    # 产品特点/卖点（取前 3 条）
    features = []
    in_features = False
    for line in text.split("\n"):
        if "产品特点" in line or "产品核心卖点" in line:
            in_features = True
            continue
        if in_features:
            if line.strip().startswith("- "):
                features.append(line.strip()[2:])
            elif line.strip() == "":
                if features:
                    break
            elif line.startswith("##") or line.startswith("###"):
                if features:
                    break

    # 一句话价值塑造
    value_match = re.search(r'### 一句话价值塑造\s*\n+\s*(.+?)(?:\n|$)', text)
    tagline = value_match.group(1).strip() if value_match else ""

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

    # 价格：从规格价格表提取（精确可靠，替换旧的全文档正则）
    price_rows, table_prices = _extract_price_rows(text, category, max_rows=8)
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

    # 设计风格（沙发专用）
    design_style = ""
    ds_match = re.search(r'### 设计风格\s*\n+\s*(.+?)(?:\n|$)', text)
    if ds_match:
        design_style = ds_match.group(1).strip()
        # 清理尾部多余的描述文字（如末尾带句号的风格描述）
        design_style = re.sub(r'[。，].*$', '', design_style).strip()

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

    # 床头高度（床架专用）：从床架外尺寸(总长×总宽×头高)中提取
    # 如 "228×166×115" → 头高 115cm
    bed_head_height = 0
    if category == "床架":
        head_heights = []
        for line in text.split('\n'):
            if '×' not in line and 'x' not in line.lower():
                continue
            stripped = line.strip()
            if not stripped.startswith('|'):
                # 非表格行只匹配包含"床架外尺寸"或"外尺寸"关键词的行
                if '床架外尺寸' not in stripped and '外尺寸' not in stripped and '头高' not in stripped:
                    continue
                nums = re.findall(r'(\d+)\s*[×x]\s*(\d+)\s*[×x]\s*(\d+)', line.lower())
                for n in nums:
                    head_heights.append(int(n[2]))
                continue
            parts = [p.strip() for p in stripped.split('|') if p.strip()]
            if len(parts) < 2:
                continue
            # 匹配尺寸列（第二列）中的 "数字×数字×数字" 格式
            size_col = parts[1]
            nums = re.findall(r'(\d+)\s*[×x]\s*(\d+)\s*[×x]\s*(\d+)', size_col.lower())
            for n in nums:
                v = int(n[2])
                if 50 <= v <= 200:  # 头高合理范围
                    head_heights.append(v)
        if head_heights:
            bed_head_height = head_heights[0]

    # 材质（床垫/配套通用）：如 "Sanitized®抑菌防螨面料+乳胶+平衡支撑绵+六环精钢连锁簧+护边系统"
    material = ""
    material_match = re.search(r'\*\*材质\*\*\s*:\s*(.+)', text)
    if material_match:
        material = material_match.group(1).strip()

    # 产品配置（床垫专用）：含面料层/填充层/支撑层等
    product_config = ""
    config_match = re.search(r'\*\*产品配置\*\*:\s*\n((?:  .+\n?)+)', text)
    if config_match:
        product_config = config_match.group(1).strip().replace('\n  ', ' | ')

    # 靠包类型（床架专用）：上下左右分段式/仅上下分段式/仅左右分段式/整体无分段/无床头
    headboard_type = ""
    hb_match = re.search(r'\*\*靠包类型\*\*\s*:\s*(.+)', text)
    if hb_match:
        headboard_type = hb_match.group(1).strip()

    return {
        "model": model,
        "name": name,
        "category": category,
        "series": series,
        "tagline": tagline[:80],
        "features": features[:3],
"colors": colors,
        "color_codes": color_codes[:3],
        "color_tone": color_tone,
        "min_price": min_price,
        "max_price": max_price,
        "lengths": sorted(set(lengths)),
        "specs": specs[:3],
        "bed_frame_height": bed_frame_height,
        "mattress_thickness": mattress_thickness,
        "price_rows": price_rows,
        "design_style": design_style,
        "sofa_dimensions": sofa_dimensions,
        "sofa_components": sofa_components,
        "all_spec_names": all_spec_names,
        "bed_head_height": bed_head_height,
        "material": material,
        "product_config": product_config,
        "headboard_type": headboard_type,
    }


@st.cache_data(show_spinner=False, ttl=86400)
def build_product_index_v3(_version="v10_headboard_type"):
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


def filter_candidates(index, category=None, max_price=None, sofa_length=None, style=None, keywords=None, min_candidates=8):
    """从产品索引中快速筛选候选产品
    关键词匹配策略（三级降级）：
    1. 先用关键词精确匹配，找到匹配的产品
    2. 如果不够 min_candidates 个，再宽松补齐（同一品类下无需关键词的候选）
    3. 如果还不够，去掉预算限制补齐
    返回：候选产品列表 + 精简摘要文本（供 LLM 使用）"""
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
                    f"{p.get('color_tone','')} "
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

    # 降级策略：关键词匹配不够时，用品类/预算内产品补齐
    if len(candidates) < min_candidates and fallback_pool:
        need = min(min_candidates - len(candidates), len(fallback_pool))
        candidates.extend(fallback_pool[:need])

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
                line += f" | 颜色: {'/'.join(colors_show[:5])}"
            else:
                line += f" | 配色: {'/'.join(colors_show[:5])}"
        if p.get("color_tone"):
            line += f" | 色调: {p['color_tone']}"
        if p.get("color_codes"):
            line += f" | 色号: {', '.join(p['color_codes'][:2])}"
        if p.get("bed_frame_height"):
            line += f" | 床身高度: {p['bed_frame_height']}cm"
        if p.get("mattress_thickness"):
            line += f" | 适配床垫厚度: {p['mattress_thickness']}"
        if p.get("headboard_type"):
            line += f" | 靠包类型: {p['headboard_type']}"
        if p.get("product_config"):
            line += f"\n    产品配置: {p['product_config']}"
        if p.get("material"):
            line += f"\n    材质: {p['material']}"
        if p.get("bed_head_height") and p["bed_head_height"] > 0:
            line += f" | 床头高度: {p['bed_head_height']}cm"
        if p.get("tagline"):
            line += f" | 卖点: {p['tagline']}"
        if p.get("design_style"):
            line += f" | 风格: {p['design_style']}"
        if p.get("features"):
            line += f" | 特点: {'; '.join(p['features'][:2])}"
        if p.get("price_rows"):
            line += "\n    " + "\n    ".join(p["price_rows"][:6])
        if p.get("sofa_dimensions"):
            dims = p["sofa_dimensions"]
            parts = []
            for key in ["靠背高度", "坐深", "坐垫高度", "扶手高度", "沙发深度"]:
                if key in dims:
                    parts.append(f"{key}: {dims[key]}cm")
            if parts:
                line += f" | {' '.join(parts)}"
        if p.get("sofa_components"):
            comps = p["sofa_components"]
            line += f" | 组件尺寸: {', '.join(f'{k}={v}cm' for k, v in list(comps.items())[:6])}"
        lines.append(line)

    summary = "\n".join(lines) if lines else "（无匹配产品）"
    return candidates, summary


# ==================== 5. 流式生成器 ====================
def _get_client(api_key):
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def stream_response(api_key, model, system_prompt, user_prompt):
    client = _get_client(api_key)
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        stream=True,
        temperature=0.2
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


def _generate_quote_html():
    """根据当前 session_state 中的报告和表单数据，生成报价单 HTML 字符串"""
    form = st.session_state.get("quote_form_data", {})
    report = st.session_state.get("current_report", "")

    # 提取产品信息（从报告文本中用正则提取型号和价格）
    products = []
    # 匹配 "KUKA 0033" 或 "JD.0036" 等产品型号后面跟价格 ¥12,800 的模式
    price_patterns = re.findall(r'([A-Za-z0-9.]+(?:[-\s][A-Za-z0-9\u4e00-\u9fff]+)?)\s*[:：]?\s*[^¥￥]*?[¥￥]\s*([\d,]+)', report)
    seen = set()
    for name, price_str in price_patterns:
        key = name.strip()[:20]
        if key not in seen:
            seen.add(key)
            price = int(price_str.replace(",", ""))
            products.append({"name": name.strip(), "price": price, "qty": 1})

    # 如果没提取到，回退：从报告中找所有 ¥ 价格
    if not products:
        all_prices = re.findall(r'[¥￥]\s*([\d,]+)', report)
        for i, p in enumerate(all_prices[:10]):
            products.append({"name": f"产品 {i+1}", "price": int(p.replace(",", "")), "qty": 1})

    total_price = sum(p["price"] * p["qty"] for p in products)
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

    # 提取设计理念段落（取报告前 500 字作为设计理念）
    concept_text = report[:800].strip() if report else "根据客户需求与空间尺寸分析，为您量身定制全屋软装搭配方案。"
    # 清理 Markdown 标记
    concept_text = re.sub(r'#{1,6}\s*', '', concept_text)
    concept_text = re.sub(r'\*\*(.*?)\*\*', r'\1', concept_text)
    concept_text = concept_text[:600]

    # 生成产品表格行
    product_rows = ""
    for i, p in enumerate(products, 1):
        product_rows += f"""
        <tr>
            <td style="text-align: center;">{i}</td>
            <td style="text-align: center;"><div class="img-placeholder">📦</div></td>
            <td><strong>{p['name']}</strong><br><span style="color: #2563eb; font-size: 10px;">KUKA 全屋定制系列</span></td>
            <td style="text-align: center;">{p['qty']}</td>
            <td style="text-align: right; font-weight: bold;">¥{p['price']:,}</td>
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
        width: 50px; height: 50px; background: #f1f5f9; border-radius: 4px;
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
        <div class="brand-name">🛋️ KUKA HOME 软装定制</div>
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
        <div class="concept-title">💡 空间搭配与设计理念</div>
        <p>{concept_text}</p>
    </div>

    <table class="quote-table">
        <thead>
            <tr>
                <th style="width: 8%;">序号</th>
                <th style="width: 12%;">产品图片</th>
                <th style="width: 50%;">产品名称 / 规格 / 卖点</th>
                <th style="width: 10%;">数量</th>
                <th style="width: 20%;">成交价</th>
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
    report = st.session_state.get("current_report", "")

    # 提取产品信息
    products = []
    price_patterns = re.findall(r'([A-Za-z0-9.]+(?:[-\s][A-Za-z0-9\u4e00-\u9fff]+)?)\s*[:：]?\s*[^¥￥]*?[¥￥]\s*([\d,]+)', report)
    seen = set()
    for name, price_str in price_patterns:
        key = name.strip()[:20]
        if key not in seen:
            seen.add(key)
            price = int(price_str.replace(",", ""))
            products.append({"name": name.strip(), "price": price, "qty": 1})
    if not products:
        all_prices = re.findall(r'[¥￥]\s*([\d,]+)', report)
        for i, p in enumerate(all_prices[:10]):
            products.append({"name": f"产品 {i+1}", "price": int(p.replace(",", "")), "qty": 1})

    total_price = sum(p["price"] * p["qty"] for p in products)
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

    # 提取设计理念
    concept_text = report[:600].strip() if report else "根据客户需求与空间尺寸分析，为您量身定制全屋软装搭配方案。"
    concept_text = re.sub(r'#{1,6}\s*', '', concept_text)
    concept_text = re.sub(r'\*\*(.*?)\*\*', r'\1', concept_text)
    concept_text = re.sub(r'\n+', ' ', concept_text)[:500]

    # 创建 PDF
    class QuotePDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 16)
            self.set_text_color(37, 99, 235)
            self.cell(0, 10, "KUKA HOME  -  ", new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "", 8)
            self.set_text_color(100, 116, 139)
            self.cell(0, 5, f"          报价单号: {doc_no}", new_x="LMARGIN", new_y="NEXT")
            self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
            self.ln(8)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(148, 163, 184)
            self.cell(0, 10, f"第 {self.page_no()} 页 / 共 {{nb}} 页", align="C")

        def section_title(self, title):
            self.set_font("Helvetica", "B", 12)
            self.set_text_color(30, 41, 59)
            self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

        def meta_row(self, label, value):
            self.set_font("Helvetica", "", 9)
            self.set_text_color(100, 116, 139)
            self.cell(30, 5, label, new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(30, 41, 59)
            self.cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")

    pdf = QuotePDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # --- 客户信息区 ---
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, pdf.get_y(), 190, 28, style="DF")
    y_start = pdf.get_y() + 3
    pdf.set_xy(14, y_start)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "装修风格:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(50, 5, style, new_x="END")
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "墙面颜色:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(50, 5, wall_color, new_x="END")
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "地面材质:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 5, floor_color, new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(14)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "空间尺寸:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(50, 5, f"客厅开间 {room_width}米 / 背景墙 {sofa_wall_len}米", new_x="END")
    pdf.set_text_color(100, 116, 139)
    pdf.cell(25, 5, "预算区间:", new_x="END")
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 5, f"¥{budget:,} 元", new_x="LMARGIN", new_y="NEXT")

    if bedroom_detail:
        pdf.set_x(14)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(25, 5, "卧室配置:", new_x="END")
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 5, bedroom_detail[:80], new_x="LMARGIN", new_y="NEXT")
    if notes:
        pdf.set_x(14)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(25, 5, "备注:", new_x="END")
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 5, notes[:80], new_x="LMARGIN", new_y="NEXT")

    pdf.ln(12)

    # --- 设计理念 ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, "Design Concept  -  ", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(37, 99, 235)
    pdf.line(10, pdf.get_y(), 12, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5, concept_text)
    pdf.ln(8)

    # --- 产品报价表 ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, "Quotation Details  -  ", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # 表头
    col_w = [12, 68, 22, 20, 28]  # 序号, 产品名称, 数量, 单价, 小计
    headers = ["#", "Product / Specification", "Qty", "Unit Price", "Subtotal"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C" if i != 1 else "L")
    pdf.ln()

    # 数据行
    pdf.set_font("Helvetica", "", 8)
    fill = False
    for i, p in enumerate(products, 1):
        if pdf.get_y() > 260:
            pdf.add_page()
            # 重复表头
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(37, 99, 235)
            pdf.set_text_color(255, 255, 255)
            for j, h in enumerate(headers):
                pdf.cell(col_w[j], 7, h, border=1, fill=True, align="C" if j != 1 else "L")
            pdf.ln()
            pdf.set_font("Helvetica", "", 8)
            fill = False

        if fill:
            pdf.set_fill_color(248, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(30, 41, 59)

        subtotal = p["price"] * p["qty"]
        pdf.cell(col_w[0], 7, str(i), border=1, align="C", fill=True)
        pdf.cell(col_w[1], 7, p["name"][:30], border=1, fill=True)
        pdf.cell(col_w[2], 7, str(p["qty"]), border=1, align="C", fill=True)
        pdf.cell(col_w[3], 7, f"¥{p['price']:,}", border=1, align="R", fill=True)
        pdf.cell(col_w[4], 7, f"¥{subtotal:,}", border=1, align="R", fill=True)
        pdf.ln()
        fill = not fill

    pdf.ln(5)

    # --- 总价 ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(220, 38, 38)
    pdf.cell(0, 10, f"Total:  ¥{total_price:,}.00", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # --- 签署区 ---
    pdf.set_draw_color(203, 213, 225)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(10)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 7, "Designer Signature:  __________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Customer Signature:  __________________", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(148, 163, 184)
    pdf.multi_cell(0, 4, "This quotation is valid for 7 days. Includes free delivery and professional installation. Final interpretation rights belong to KUKA HOME.", align="C")

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
            st.session_state.query_in_progress = True
            st.session_state.trigger_query = True
            st.rerun()

        if st.session_state.get("query_in_progress") and st.session_state.get("trigger_query"):
            st.session_state.trigger_query = False
            if not api_key.startswith("sk-"):
                st.error("❌ 请先配置 DeepSeek API Key（侧边栏或 secrets.toml）")
                st.session_state.query_in_progress = False
                st.rerun()
                st.stop()

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
            sofa_budget = int(total_budget * 0.50)   # 沙发约占 50%
            bed_budget = int(total_budget * 0.40)     # 床+床垫约占 40%
            table_budget = int(total_budget * 0.15)   # 配套约占 15%

            sofa_wall_cm = sofa_wall_len * 100
            sofa_min = int(sofa_wall_cm * 0.7)
            sofa_max = int(sofa_wall_cm * 0.85)

            sofa_candidates, sofa_summary = filter_candidates(
                product_index, category="沙发", max_price=sofa_budget, sofa_length=sofa_wall_cm, style=style_pref
            )
            bed_candidates, bed_summary = filter_candidates(
                product_index, category="床架", max_price=bed_budget
            )
            mattress_candidates, mattress_summary = filter_candidates(
                product_index, category="床垫", max_price=bed_budget
            )
            table_candidates, table_summary = filter_candidates(
                product_index, category="配套", max_price=table_budget
            )

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
                    product_index, category="床架", max_price=int(bed_budget * 1.5)
                )
                bed_summary += "\n（注：已适度放宽预算限制）"
                _bed_relaxed = True
            _mat_relaxed = False
            if "无匹配产品" in mattress_summary:
                mattress_candidates, mattress_summary = filter_candidates(
                    product_index, category="床垫", max_price=int(bed_budget * 1.5)
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

            with st.expander("🔍 诊断：AI 收到的候选产品摘要", expanded=False):
                st.caption("沙发候选:"); st.code(sofa_summary[:500])
                st.caption("床架候选:"); st.code(bed_summary[:500])
                st.caption("床垫候选:"); st.code(mattress_summary[:500])
                st.caption("配套候选:"); st.code(table_summary[:500])

            # 标记哪些品类放宽了预算
            _relaxed_notes = []
            if _sofa_relaxed: _relaxed_notes.append("沙发")
            if _bed_relaxed: _relaxed_notes.append("床架")
            if _mat_relaxed: _relaxed_notes.append("床垫")
            if _table_relaxed: _relaxed_notes.append("配套")
            _relaxed_hint = f"（以下品类候选已适度放宽：{'、'.join(_relaxed_notes)}，请优先选择其中价格较低的产品）" if _relaxed_notes else ""

            system_prompt = f"""你是一位顶级的家居软装与健康睡眠主理人。**严格仅从下方精选候选产品中**为客户搭配方案，不得推荐列表之外的产品（如无合适产品则如实说明）。

【精选沙发候选】：
{sofa_summary}

【精选床架候选】：
{bed_summary}

【精选床垫候选】：
{mattress_summary}

【精选配套（茶几/电视柜/餐桌椅）候选】：
{table_summary}

【预算分配】（客户总预算：¥{total_budget:,}）：
- 🛋️ 沙发品类预算上限：约 ¥{sofa_budget:,}  {_relaxed_hint}
- 🛏️ 床架+床垫品类预算上限：约 ¥{bed_budget:,}（含所有卧室）{_relaxed_hint}
- 🪑 配套（茶几/电视柜/餐桌椅）预算上限：约 ¥{table_budget:,}  {_relaxed_hint}
- ⚠️ 各品类预算之和不得超过总预算 ¥{total_budget:,}

【搭配规则】：
        1. 💰 **严控预算（最高优先级）**：
           - 推荐方案总价**必须**控制在预算的 **95%~100%** 之间（即 ¥{int(total_budget*0.95):,}~¥{total_budget:,}），**严格禁止超预算**！
           - 每个品类的总价不得超过上方【预算分配】中对应的品类预算上限。
           - 如果候选产品组合超出预算，必须减少品类或选择更低价的产品/规格，直到总价不超过 ¥{total_budget:,}。
           - **必须在输出中逐项列出每个产品的价格，并在最后计算累加总价，确认不超过 ¥{total_budget:,}。**
        2. 🛏️ **必须为每个卧室配置床架+床垫**：客户选了卧室就必须推荐对应的床和床垫，不得遗漏。
        3. 📐 **沙发长度严格匹配**：沙发总长度必须在 **{sofa_min}~{sofa_max}cm** 之间（背景墙 {sofa_wall_len} 米的 70%~85%），不得推荐此范围之外的规格。
        4. ✅ **严格按采购清单推荐**：只推荐客户勾选的品类，未勾选的品类不要推荐。
        5. 💤 **融入科学睡眠理念**。
        6. 🛌 **床垫厚度匹配**：计算睡眠总高度时使用床架标注的**床身高度**（即床架平台离地高度），搭配床垫后总高度建议 45~55cm，**非**床头靠背高度。
        7. ⚠️ **价格必须使用候选产品中标注的真实价格**：每个产品下方标注有具体的规格价格表（如"1.5右B+3左A丨扶手翻折 → 296cm, ¥12,399"），请直接从这些数据中引用价格，**不得自行编造价格**。如候选产品中无对应规格则如实说明。
        8. 🪑 **推荐餐桌时必须标配 4 把椅子**：配套产品中的餐台（如 PT3188T 等）必须搭配对应系列的餐椅（如 PT3188Y），且每张餐台搭配 4 把椅子计算总价。
        9. 🎨 **色调匹配**：优先推荐与客户墙面/地面颜色同色调的产品。墙面浅色系（如奶咖色/奶油白/纯白）搭配浅色系产品，深色系墙面（太空灰/咖色护墙板）可搭配深色系产品形成层次感。地面同理。
        10. ⛔ **超预算处理**：如果所有候选产品组合后的总价仍超过预算，请主动告知客户并给出最接近预算的方案，**不要强行凑出超预算的方案**。

【输出结构】：
一、空间尺寸与气场碰撞分析
二、全屋推荐产品清单与报价明细（**每个产品必须注明具体规格/组合名称、总长度、实际成交价**，不得只写产品名和价格范围）
    请在推荐清单后附上 **逐项价格计算过程**，确认各品类在预算分配内、总价不超过 ¥{total_budget:,}。
三、价格汇总与预算控制说明
四、科学睡眠理念与健康生活场景建议"""

            # 构造采购清单
            items_list = []
            if need_sofa: items_list.append("🛋️ 沙发")
            if need_chair: items_list.append("🪑 单人休闲椅")
            if need_table: items_list.append("☕ 茶几")
            if need_tv: items_list.append("📺 电视柜")
            if need_dining: items_list.append("🍽️ 餐桌椅组合")

            user_prompt = f"""客户需求：
- 风格：{style_pref}
- 客厅开间：{room_width}米，背景墙：{sofa_wall_len}米
- 墙面：{wall_color}，地面：{floor_color}
- **采购清单**：{'、'.join(items_list) if items_list else '无'}
- 总预算：¥{total_budget:,}（**总价不得超过预算¥{total_budget:,}**，严格禁止超预算）
- 品类预算分配参考：沙发≤¥{sofa_budget:,}，床架+床垫≤¥{bed_budget:,}，配套≤¥{table_budget:,}
- 特殊需求：{'; '.join(special_tags)}
- 备注：{custom_notes if custom_notes else '无'}
- **卧室配置（必须为以下每个房间推荐床架+床垫）**：
{chr(10).join(f'  · {bd["room_name"]}: {bd["bed_spec"]}, 床垫需求: {bd["mat_pref"]}' for bd in bedroom_configs) if bedroom_configs else '  无卧室配置'}
"""

            try:
                full_response = st.write_stream(stream_response(api_key, model_name, system_prompt, user_prompt))
                # 保存当前报告到 session_state，供后续微调使用
                st.session_state.current_report = full_response
                # 记录历史版本
                st.session_state.report_history.append(full_response)
            except Exception as e:
                st.error(f"❌ API 调用失败: {e}")
                st.session_state.query_in_progress = False
                st.stop()

            # 图集
            st.divider()
            st.subheader("🖼️ 推荐产品视觉预览")
            matched_models = set()
            for m in re.findall(r'[A-Za-z0-9.]+', full_response):
                if len(m) >= 4:
                    matched_models.add(m.upper())

            display_count = 0
            for folder_key, img_dict in images_db.items():
                if any(m in folder_key.upper() for m in matched_models):
                    display_count += 1
                    with st.expander(f"📦 视觉预览：{folder_key}", expanded=True):
                        tab_cat, tab_scene, tab_home = st.tabs(["📦 规格/浏览图", "🏡 展厅/场景效果图", "📸 客户入户实景图"])
                        for tab_name, img_key in [("cat", "catalog_images"), ("scene", "scene_images"), ("home", "home_images")]:
                            with [tab_cat, tab_scene, tab_home][["cat", "scene", "home"].index(tab_name)]:
                                imgs = img_dict.get(img_key, []) or (img_dict.get("real_images", []) if img_key == "home_images" else [])
                                if imgs:
                                    for i in range(0, len(imgs), 3):
                                        cols = st.columns(3)
                                        for j, img_p in enumerate(imgs[i:i+3]):
                                            with cols[j]:
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
                st.markdown(st.session_state.current_report)
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
                    # 组装精简的微调 Prompt
                    edit_prompt = f"""你是一名专业软装设计师。以下是之前为客户生成的方案：
    ---
    {st.session_state.current_report}
    ---
    客户提出了以下修改意见：
    "{edit_instruction}"

    请在保留原方案合理部分的基础上，针对客户意见重新更新一份完整软装报告与报价单。
    """
                    try:
                        st.info("🤖 AI 正在根据您的意见调整方案...")
                        new_report = st.write_stream(stream_response(api_key, model_name, edit_prompt, f"客户修改意见：{edit_instruction}"))
                        st.session_state.current_report = new_report
                        st.session_state.report_history.append(new_report)
                        st.success("✅ 方案已更新！")
                    except Exception as e:
                        st.error(f"❌ 微调失败: {e}")
                    finally:
                        st.session_state.refine_in_progress = False


# =========================================================================
# Tab 2：导购速查（同样使用预筛选）
# =========================================================================
with main_tab2:
    st.subheader("🔍 导购全品类速查助手（床 / 床垫 / 沙发）")
    st.caption("⚡ 专门面向线下导购：随手输入要求，精准匹配！")

    col_q1, col_q2 = st.columns([3, 1])
    with col_q1:
        guide_query = st.text_input("请输入查询条件：", placeholder="例如：1.8米皮床，推荐适配厚度22-25cm的独立弹簧护脊床垫，总预算7000内", key="guide_query_input")
    with col_q2:
        st.write(" "); st.write(" ")
        search_btn = st.button("🔎 立即检索库", type="primary", use_container_width=True, disabled=st.session_state.guide_query_in_progress)

    st.caption("💡 高频快捷检索：")
    col_e1, col_e2, col_e3, col_e4 = st.columns(4)
    if col_e1.button("📌 1.8米床 + 适配床垫组合", disabled=st.session_state.guide_query_in_progress):
        guide_query = "1.8米主卧软体床，推荐匹配高度适中的护脊床垫，一套预算8000以内"
        search_btn = True
    if col_e2.button("📌 青少年防弯曲护脊床垫", disabled=st.session_state.guide_query_in_progress):
        guide_query = "适合青少年或儿童的1.5米护脊床垫，透气环保硬质支撑"
        search_btn = True
    if col_e3.button("📌 3米左右 1万内 意式沙发", disabled=st.session_state.guide_query_in_progress):
        guide_query = "尺寸3米左右，价格10000以内，意式风格真皮或科技布沙发"
        search_btn = True
    if col_e4.button("📌 独立弹簧零干扰静音床垫", disabled=st.session_state.guide_query_in_progress):
        guide_query = "主卧独立袋装弹簧床垫，抗干扰抗震动，适合浅睡眠人群"
        search_btn = True

    st.markdown("---")

    if search_btn and guide_query:
        if st.session_state.guide_query_in_progress:
            st.info("⏳ 正在检索中，请耐心等待...")
            st.stop()
        st.session_state.guide_query_in_progress = True
        if not api_key.startswith("sk-"):
            st.error("❌ 请先配置 DeepSeek API Key")
            st.session_state.guide_query_in_progress = False
            st.stop()

        # 记录导购查询
        _log_query("guide_search", {"query": guide_query, "source": "quick_btn" if guide_query in [
            "1.8米主卧软体床，推荐匹配高度适中的护脊床垫，一套预算8000以内",
            "适合青少年或儿童的1.5米护脊床垫，透气环保硬质支撑",
            "尺寸3米左右，价格10000以内，意式风格真皮或科技布沙发",
            "主卧独立袋装弹簧床垫，抗干扰抗震动，适合浅睡眠人群",
        ] else "manual_input"})

        # 判断是否为命名/型号解读类问题
        if _is_naming_query(guide_query):
            # 命名问题：直接使用命名结构文档回答，不查产品
            naming_prompt = f"""你是一位顾家家居产品专家。用户正在询问床类产品型号的命名规则。

请参考以下《卧室产品命名结构说明》文档，用通俗易懂的语言解答用户的疑问。

【命名结构文档】：
{BED_NAMING_GUIDE}

【用户提问】：{guide_query}

【输出要求】：
1. 用简明清晰的语言解释命名规则
2. 如果用户提到了具体型号（如 FQ1PQ4），请按文档解析该型号的各段位含义
3. 如果用户没有具体型号，用文档中的示例（如 ZX.B712PQ7）来演示如何解读
4. 让导购能看懂并能快速向客户解释"""
            try:
                result_placeholder = st.empty()
                full_result = ""
                for chunk in stream_response(api_key, model_name, naming_prompt, f"用户问题：{guide_query}"):
                    full_result += chunk
                    result_placeholder.markdown(re.sub(r'~~', '', full_result) + "▌")
                result_placeholder.markdown(re.sub(r'~~', '', full_result))
            except Exception as e:
                st.error(f"❌ 检索失败: {e}")
        else:
            # 产品检索：从查询中提取关键词和预算
            budget_match = re.search(r'(\d{4,})\s*元|\d{4,}\s*以内|\d{4,}\s*内|预算(\d{4,})', guide_query)
            max_price = int(budget_match.group(1) or budget_match.group(2) or 0) if budget_match else None

            kw = ""
            if "床垫" in guide_query:
                kw = "床垫"
            elif "床" in guide_query or "软体床" in guide_query:
                kw = "床架"
            elif "沙发" in guide_query:
                kw = "沙发"

            cat_map = {"床垫": "床垫", "床架": "床架", "沙发": "沙发"}
            category = cat_map.get(kw)

            # 增强关键词提取：同时保留原始查询 + 提取的数字/型号关键词
            # 用 \d{2,} 代替 \b\d{3,4}\b，因为 \b 在中文前后（如"815的床"）会失效
            search_kw = guide_query
            model_patterns = re.findall(r'[A-Za-z]{1,4}\.?\d{2,4}[A-Za-z0-9]*|\d{2,}', guide_query)
            extra_kw = " ".join(model_patterns)
            if extra_kw.strip():
                search_kw = guide_query + " " + extra_kw
            # 色系关键词补充：用户搜"浅色床"，需匹配"浅色系"
            if "浅色" in guide_query:
                search_kw += " 浅色"
            if "深色" in guide_query:
                search_kw += " 深色"
            if "浅色系" in guide_query or "浅色调" in guide_query:
                search_kw += " 浅色系"
            if "深色系" in guide_query or "深色调" in guide_query:
                search_kw += " 深色系"
            candidates, summary = filter_candidates(product_index, category=category, max_price=max_price, keywords=search_kw, min_candidates=999)

            # 如果查询中包含型号字样（如 B815PQ1），同时提供命名解读作为参考
            naming_context = ""
            if re.search(r'[A-Z]{1,3}\.?\d{3,}', guide_query):
                naming_context = f"\n\n【参考 - 床型号命名规则】\n当客户问起型号含义时，可参考以下规则解析：\n" + BED_NAMING_GUIDE[:1500]

            guide_prompt = f"""你是一位精准的家居与睡眠产品检索助手。**以下列出了所有符合条件的候选产品**，请逐一列出并说明。如无合适产品则如实说明。

【所有候选产品】：
{summary}

【导购要求】：{guide_query}{naming_context}

【输出要求】：
1. **列出所有候选产品**，逐一说明每个产品的型号、规格、成交价和推荐理由。
2. **必须使用候选产品中标注的真实价格**（每个产品下方都有具体的规格价格表），不得自行编造。
3. 涉及床+床垫搭配时说明高度适配性：使用床架标注的**床身高度**（平台离地高）搭配床垫，总睡眠高度建议 45~55cm，**非**床头靠背高度。
4. 涉及餐桌时，必须搭配 4 把同系列餐椅计算总价。"""

            try:
                result_placeholder = st.empty()
                full_result = ""
                for chunk in stream_response(api_key, model_name, guide_prompt, f"导购检索：{guide_query}"):
                    full_result += chunk
                    result_placeholder.markdown(re.sub(r'~~', '', full_result) + "▌")
                result_placeholder.markdown(re.sub(r'~~', '', full_result))

                st.markdown("---")
                st.markdown("### 🖼️ 匹配产品图片")
                matched_models = set(re.findall(r'[A-Za-z0-9.]+', full_result))
                display_count = 0
                for folder_key, img_dict in images_db.items():
                    if any(m.upper() in folder_key.upper() for m in matched_models if len(m) >= 4):
                        display_count += 1
                        st.markdown(f"#### 📦 {folder_key}")
                        tab_cat, tab_scene, tab_home = st.tabs(["📦 规格/浏览图", "🏡 展厅/场景效果图", "📸 客户入户实景图"])
                        for tab_name, img_key in [("cat", "catalog_images"), ("scene", "scene_images"), ("home", "home_images")]:
                            with [tab_cat, tab_scene, tab_home][["cat", "scene", "home"].index(tab_name)]:
                                imgs = img_dict.get(img_key, []) or (img_dict.get("real_images", []) if img_key == "home_images" else [])
                                if imgs:
                                    for i in range(0, len(imgs), 3):
                                        cols = st.columns(3)
                                        for j, img_p in enumerate(imgs[i:i+3]):
                                            with cols[j]:
                                                st.image(img_p, use_container_width=True)
                                else:
                                    st.info({"cat": "暂无规格/浏览图", "scene": "暂无展厅/场景效果图", "home": "📸 暂无客户入户实景图"}[tab_name])
                if display_count == 0:
                    st.info("💡 提示：未能匹配到图片。")
            except Exception as e:
                st.error(f"❌ 检索失败: {e}")
            finally:
                st.session_state.guide_query_in_progress = False
