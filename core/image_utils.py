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
    "title_text": "#1E40AF",  # 标题深蓝色
    "qid_text": "#1E40AF",  # 题号蓝色
    "ans_text": "#D97706",  # 标准答案橙色
    "desc_text": "#1F2937",  # 解析纯黑色
    "divider_line": "#E5E7EB",  # 分割线浅灰
    "title_bg": "#F3F4F6",  # 标题栏背景
    "canvas_bg": "#FFFFFF"  # 画布底色
}

# 排版尺寸
PAGE_PADDING = 30
ROW_SPACING = 18
TITLE_FONT_SIZE = 30
CONTENT_FONT_SIZE = 24
SAFE_MARGIN = 100



def sanitize_text(text):
    """
    文本清洗：处理LaTeX公式、乱码
    处理顺序：先替换带反斜杠的命令，再去掉残留反斜杠
    """
    if not isinstance(text, str):
        text = str(text)

    # 1. 基础清理
    text = text.replace('\xa0', ' ').replace('\u3000', ' ').replace('\u200b', '')
    text = text.replace('□', '→')
    text = text.replace('\\left(', '(').replace('\\right)', ')')  # 去掉LaTeX括号

    # 2. 先处理带反斜杠的LaTeX命令（在去掉反斜杠之前）
    # 2.1 处理分数 \frac{分子}{分母} → (分子)/(分母)
    text = re.sub(r'\\frac\s*\{([^}]+)\}\s*\{([^}]+)\}', r'(\1)/(\2)', text)
    # 2.2 处理根号
    text = re.sub(r'\\sqrt\s*\{([^}]+)\}', r'√\1', text)
    text = re.sub(r'\\sqrt\s*\(([^)]+)\)', r'√(\1)', text)
    # 将 - 移到字符集末尾，避免非法范围错误
    text = re.sub(r'\\sqrt([a-zA-Z0-9.+*/-]+)', r'√\1', text)
    # 2.3 处理其他数学符号
    text = re.sub(r'\\(le|leq)', r'≤', text)
    text = re.sub(r'\\(ge|geq)', r'≥', text)
    text = re.sub(r'\\neq', r'≠', text)
    text = re.sub(r'\\times', r'×', text)
    text = re.sub(r'\\div', r'÷', text)
    text = re.sub(r'\\pi', r'π', text)

    # 3. 处理上标
    # 格式：数字/字母^数字 → 数字/字母⁴（用Unicode上标）
    sup_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}

    def replace_sup(match):
        base = match.group(1)
        exp = match.group(2)
        # 转换为上标字符
        exp_sup = ''.join([sup_map.get(c, c) for c in exp])
        return f"{base}{exp_sup}"

    text = re.sub(r'(\w+)\^(\d+)', replace_sup, text)

    # 4. 去掉残留的反斜杠（在所有正则处理之后）
    text = text.replace('\\', '').replace('  ', ' ')

    # 5. 处理无反斜杠的frac残留
    text = re.sub(r'frac\s*\{([^}]+)\}\s*\{([^}]+)\}', r'(\1)/(\2)', text)

    # 6. 字符标准化，过滤表情符号
    text = unicodedata.normalize('NFKC', text)
    valid_chars = []
    for char in text:
        char_code = ord(char)
        # 仅过滤表情/图标，保留数学符号区（0x2200~0x22FF）
        if 0x1F300 <= char_code <= 0x1FAFF or 0x2600 <= char_code <= 0x27BF:
            continue
        valid_chars.append(char)

    return "".join(valid_chars)


