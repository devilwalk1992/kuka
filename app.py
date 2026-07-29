import os
import json
import re
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ==================== 1. 页面基本配置 ====================
st.set_page_config(
    page_title="KUKA 赛博软装与睡眠主理人 - DeepSeek AI 导购系统",
    page_icon="🛋️",
    layout="wide"
)

# 优先用 __file__ 定位脚本所在目录
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
except Exception:
    BASE_DIR = os.getcwd()
MD_DB_DIR = os.path.join(BASE_DIR, "markdown_db")
# fallback: 若 __file__ 路径找不到，尝试相对路径
if not os.path.exists(MD_DB_DIR):
    MD_DB_DIR = os.path.join(os.getcwd(), "markdown_db")
JSON_INDEX_PATH = os.path.join(MD_DB_DIR, "product_images.json")


# ==================== 2. 本地数据库读取 ====================
@st.cache_data(ttl=3600)
def load_database():
    """读取 Markdown 数据库与 JSON 图文索引"""
    knowledge_base = ""
    if os.path.exists(MD_DB_DIR):
        for root, dirs, files in os.walk(MD_DB_DIR):
            for file in files:
                if file.endswith(".md"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, MD_DB_DIR)
                    with open(file_path, "r", encoding="utf-8") as f:
                        knowledge_base += f"\n\n--- 档案文件: {rel_path} ---\n" + f.read()

    images_db = {}
    if os.path.exists(JSON_INDEX_PATH):
        with open(JSON_INDEX_PATH, "r", encoding="utf-8") as f:
            images_db = json.load(f)

        # 将图片路径转为绝对路径
        for folder_key, img_dict in images_db.items():
            for key in ("catalog_images", "scene_images", "home_images", "real_images"):
                if key in img_dict and img_dict[key]:
                    img_dict[key] = [
                        os.path.join(BASE_DIR, p) if not os.path.isabs(p) else p
                        for p in img_dict[key]
                    ]

    return knowledge_base, images_db

knowledge_base, images_db = load_database()


# ==================== 3. 侧边栏 (Sidebar) - API 设置 ====================
with st.sidebar:
    st.header("⚙️ DeepSeek API 设置")
    api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=os.getenv("DEEPSEEK_API_KEY", ""),
        placeholder="sk-...",
        help="优先读取 .env 文件中的 DEEPSEEK_API_KEY"
    )

    model_name = st.selectbox(
        "模型选择",
        ["deepseek-v4-flash", "deepseek-v4-pro"],
        index=0,
        help="deepseek-v4-flash 为 DeepSeek-V4 快速模型（推荐）；deepseek-v4-pro 为专业推理模型"
    )

    st.divider()
    st.header("📊 数据库状态")
    if knowledge_base:
        st.success(f"✅ 知识库已就绪\n(包含 {len(images_db)} 个产品映射)")
    else:
        st.warning("⚠️ 未找到 markdown_db 目录，请先运行 build_full_database.py")


# ==================== 4. 主界面 Header & 功能 Tab 切换 ====================
st.title("🛋️ KUKA 赛博软装与睡眠主理人 · 智能导购工作台")

main_tab1, main_tab2 = st.tabs(["🏠 全屋 AI 软装与睡眠方案生成", "🔍 导购全品类速查助手（床/床垫/沙发）"])


