"""
api/grade_api.py — 作业批改模块（Blueprint: grade_bp）
负责：接收作业图片 → OpenCV 预处理 → OCR → 大模型批改 →
绘制批改结果图 → 返回结果
"""
import os
import json
import base64
import uuid
from flask import Blueprint, request, jsonify, session, current_app
from api.ocr_api import extract_text
from core.image_utils import draw_result_on_image
from core.llm_api import correction_work
from core.scanner import scan_and_enhance_document

grade_bp = Blueprint('grade', __name__)


@grade_bp.route('/api/grade', methods=['POST'])
def api_grade():
    """
    核心批改接口：
    1. 接收上传的作业图片
    2. OpenCV 自动裁剪与增强
    3. 夸克 OCR 识别文本
    4. 大模型批改
    5. 绘制批改结果图（base64）
    """
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': '没有找到图片'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '没有选择文件'}), 400

    os.makedirs("temp", exist_ok=True)
    temp_path = os.path.join("temp", "temp_upload.jpg")

    try:
        file.save(temp_path)

        with open(temp_path, "rb") as f:
            image_bytes = f.read()

        print("正在使用OpenCV进行图像自动切割与增强")
        enhanced_bytes = scan_and_enhance_document(image_bytes)

        with open(temp_path, "wb") as f:
            f.write(enhanced_bytes)

        print("正在进行OCR识别")
        paper_text = extract_text(image_bytes)

        if not paper_text or "OCR识别失败" in paper_text:
            return jsonify({'status': 'error', 'message': 'OCR识别失败'}), 500

        print("正在调用大模型进行批改")
        result = correction_work(paper_text)

        print("正在绘制批改结果")
        annotated_image_path = draw_result_on_image(image_bytes, result)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        return jsonify({
            'status': 'success',
            'message': '批改成功',
            'image_path': annotated_image_path,
            'ocr_text': paper_text,
            'feedback_json': json.dumps(result, ensure_ascii=False),
            'filename': file.filename or '作业图片.jpg',
            'original_image': f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return jsonify({'status': 'error', 'message': str(e)}), 500
