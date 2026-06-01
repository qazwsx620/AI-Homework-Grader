"""

core/image_utils.py — 批改结果图像绘制模块
负责：将大模型返回的批改 JSON 渲染为图片，支持 LaTeX 公式
清洗、自动换行、动态画布高度，输出 base64 数据 URI

"""
import io
import os
import base64
import re
import unicodedata
from PIL import Image, ImageDraw, ImageFont

# 配色方案
THEME_COLOR = {
    "title_text": "#1E40AF",
    "qid_text": "#1E40AF",
    "ans_text": "#D97706",
    "desc_text": "#1F2937",
    "divider_line": "#E5E7EB",
    "title_bg": "#F3F4F6",
    "canvas_bg": "#FFFFFF"
}

# 双栏布局尺寸
LEFT_RATIO = 0.62                  # 左栏（文字）占比
RIGHT_RATIO = 0.38                 # 右栏（图片）占比
CANVAS_WIDTH = 1600
LEFT_WIDTH = int(CANVAS_WIDTH * LEFT_RATIO)
RIGHT_WIDTH = CANVAS_WIDTH - LEFT_WIDTH

PAGE_PADDING = 30
ROW_SPACING = 20
TITLE_FONT_SIZE = 34
CONTENT_FONT_SIZE = 26
TITLE_BAR_HEIGHT = 68


def sanitize_text(text):
    """
    文本清洗：处理LaTeX公式、乱码
    处理顺序：先替换带反斜杠的命令，再去掉残留反斜杠
    """
    if not isinstance(text, str):
        text = str(text)

    text = text.replace('\xa0', ' ').replace('\u3000', ' ').replace('\u200b', '')
    text = text.replace('□', '→')
    text = text.replace('\\left(', '(').replace('\\right)', ')')

    # LaTeX 命令替换
    text = re.sub(r'\\frac\s*\{([^}]+)\}\s*\{([^}]+)\}', r'(\1)/(\2)', text)
    text = re.sub(r'\\sqrt\s*\{([^}]+)\}', r'√\1', text)
    text = re.sub(r'\\sqrt\s*\(([^)]+)\)', r'√(\1)', text)
    text = re.sub(r'\\sqrt([a-zA-Z0-9.+*/-]+)', r'√\1', text)
    text = re.sub(r'\\(le|leq)', r'≤', text)
    text = re.sub(r'\\(ge|geq)', r'≥', text)
    text = re.sub(r'\\neq', r'≠', text)
    text = re.sub(r'\\times', r'×', text)
    text = re.sub(r'\\div', r'÷', text)
    text = re.sub(r'\\pi', r'π', text)

    # 上标
    sup_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}

    def replace_sup(match):
        base = match.group(1)
        exp = match.group(2)
        exp_sup = ''.join([sup_map.get(c, c) for c in exp])
        return f"{base}{exp_sup}"

    text = re.sub(r'(\w+)\^(\d+)', replace_sup, text)

    text = text.replace('\\', '').replace('  ', ' ')
    text = re.sub(r'frac\s*\{([^}]+)\}\s*\{([^}]+)\}', r'(\1)/(\2)', text)

    # 过滤表情符号
    text = unicodedata.normalize('NFKC', text)
    valid_chars = []
    for char in text:
        char_code = ord(char)
        if 0x1F300 <= char_code <= 0x1FAFF or 0x2600 <= char_code <= 0x27BF:
            continue
        valid_chars.append(char)

    return "".join(valid_chars)


def wrap_text(text, font, max_width):
    """智能自动换行：优先按空格拆分，超宽长段落实按字符切分"""
    line_list = []
    paragraph_list = text.split('\n')

    for paragraph in paragraph_list:
        if not paragraph:
            line_list.append("")
            continue

        indent = "  " if re.match(r'^\d+\.?\s', paragraph) else ""
        current_line = indent
        words = re.split(r'(\s|×|/|√|\+|\-|\*)', paragraph)
        words = [w for w in words if w.strip() != '']

        for word in words:
            try:
                single_word_w = font.getbbox(word)[2]
            except AttributeError:
                single_word_w = font.getsize(word)[0]

            if single_word_w > max_width:
                for char in word:
                    temp_line = current_line + char
                    try:
                        char_w = font.getbbox(temp_line)[2]
                    except AttributeError:
                        char_w = font.getsize(temp_line)[0]
                    if char_w <= max_width:
                        current_line = temp_line
                    else:
                        line_list.append(current_line.strip())
                        current_line = indent + char
                continue

            temp_line = current_line + word
            try:
                text_width = font.getbbox(temp_line)[2]
            except AttributeError:
                text_width = font.getsize(temp_line)[0]

            if text_width <= max_width:
                current_line = temp_line
            else:
                line_list.append(current_line.strip())
                current_line = indent + word

        if current_line.strip():
            line_list.append(current_line.strip())

    return line_list