# =========================================================================
# 【Tab 1】：全屋 AI 软装与睡眠方案搭配生成
# =========================================================================
with main_tab1:
    col_left, col_right = st.columns([1, 1], gap="large")

    # -------------------- 【左侧列】：客户空间与需求录入区 --------------------
    with col_left:
        st.subheader("🏠 1. 客厅空间与硬装环境")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            room_width = st.number_input("客厅开间/视距 (米)", min_value=2.0, max_value=8.0, value=3.6, step=0.1)
            wall_color = st.selectbox("墙面颜色", ["奶咖色/大白墙", "浅灰色", "原木色系", "暗色极简"])
            style_pref = st.selectbox("整体装修风格", ["意式极简", "法式奶油风", "现代轻奢", "极简风", "原木风", "新中式"])
        with col_s2:
            sofa_wall_len = st.number_input("沙发背景墙长度 (米)", min_value=2.0, max_value=8.0, value=4.2, step=0.1)
            floor_color = st.selectbox("地面材质", ["浅色亮光地砖", "柔光大理石砖", "原木地板", "灰调地砖"])

        st.subheader("🛒 2. 客厅与餐厨采购清单")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            need_sofa = st.checkbox("🛋️ 沙发", value=True)
            need_chair = st.checkbox("🪑 单人休闲椅", value=False)
            need_table = st.checkbox("☕ 茶几", value=True)
        with col_c2:
            need_tv = st.checkbox("📺 电视柜", value=True)
            need_dining = st.checkbox("🍽️ 餐桌椅组合", value=False)

        st.subheader("🛏️ 3. 卧室空间与睡眠健康配置")
        ROOM_TYPES = ["主卧", "儿子房", "女儿房", "老人房", "次卧/客卧"]
        MATTRESS_TYPES = [
            "高端护脊/独立弹簧（适合主卧/深睡释压）",
            "青少年/儿童护脊床垫（防脊柱弯曲/高支撑）",
            "硬挺护脊/天然棕榈（适合老人/习惯睡硬床）",
            "软硬适中/浮法乳胶层（微环境透气/全家通用）",
            "高性价比舒适床垫"
        ]

        selected_rooms = st.multiselect("选择配置的卧室：", options=ROOM_TYPES, default=["主卧", "次卧/客卧"])

        bedroom_configs = []
        for r_name in selected_rooms:
            with st.expander(f"📌 【{r_name}】尺寸与睡眠健康偏好", expanded=(r_name == "主卧")):
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    hb_limit = st.number_input(
                        f"{r_name} 床头墙允许最大净宽 (米)",
                        min_value=1.2, max_value=4.0,
                        value=2.2 if r_name == "主卧" else 1.8,
                        step=0.05, key=f"hb_{r_name}",
                        help="预留开关插座及两侧通道后的净宽度"
                    )
                    bed_spec = st.selectbox(
                        f"{r_name} 床架规格",
                        ["1.8米床 (180*200cm)", "1.5米床 (150*200cm)", "1.2米床 (120*200cm)"],
                        key=f"bs_{r_name}"
                    )
                with col_b2:
                    need_mat = st.checkbox(f"为{r_name}选配床垫", value=True, key=f"mc_{r_name}")

                    def_idx = 0
                    if "儿子" in r_name or "女儿" in r_name: def_idx = 1
                    elif "老人" in r_name: def_idx = 2
                    elif "次卧" in r_name: def_idx = 4

                    mat_pref = st.selectbox(f"{r_name} 床垫类型", MATTRESS_TYPES, index=def_idx, key=f"mp_{r_name}") if need_mat else "不需要床垫"

                bedroom_configs.append({
                    "room_name": r_name, "hb_limit": f"{hb_limit}米",
                    "bed_spec": bed_spec, "mat_pref": mat_pref
                })

        st.subheader("💰 4. 全屋采购总预算")
        total_budget = st.number_input("采购总预算 (元)", min_value=5000, max_value=500000, value=35000, step=1000)

        st.subheader("✨ 5. 自定义与特殊需求")
        special_tags = st.multiselect(
            "特殊功能与健康偏好（可多选）：",
            options=[
                "电动零重力 / 智能功能沙发",
                "养宠家庭（需防抓擦 / 防粘毛面料）",
                "有婴幼儿（需防磕碰圆角 / 低矮安全设计）",
                "扫地机器人进出（离地高脚 >12cm）",
                "腰椎保护 / 偏硬支撑坐感",
                "去电视化 / 360° 自由组合模块"
            ],
            default=["电动零重力 / 智能功能沙发"]
        )
        custom_notes = st.text_input("补充备注 / 个性化叮嘱：", placeholder="例如：主卧想要头层牛皮床、床垫不要太厚等...")

        st.markdown("---")
        submit_btn = st.button("🚀 一键生成全屋 AI 搭配与睡眠方案", type="primary", use_container_width=True)

    # -------------------- 【右侧列】：AI 方案生成与图集预览区 --------------------
    with col_right:
        st.subheader("📋 专属软装搭配与健康睡眠方案报告")

        if submit_btn:
            if not api_key.startswith("sk-"):
                st.error("❌ 请先在【左侧侧边栏】顶部输入有效的 DeepSeek API Key (以 sk- 开头)！")
                st.stop()

            items_list = []
            if need_sofa: items_list.append("沙发 x 1套")
            if need_chair: items_list.append("单人休闲椅 x 1张")
            if need_table: items_list.append("茶几 x 1个")
            if need_tv: items_list.append("电视柜 x 1个")
            if need_dining: items_list.append("餐桌椅组合 x 1套")

            bd_lines = []
            for bd in bedroom_configs:
                bd_lines.append(f"  - 【{bd['room_name']}】：床规格【{bd['bed_spec']}】，床头墙最大净宽限制【{bd['hb_limit']}】（选定床头宽度绝对不能超过此限制），床垫需求【{bd['mat_pref']}】")
            bd_summary_str = "\n".join(bd_lines)

            all_custom_reqs = special_tags.copy()
            if custom_notes.strip():
                all_custom_reqs.append(f"客户额外叮嘱：{custom_notes.strip()}")
            custom_reqs_str = "；".join(all_custom_reqs) if all_custom_reqs else "无特殊自定义需求"

            system_prompt = f"""
            你是一位顶级的家居软装与健康睡眠主理人。请根据客户录入的尺寸、风格需求、睡眠偏好以及下方提供的封闭数据库，提炼生成一套专业、不超预算的全屋家具与健康睡眠搭配方案。

            【封闭产品数据库（请严格在此范围内选择型号与报价，价格已换算为实际成交价）】：
            {knowledge_base}
            """

            user_prompt = f"""
            客户采购与空间需求资料：

            【硬装与空间几何】：
            - 装修风格偏好：【{style_pref}】（推荐的产品造型、面料材质和配色必须高度契合此风格）
            - 客厅开间/视距：{room_width} 米
            - 沙发背景墙长度：{sofa_wall_len} 米
            - 色彩基调：墙面【{wall_color}】 + 地面【{floor_color}】

            【勾选采购清单】：
            - 客厅/餐厅需求：{'、'.join(items_list) if items_list else '无'}
            - 卧室专项配置：
            {bd_summary_str}

            【自定义与特殊功能需求】：
            {custom_reqs_str}

            【全屋总预算】：
            ¥{total_budget:,} 元人民币

            【🚨 核心搭配算法与生成规则】：
            1. 💰 **严禁超预算**：方案中所有选购产品的【实际成交价】相加总和，绝对不能超过总预算 ¥{total_budget:,} 元。
            2. 🛏️ **床与床垫高度适配逻辑（防踩坑必查）**：
               - 当同时推荐【床架】与【床垫】时，必须校验床垫厚度与床架的适配性。
               - **睡眠高度黄金比例**：床板高度 + 床垫厚度（扣除齐边沉降深度）后的最终【睡眠总高度】建议保持在 **45cm ~ 55cm** 之间（人体工程学最佳起卧高度）。
               - **床屏美观协调**：避免床垫太厚遮挡床屏艺术靠背，或床垫太薄导致床屏下沿悬空。
            3. 💤 **深度融入科学睡眠理念**：
               - 结合不同房间使用者（主卧夫妻/青少年/老人）的生理曲度特点，讲解选配床垫的人体工学支撑（如独立袋装弹簧的零干扰、七区分区释压、天然棕榈对青少年脊柱侧弯的预防、微环境透气呼吸等）。
            4. 📐 **沙发尺寸与气场校验**：
               - 在保证通行过道足够（>80cm）的前提下，**尽量选择偏大、偏宽、体量更强的大气规格（建议沙发长度控制在背景墙长度的 70%~80% 左右）**。
            5. 👑 **主卧倾斜规则**：主卧配置权重提高，配置品质感好的软体床和高端护脊床垫；次卧/儿童房主打性价比与脊柱健康。

            【📜 输出结构要求】：
            一、 空间尺寸与气场碰撞分析（包含过道计算、背景墙比例及床与床垫高度适配校验）
            二、 全屋推荐产品清单与报价明细（包含产品型号、规格尺寸/床垫厚度、实际成交价、推荐理由）
            三、 价格汇总与预算控制说明
            四、 科学睡眠理念与健康生活场景建议（重点阐述床垫人体工学、脊柱健康与深睡释压）
            """

            try:
                client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

                response_box = st.empty()
                full_response = ""

                stream = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2, stream=True
                )

                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_response += content
                        response_box.markdown(full_response + "▌")

                response_box.markdown(full_response)

                # 图集展示
                st.divider()
                st.subheader("🖼️ 推荐产品视觉预览")
                matched_models = set(re.findall(r'[A-Za-z0-9.]+', full_response))

                display_count = 0
                for folder_key, img_dict in images_db.items():
                    if any(m.upper() in folder_key.upper() for m in matched_models if len(m) >= 4):
                        display_count += 1
                        with st.expander(f"📦 视觉预览：{folder_key}", expanded=True):
                            tab_cat, tab_scene, tab_home = st.tabs(["📦 规格/浏览图", "🏡 展厅/场景效果图", "📸 客户入户实景图"])

                            with tab_cat:
                                catalog_imgs = img_dict.get("catalog_images", [])
                                if catalog_imgs:
                                    cols = st.columns(3)
                                    for idx, img_p in enumerate(catalog_imgs[:3]):
                                        with cols[idx % 3]: st.image(img_p, use_container_width=True)
                                else: st.info("暂无规格/浏览图")

                            with tab_scene:
                                scene_imgs = img_dict.get("scene_images", [])
                                if scene_imgs:
                                    cols = st.columns(3)
                                    for idx, img_p in enumerate(scene_imgs[:3]):
                                        with cols[idx % 3]: st.image(img_p, use_container_width=True)
                                else: st.info("暂无展厅/场景效果图")

                            with tab_home:
                                home_imgs = img_dict.get("home_images", []) or img_dict.get("real_images", [])
                                if home_imgs:
                                    cols = st.columns(3)
                                    for idx, img_p in enumerate(home_imgs[:3]):
                                        with cols[idx % 3]: st.image(img_p, use_container_width=True)
                                else: st.info("📸 暂无客户入户实景图")

                if display_count == 0:
                    st.info("💡 提示：未能根据方案自动匹配到本地图片，请检查 `product_images.json` 里的型号对应路径。")

            except Exception as e:
                st.error(f"❌ DeepSeek API 调用失败: {e}")
        else:
            st.info("👈 请在左侧填写客户的需求和预算，点击【🚀 一键生成全屋 AI 搭配与睡眠方案】。")


