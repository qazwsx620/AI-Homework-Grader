"""
api/grade_api.py — 作业批改模块（Blueprint: grade_bp）
负责：接收作业图片 → OpenCV 预处理 → 本机图床中转 → OCR → 大模型批改 → 绘制批改结果图
"""
import json
import base64
import traceback
import os
import uuid
import gc
from flask import Blueprint, request, jsonify
from api.ocr_api import extract_text
from core.image_utils import draw_result_on_image
from core.llm_api import correction_work
from core.scanner import scan_and_enhance_document

grade_bp = Blueprint('grade', __name__)

@grade_bp.route('/api/grade', methods=['POST'])
def api_grade():
    """
    核心批改接口：本机公网图床直传升级版
    """
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': '没有找到图片'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '没有选择文件'}), 400

    temp_filepath = None
    try:
        image_bytes = file.read()

        print("正在使用OpenCV进行图像自动切割与增强")
        enhanced_bytes = scan_and_enhance_document(image_bytes)

        # ==========================================
        # 把服务器当做公网图床！
        # ==========================================
        os.makedirs("static", exist_ok=True)
        temp_filename = f"ocr_temp_{uuid.uuid4().hex}.jpg"
        temp_filepath = os.path.join("static", temp_filename)

        # 将 OpenCV 处理好的图片暂时存在自己服务器的 static 文件夹中
        with open(temp_filepath, "wb") as f:
            f.write(enhanced_bytes)

        # 利用 Flask 动态生成当前服务器的真实公网地址
        # (例如: http://11.22.33.44:5000/static/ocr_temp_xxx.jpg)
        my_public_url = request.host_url + f"static/{temp_filename}"
        print(f"本机图床链接已生成: {my_public_url}")

        print("正在调用夸克进行OCR识别")
        # 把自己的公网 URL 传给夸克，彻底跳过不稳定的海外免费图床！
        paper_text = extract_text(enhanced_bytes, public_url=my_public_url)

        # 阅后即焚：夸克一旦识别完，立刻删掉刚才保存在服务器上的图片，防止硬盘爆满
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

        if not paper_text or "OCR识别失败" in paper_text or "运行异常" in paper_text:
            error_detail = paper_text if paper_text else "OCR未返回任何文字"
            print(f"OCR识别失败，详情: {error_detail}")
            return jsonify({'status': 'error', 'message': error_detail}), 500

        print("正在调用大模型进行智能批改")
        result = correction_work(paper_text)

        if result is None:
            return jsonify({'status': 'error', 'message': 'AI批改失败，返回结果为空'}), 500

        print("正在绘制批改结果图")
        result_image = draw_result_on_image(image_bytes, result)

        # 强制释放内存，防止 OOM
        del image_bytes
        del enhanced_bytes
        gc.collect()

        return jsonify({
            'status': 'success',
            'message': '批改成功',
            'image_path': result_image,
            'ocr_text': paper_text,
            'feedback_json': json.dumps(result, ensure_ascii=False),
            'filename': file.filename or '作业图片.jpg',
            'original_image': f"data:image/jpeg;base64,{base64.b64encode(file.read()).decode('utf-8')}"
        })

    except Exception as e:
        traceback.print_exc()
        # 发生异常报错时，也要确保临时图片被删掉
        if temp_filepath and os.path.exists(temp_filepath):
            try: os.remove(temp_filepath)
            except: pass
        gc.collect()
        return jsonify({'status': 'error', 'message': str(e)}), 500
