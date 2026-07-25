"""
整理 sofa_products 下各产品文件夹为标准结构：
  PPT/        - 产品培训课件
  浏览图/      - 产品浏览图/规格图
  场景图/      - 场景实拍图
  入户实景图/   - 入户实景照片
"""
import os, glob, shutil

BASE = "sofa_products"
STANDARD_DIRS = ["PPT", "浏览图", "场景图", "入户实景图"]

def ensure_dirs(product_path):
    for d in STANDARD_DIRS:
        os.makedirs(os.path.join(product_path, d), exist_ok=True)

def classify_file(rel_path: str) -> str | None:
    """判断文件应归入哪个标准目录，返回目录名或 None（跳过）"""
    parts = rel_path.replace("\\", "/").split("/")
    filename = parts[-1].lower()
    full_lower = rel_path.lower()

    # PPT/PDF 文件
    if filename.endswith(".pptx") or filename.endswith(".ppt") or filename.endswith(".pdf") or filename.endswith(".docx") or filename.endswith(".xlsx"):
        return "PPT"

    # 图片文件
    if not any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
        return None

    # 已在标准目录中 → 跳过
    for std in STANDARD_DIRS:
        if std in parts:
            return None

    # 根据原路径关键词分类
    # 优先检查：入户实景
    if "入户实景" in full_lower or "入户" in full_lower:
        return "入户实景图"
    # 场景图：路径含场景/实拍/scene
    if "场景" in full_lower or "实拍" in full_lower or "scene" in full_lower:
        return "场景图"
    # 浏览图：路径含浏览
    if "浏览" in full_lower:
        return "浏览图"

    # 剩余图片默认归入浏览图
    return "浏览图"


def main():
    products = sorted([p for p in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, p))])

    for prod in products:
        prod_path = os.path.join(BASE, prod)
        ensure_dirs(prod_path)
        moved = 0

        # 遍历所有文件
        for root, dirs, files in os.walk(prod_path):
            # 跳过标准目录本身
            rel_root = os.path.relpath(root, prod_path)
            if rel_root == ".":
                pass  # 根目录
            elif rel_root.split(os.sep)[0] in STANDARD_DIRS:
                continue  # 已在标准目录内，跳过

            for f in files:
                src = os.path.join(root, f)
                rel_file = os.path.relpath(src, prod_path)
                target_dir = classify_file(rel_file)
                if not target_dir:
                    continue

                dst = os.path.join(prod_path, target_dir, f)
                # 避免覆盖已有文件
                if os.path.exists(dst):
                    base, ext = os.path.splitext(f)
                    dst = os.path.join(prod_path, target_dir, f"{base}_dup{ext}")

                shutil.move(src, dst)
                moved += 1
                print(f"  {prod}: {f} → {target_dir}/")

        if moved == 0:
            print(f"  {prod}: 无需移动")

    # 清理空目录
    print("\n清理空目录...")
    for prod in products:
        prod_path = os.path.join(BASE, prod)
        for root, dirs, files in os.walk(prod_path, topdown=False):
            if root == prod_path:
                continue
            # 只删除非标准目录的空文件夹
            rel = os.path.relpath(root, prod_path)
            if rel.split(os.sep)[0] in STANDARD_DIRS:
                continue
            try:
                os.rmdir(root)
                print(f"  删除空目录: {os.path.relpath(root, BASE)}")
            except OSError:
                pass  # 目录非空

    print("\n整理完成！")


if __name__ == "__main__":
    main()
