"""
api/grade_api.py — 作业批改模块（Blueprint: grade_bp）
负责：接收作业图片 → OpenCV 预处理 → OCR → 大模型批改 →
绘制批改结果图 → 返回结果
"""
import json
import base64
import traceback
from flask import Blueprint, request, jsonify
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

    try:
        image_bytes = file.read()

        print("正在使用OpenCV进行图像自动切割与增强")
        enhanced_bytes = scan_and_enhance_document(image_bytes)

        print("正在进行OCR识别")
        paper_text = extract_text(enhanced_bytes)

        if not paper_text or "OCR识别失败" in paper_text or "运行异常" in paper_text:
            error_detail = paper_text if paper_text else "OCR未返回任何文字"
            print(f"OCR识别失败，详情: {error_detail}")
            return jsonify({'status': 'error', 'message': error_detail}), 500

        print("正在调用大模型进行批改")
        result = correction_work(paper_text)

        if result is None:
            return jsonify({'status': 'error', 'message': 'AI批改失败，返回结果为空'}), 500

        print("正在绘制批改结果")
        result_image = draw_result_on_image(image_bytes, result)

        return jsonify({
            'status': 'success',
            'message': '批改成功',
            'image_path': result_image,
            'ocr_text': paper_text,
            'feedback_json': json.dumps(result, ensure_ascii=False),
            'filename': file.filename or '作业图片.jpg',
            'original_image': f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