def load_font_resource():
    """加载支持所有数学符号的中文字体（优先微软雅黑）"""
    title_font = None
    content_font = None

    win_font_dir = "C:/Windows/Fonts"
    font_candidate = [
        os.path.join(win_font_dir, "msyh.ttc"),
        os.path.join(win_font_dir, "msyhbd.ttc"),
        os.path.join(win_font_dir, "simhei.ttf"),
        os.path.join(win_font_dir, "simsun.ttc"),
        "msyh.ttc",
        "simhei.ttf",
        "Arial Unicode.ttf",
        "PingFang.ttc",
    ]

    for font_name in font_candidate:
        try:
            title_font = ImageFont.truetype(font_name, TITLE_FONT_SIZE)
            content_font = ImageFont.truetype(font_name, CONTENT_FONT_SIZE)
            break
        except (IOError, OSError):
            continue

    if not title_font:
        title_font = ImageFont.load_default(size=TITLE_FONT_SIZE)
    if not content_font:
        content_font = ImageFont.load_default(size=CONTENT_FONT_SIZE)

    return title_font, content_font


def format_feedback_text(feedback_text):
    """结构化批改内容：题号/答案/解析分块更清晰"""
    output_lines = []
    if isinstance(feedback_text, list):
        for item in feedback_text:
            if isinstance(item, dict):
                qid = item.get("题号", "未知")
                judge_res = item.get("正误判断", "")
                std_ans = item.get("正确答案", "")
                solve_method = item.get("正确解法", "")

                output_lines.append(sanitize_text(f"题号 {qid}：{judge_res}"))
                output_lines.append("")

                output_lines.append(sanitize_text(f"标准答案：{std_ans}"))
                output_lines.append("")

                if solve_method:
                    output_lines.append(sanitize_text("解题解析："))
                    output_lines.append("  " + sanitize_text(solve_method))

                output_lines.append("----分割线----")
                output_lines.append("")

            else:
                output_lines.append(sanitize_text(str(item)))
                output_lines.append("")

    elif isinstance(feedback_text, str):
        clean_str = sanitize_text(feedback_text)
        output_lines.extend(clean_str.split("\n"))
    else:
        output_lines.append(sanitize_text(str(feedback_text)))

    return output_lines


