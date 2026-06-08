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
import threading
from flask import Blueprint, request, jsonify, current_app
from api.ocr_api import extract_text
from core.image_utils import draw_result_on_image
from core.llm_api import correction_work
from core.scanner import scan_and_enhance_document

grade_bp = Blueprint('grade', __name__)

# ========== 实时进度追踪 ==========
_progress_store = {}
_progress_lock = threading.Lock()


def update_progress(task_id, progress, stage):
    """更新某个任务的进度（线程安全）"""
    with _progress_lock:
        _progress_store[task_id] = {'progress': progress, 'stage': stage}


def clean_old_progress():
    """清理超过 5 分钟的旧进度记录"""
    import time
    now = time.time()
    with _progress_lock:
        stale = [tid for tid, _ in _progress_store.items()
                 if isinstance(_, dict) and _.get('_ts', 0) < now - 300]
        for tid in stale:
            del _progress_store[tid]


@grade_bp.route('/api/grade', methods=['POST'])
def api_grade():
    """
    核心批改接口（异步）：返回 task_id，前端轮询进度
    """
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': '没有找到图片'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '没有选择文件'}), 400

    #处理上传的作业图片文件
    image_bytes = file.read()
    task_id = str(uuid.uuid4())
    filename = file.filename or '作业图片.jpg'
    host_url = request.host_url
    app = current_app._get_current_object()

    update_progress(task_id, 0, '正在准备...')

    # 后台线程处理，不阻塞前端
    thread = threading.Thread(
        target=_process_grade_background,
        args=(task_id, image_bytes, filename, host_url, app)
    )
    thread.daemon = True
    thread.start()

    # 顺手清理过期记录
    clean_old_progress()

    return jsonify({'status': 'success', 'task_id': task_id})


@grade_bp.route('/api/grade/progress/<task_id>')
def get_grade_progress(task_id):
    """前端轮询进度的接口"""
    with _progress_lock:
        data = _progress_store.get(task_id)
    if data is None:
        return jsonify({'progress': 0, 'stage': '准备中'})
    # 不把 _ts 返回给前端
    result = {k: v for k, v in data.items() if k != '_ts'}
    return jsonify(result)


def _process_grade_background(task_id, image_bytes, filename, host_url, app):
    """
    后台异步执行批改全流程（OpenCV → OCR → LLM → 绘图）
    每完成一个阶段就更新一次进度
    """
    import time
    temp_filepath = None
    try:
        # ====== 阶段1：OpenCV 图像处理 ======
        update_progress(task_id, 5, '正在使用OpenCV进行图像增强...')
        print("正在使用OpenCV进行图像自动切割与增强")
        enhanced_bytes = scan_and_enhance_document(image_bytes)
        update_progress(task_id, 15, '图像增强完成')

        # ====== 阶段2：保存临时图片、准备图床链接 ======
        update_progress(task_id, 20, '正在准备图床...')
        os.makedirs("static", exist_ok=True)
        temp_filename = f"ocr_temp_{uuid.uuid4().hex}.jpg"
        temp_filepath = os.path.join("static", temp_filename)
        with open(temp_filepath, "wb") as f:
            f.write(enhanced_bytes)

        my_public_url = host_url + f"static/{temp_filename}"
        is_local = "127.0.0.1" in my_public_url or "localhost" in my_public_url or "0.0.0.0" in my_public_url
        if is_local:
            print("检测到本地地址，改用公网图床上传中转")
            my_public_url = None
        else:
            print(f"本机图床链接已生成: {my_public_url}")

        # ====== 阶段3：OCR 识别 ======
        update_progress(task_id, 30, '正在调用OCR识别文字...')
        print("正在调用夸克进行OCR识别")
        paper_text = extract_text(enhanced_bytes, public_url=my_public_url)

        # 阅后即焚
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
            temp_filepath = None

        if not paper_text or "OCR识别失败" in paper_text or "运行异常" in paper_text:
            error_detail = paper_text if paper_text else "OCR未返回任何文字"
            print(f"OCR识别失败: {error_detail}")
            update_progress(task_id, -1, f'OCR失败: {error_detail}')
            return

        update_progress(task_id, 60, '文字识别完成')

        # ====== 阶段4：大模型批改 ======
        update_progress(task_id, 65, '正在调用AI大模型批改...')
        print("正在调用大模型进行智能批改")
        result = correction_work(paper_text)

        if result is None:
            update_progress(task_id, -1, 'AI批改失败，返回结果为空')
            return

        update_progress(task_id, 85, 'AI批改完成')

        # ====== 阶段5：绘制结果图 ======
        update_progress(task_id, 90, '正在生成批改结果图片...')
        print("正在绘制批改结果图")
        result_image = draw_result_on_image(image_bytes, result)

        # 强制释放内存
        del image_bytes
        del enhanced_bytes
        gc.collect()

        # ====== 阶段6：完成 ======
        final_result = {
            'status': 'success',
            'image_path': result_image,
            'ocr_text': paper_text,
            'feedback_json': json.dumps(result, ensure_ascii=False),
            'filename': filename,
        }
        # 保存到数据库（后台静默执行）
        try:
            with app.app_context():
                _save_grading_to_db(filename, paper_text,
                                    json.dumps(result, ensure_ascii=False), result_image)
        except Exception as db_err:
            print(f"保存批改记录到数据库失败（不影响结果）: {db_err}")

        with _progress_lock:
            _progress_store[task_id] = {
                'progress': 100,
                'stage': '批改完成',
                'result': final_result,
                '_ts': time.time()
            }
        print("批改全流程完成")

    except Exception as e:
        traceback.print_exc()
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except:
                pass
        gc.collect()
        update_progress(task_id, -1, f'批改失败: {str(e)}')


def _save_grading_to_db(filename, ocr_text, feedback_json, result_image):
    """后台静默保存批改记录到数据库"""
    try:
        from sqlalchemy import text

        engine = current_app.config.get('DB_ENGINE')
        if not engine:
            return

        with engine.connect() as conn:
            # 尝试获取当前登录用户
            try:
                from api.auth_api import get_current_user
                # 在后台线程中无法访问 session，跳过用户关联
                username = None
            except:
                username = None

            stmt = text("""
                INSERT INTO grading_records (filename, ocr_text, feedback_json, result_image, created_at)
                VALUES (:filename, :ocr_text, :feedback_json, :result_image, NOW())
            """)
            conn.execute(stmt, {
                'filename': filename,
                'ocr_text': ocr_text,
                'feedback_json': feedback_json,
                'result_image': result_image,
            })
            conn.commit()
    except Exception as e:
        print(f"数据库保存失败: {e}")