def wrap_text(text, font, max_width):
    """
    智能自动换行：优先按空格拆分，对中文无空格长段落实按字符切分
    确保所有文字都不会超出最大宽度，解决解析文本溢出面板的问题
    """
    line_list = []
    paragraph_list = text.split('\n')

    for paragraph in paragraph_list:
        if not paragraph:
            line_list.append("")
            continue

        # 识别列表项（如1. 2. 3. 或1 2 3），自动添加缩进
        indent = "  " if re.match(r'^\d+\.?\s', paragraph) else ""
        current_line = indent
        # 优先按空格拆分，避免拆断公式，同时允许在×、/、√后换行
        words = re.split(r'(\s|×|/|√|\+|\-|\*)', paragraph)
        words = [w for w in words if w.strip() != '']  # 过滤空字符串

        for word in words:
            # 检查单个word是否已超过最大宽度（中文长段落无空格时）
            try:
                single_word_w = font.getbbox(word)[2]
            except AttributeError:
                single_word_w = font.getsize(word)[0]

            if single_word_w > max_width:
                # 逐字符拆分：确保每个字符都不会溢出
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

            # 正常单词：尝试追加
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

    # Windows 系统字体目录
    win_font_dir = "C:/Windows/Fonts"
    font_candidate = [
        os.path.join(win_font_dir, "msyh.ttc"),       # 微软雅黑
        os.path.join(win_font_dir, "msyhbd.ttc"),     # 微软雅黑粗体
        os.path.join(win_font_dir, "simhei.ttf"),      # 黑体
        os.path.join(win_font_dir, "simsun.ttc"),      # 宋体
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

    # 兜底字体
    if not title_font:
        title_font = ImageFont.load_default(size=TITLE_FONT_SIZE)
    if not content_font:
        content_font = ImageFont.load_default(size=CONTENT_FONT_SIZE)

    return title_font, content_font


def format_feedback_text(feedback_text):
    """
    结构化批改内容：题号/答案/解析分块更清晰
    解决文本拥挤问题，添加更多空行分隔
    """
    output_lines = []
    if isinstance(feedback_text, list):
        for item in feedback_text:
            if isinstance(item, dict):
                qid = item.get("题号", "未知")
                judge_res = item.get("正误判断", "")
                std_ans = item.get("正确答案", "")
                solve_method = item.get("正确解法", "")

                # 题号+正误
                output_lines.append(sanitize_text(f"题号 {qid}：{judge_res}"))
                output_lines.append("")  # 空行分隔

                # 标准答案
                output_lines.append(sanitize_text(f"标准答案：{std_ans}"))
                output_lines.append("")  # 空行分隔

                # 解题解析（保留原换行，自动处理列表缩进）
                if solve_method:
                    output_lines.append(sanitize_text("解题解析："))
                    output_lines.append("  " + sanitize_text(solve_method))  # 解析整体缩进，更像老师批注

                # 分割线（仅在题目之间添加）
                output_lines.append("----分割线----")
                output_lines.append("")  # 分割线后空行

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
    批改结果绘制：增大安全边距+优化高度计算，解决文本截断
    """
    # 读取原始图片
    origin_img = Image.open(io.BytesIO(image_data)).convert("RGB")

    # 统一缩放宽度
    fixed_width = 1200
    scale_ratio = fixed_width / origin_img.width
    fixed_height = int(origin_img.height * scale_ratio)
    try:
        origin_img = origin_img.resize((fixed_width, fixed_height), Image.Resampling.LANCZOS)
    except AttributeError:
        origin_img = origin_img.resize((fixed_width, fixed_height))

    # 加载字体
    title_font, content_font = load_font_resource()
    
    # 空值检查：防止 result_data 为 None
    if result_data is None:
        result_data = {"feedback": "批改结果为空，请重试"}
    
    raw_feedback = result_data.get("feedback", "")
    text_lines = format_feedback_text(raw_feedback)
    max_text_width = fixed_width - PAGE_PADDING * 2

    # 计算所有文本行（处理换行）
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

    # 动态计算画布高度（增大安全边距，防止截断）
    total_text_height = 0
    for line in wrap_all_lines:
        if "分割线" in line:
            total_text_height += 25
            continue
        if not line.strip():
            total_text_height += 10
            continue
        try:
            line_h = content_font.getbbox(line)[3] - content_font.getbbox(line)[1]
        except AttributeError:
            line_h = content_font.getsize(line)[1]
        total_text_height += line_h + ROW_SPACING

    # 增大面板高度，避免底部文本被截断
    panel_height = 70 + total_text_height + PAGE_PADDING * 2 + SAFE_MARGIN
    total_canvas = Image.new("RGB", (fixed_width, fixed_height + panel_height), THEME_COLOR["canvas_bg"])
    total_canvas.paste(origin_img, (0, 0))
    draw_tool = ImageDraw.Draw(total_canvas)

    # 绘制标题栏
    title_start_y = fixed_height
    draw_tool.rectangle([(0, title_start_y), (fixed_width, title_start_y + 70)], fill=THEME_COLOR["title_bg"])
    title_content = "AI智能作业批改结果"
    try:
        title_w = title_font.getbbox(title_content)[2]
    except AttributeError:
        title_w = title_font.getsize(title_content)[0]
    title_x = fixed_width // 2 - title_w // 2
    draw_tool.text((title_x, title_start_y + 18), title_content, font=title_font, fill=THEME_COLOR["title_text"])

    # 逐行绘制批改内容（优化排版，不截断，超限自动终止）
    current_y = title_start_y + 70 + PAGE_PADDING
    canvas_bottom = fixed_height + panel_height - PAGE_PADDING
    for show_line in wrap_all_lines:
        # 安全边界：剩余空间不足一行时停止绘制，防止文字溢出画布
        if current_y > canvas_bottom - 30:
            break

        if not show_line.strip():
            current_y += 10
            continue

        # 绘制分割线（浅灰色，不突兀）
        if "分割线" in show_line:
            draw_tool.line([(PAGE_PADDING, current_y + 12), (fixed_width - PAGE_PADDING, current_y + 12)],
                           fill=THEME_COLOR["divider_line"], width=2)
            current_y += 25
            continue

        # 按行类型设置颜色
        if "题号" in show_line:
            text_color = THEME_COLOR["qid_text"]
        elif "标准答案" in show_line:
            text_color = THEME_COLOR["ans_text"]
        else:
            text_color = THEME_COLOR["desc_text"]

        # 绘制文字（含数学符号，不截断）
        draw_tool.text((PAGE_PADDING, current_y), show_line, font=content_font, fill=text_color)

        # 更新纵坐标
        try:
            single_h = content_font.getbbox(show_line)[3] - content_font.getbbox(show_line)[1]
        except AttributeError:
            single_h = content_font.getsize(show_line)[1]
        current_y += single_h + ROW_SPACING

    # 图片转base64输出
    output_buffer = io.BytesIO()
    total_canvas.save(output_buffer, format="JPEG", quality=90)
    base64_img = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{base64_img}"