def draw_result_on_image(image_data, result_data):
    """
    双栏布局渲染批改结果：
    左栏：批改文本      右栏：
    题号/答案/解析     原图
    自动换行动态高度      (缩小)
    """
    # 加载原始图片
    origin_img = Image.open(io.BytesIO(image_data)).convert("RGB")

    # 缩放原图以适应右栏
    right_img_max_w = RIGHT_WIDTH - PAGE_PADDING * 2
    right_img_max_h = 520
    scale = min(right_img_max_w / origin_img.width, right_img_max_h / origin_img.height, 1.0)
    right_img_w = int(origin_img.width * scale)
    right_img_h = int(origin_img.height * scale)
    try:
        right_img = origin_img.resize((right_img_w, right_img_h), Image.Resampling.LANCZOS)
    except AttributeError:
        right_img = origin_img.resize((right_img_w, right_img_h))

    # 加载字体
    title_font, content_font = load_font_resource()

    # 空值检查
    if result_data is None:
        result_data = {"feedback": "批改结果为空，请重试"}

    # 格式化文本
    raw_feedback = result_data.get("feedback", "")
    text_lines = format_feedback_text(raw_feedback)
    max_text_width = LEFT_WIDTH - PAGE_PADDING * 2

    # 计算所有换行后的行
    wrap_all_lines = []
    for line in text_lines:
        if "分割线" in line:
            wrap_all_lines.append(line)
            continue
        if not line.strip():
            wrap_all_lines.append("")
            continue
        wrap_sub_lines = wrap_text(line, content_font, max_text_width)
        wrap_all_lines.extend(wrap_sub_lines)

    # 如果没有任何批改文本，显示提示信息
    has_meaningful = any(line.strip() and "分割线" not in line for line in wrap_all_lines)
    if not has_meaningful:
        wrap_all_lines = ["暂无批改结果，请检查图片内容或重新尝试"]

    # 动态计算左栏文本高度
    total_text_height = 0
    for line in wrap_all_lines:
        if "分割线" in line:
            total_text_height += 20
            continue
        if not line.strip():
            total_text_height += 8
            continue
        try:
            line_h = content_font.getbbox(line)[3] - content_font.getbbox(line)[1]
        except AttributeError:
            line_h = content_font.getsize(line)[1]
        total_text_height += line_h + ROW_SPACING

    # 画布高度 = 标题栏 + 文本内容 + 底部留白，至少能放下右栏图片
    left_panel_height = max(TITLE_BAR_HEIGHT + total_text_height + PAGE_PADDING * 3,
                            right_img_h + PAGE_PADDING * 3)
    canvas_height = max(left_panel_height, 500)

    # 创建画布
    canvas = Image.new("RGB", (CANVAS_WIDTH, canvas_height), THEME_COLOR["canvas_bg"])
    draw_tool = ImageDraw.Draw(canvas)

    # ── 绘制右栏：原图 ──
    right_img_x = LEFT_WIDTH + (RIGHT_WIDTH - right_img_w) // 2
    right_img_y = PAGE_PADDING
    canvas.paste(right_img, (right_img_x, right_img_y))

    # 给图片加一个浅色边框
    draw_tool.rectangle(
        [right_img_x - 2, right_img_y - 2, right_img_x + right_img_w + 2, right_img_y + right_img_h + 2],
        outline="#D1D5DB", width=1
    )

    # ── 绘制左栏：标题栏 ──
    draw_tool.rectangle([(0, 0), (LEFT_WIDTH, TITLE_BAR_HEIGHT)], fill=THEME_COLOR["title_bg"])
    title_content = "AI 智能作业批改结果"
    try:
        title_w = title_font.getbbox(title_content)[2]
    except AttributeError:
        title_w = title_font.getsize(title_content)[0]
    title_x = LEFT_WIDTH // 2 - title_w // 2
    draw_tool.text((title_x, 14), title_content, font=title_font, fill=THEME_COLOR["title_text"])

    # 左右栏之间的分割线
    draw_tool.line([(LEFT_WIDTH, 0), (LEFT_WIDTH, canvas_height)], fill="#E5E7EB", width=1)

    # ── 绘制左栏：批改文本 ──
    current_y = TITLE_BAR_HEIGHT + PAGE_PADDING
    canvas_bottom = canvas_height - PAGE_PADDING

    for show_line in wrap_all_lines:
        if current_y > canvas_bottom - 25:
            break

        if not show_line.strip():
            current_y += 8
            continue

        if "分割线" in show_line:
            draw_tool.line([(PAGE_PADDING, current_y + 10),
                            (LEFT_WIDTH - PAGE_PADDING, current_y + 10)],
                           fill=THEME_COLOR["divider_line"], width=1)
            current_y += 20
            continue

        if "题号" in show_line:
            text_color = THEME_COLOR["qid_text"]
        elif "标准答案" in show_line:
            text_color = THEME_COLOR["ans_text"]
        else:
            text_color = THEME_COLOR["desc_text"]

        draw_tool.text((PAGE_PADDING, current_y), show_line, font=content_font, fill=text_color)

        try:
            single_h = content_font.getbbox(show_line)[3] - content_font.getbbox(show_line)[1]
        except AttributeError:
            single_h = content_font.getsize(show_line)[1]
        current_y += single_h + ROW_SPACING

    # 输出 base64
    output_buffer = io.BytesIO()
    canvas.save(output_buffer, format="JPEG", quality=95)
    base64_img = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{base64_img}"