# =========================================================================
# 【Tab 2】：导购全品类速查助手（床/床垫/沙发/软装）
# =========================================================================
with main_tab2:
    st.subheader("🔍 导购全品类速查助手（床 / 床垫 / 沙发）")
    st.caption("⚡ 专门面向线下导购：随手输入要求，精准匹配床架、床垫厚度适配、沙发尺寸及睡眠健康偏好！")

    col_q1, col_q2 = st.columns([3, 1])
    with col_q1:
        guide_query = st.text_input(
            "请输入查询条件：",
            placeholder="例如：1.8米皮床，推荐适配厚度22-25cm的独立弹簧护脊床垫，总预算7000内",
            key="guide_query_input"
        )
    with col_q2:
        st.write(" ")
        st.write(" ")
        search_btn = st.button("🔎 立即检索库", type="primary", use_container_width=True)

    st.caption("💡 导购高频快捷检索推荐：")
    col_e1, col_e2, col_e3, col_e4 = st.columns(4)
    if col_e1.button("📌 1.8米床 + 适配床垫组合"):
        guide_query = "1.8米主卧软体床，推荐匹配高度适中的护脊床垫，一套预算8000以内"
        search_btn = True
    if col_e2.button("📌 青少年防弯曲护脊床垫"):
        guide_query = "适合青少年或儿童的1.5米护脊床垫，透气环保硬质支撑"
        search_btn = True
    if col_e3.button("📌 3米左右 1万内 意式沙发"):
        guide_query = "尺寸3米左右，价格10000以内，意式风格真皮或科技布沙发"
        search_btn = True
    if col_e4.button("📌 独立弹簧零干扰静音床垫"):
        guide_query = "主卧独立袋装弹簧床垫，抗干扰抗震动，适合浅睡眠人群"
        search_btn = True

    st.markdown("---")

    if search_btn and guide_query:
        if not api_key.startswith("sk-"):
            st.error("❌ 请先在【左侧侧边栏】顶部输入有效的 DeepSeek API Key (以 sk- 开头)！")
            st.stop()

        guide_system_prompt = f"""
        你是一位精准的家居与睡眠产品检索助手。请严格根据导购提出的要求（支持床架、床垫厚度适配、睡眠健康需求、沙发尺寸、价格与风格），从封闭数据库中检索并列出符合条件的最佳产品。

        【封闭产品数据库】：
        {knowledge_base}

        【输出要求】：
        1. 简洁清晰：直接列出符合条件的产品列表。
        2. 若涉及【床+床垫搭配】：必须明确说明**床架沉降深度与床垫厚度的适配性**（确保睡眠总高度 45-55cm，且不遮挡床屏）。
        3. 融入【健康睡眠卖点】：列出床垫或软体床在脊柱支撑、独立抗干扰、透气性等方面的睡眠理念。
        4. 每项包含：【型号与名称】、【规格尺寸/厚度】、【实际成交价】、【睡眠与软装推荐理由】。
        """

        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

            with st.spinner("🔍 正在从产品库中检索比对..."):
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": guide_system_prompt},
                        {"role": "user", "content": f"导购检索要求：{guide_query}"}
                    ],
                    temperature=0.1
                )
                search_result = response.choices[0].message.content

            st.markdown("### 📋 检索到匹配的产品及适配方案：")
            st.markdown(search_result)

            st.markdown("---")
            st.markdown("### 🖼️ 匹配产品图片直达展示：")

            matched_models = set(re.findall(r'[A-Za-z0-9.]+', search_result))
            display_count = 0

            for folder_key, img_dict in images_db.items():
                if any(m.upper() in folder_key.upper() for m in matched_models if len(m) >= 4):
                    display_count += 1
                    st.markdown(f"#### 📦 {folder_key}")

                    tab_cat, tab_scene, tab_home = st.tabs(["📦 规格/浏览图", "🏡 展厅/场景效果图", "📸 客户入户实景图"])

                    with tab_cat:
                        catalog_imgs = img_dict.get("catalog_images", [])
                        if catalog_imgs:
                            cols = st.columns(3)
                            for idx, img_p in enumerate(catalog_imgs[:3]):
                                with cols[idx % 3]: st.image(img_p, use_container_width=True)
                        else: st.info("暂无规格/浏览图")

                    with tab_scene:
                        scene_imgs = img_dict.get("scene_images", [])
                        if scene_imgs:
                            cols = st.columns(3)
                            for idx, img_p in enumerate(scene_imgs[:3]):
                                with cols[idx % 3]: st.image(img_p, use_container_width=True)
                        else: st.info("暂无展厅/场景效果图")

                    with tab_home:
                        home_imgs = img_dict.get("home_images", []) or img_dict.get("real_images", [])
                        if home_imgs:
                            cols = st.columns(3)
                            for idx, img_p in enumerate(home_imgs[:3]):
                                with cols[idx % 3]: st.image(img_p, use_container_width=True)
                        else: st.info("📸 暂无客户入户实景图")

            if display_count == 0:
                st.info("💡 提示：未能根据检索文本找到匹配的图片，请检查 `product_images.json` 映射。")

        except Exception as e:
            st.error(f"❌ 检索失败: {e}")
