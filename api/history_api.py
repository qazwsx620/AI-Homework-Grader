"""
api/history_api.py — 批改记录模块（Blueprint: history_bp）
负责：保存批改记录、获取记录列表、获取记录详情、删除记录
"""
from flask import Blueprint, request, jsonify, session, current_app
from sqlalchemy import text

history_bp = Blueprint('history', __name__)


@history_bp.route('/api/save_grading', methods=['POST'])
def api_save_grading():
    """保存批改记录到 grading_history 表"""
    user = session.get('user')
    if not user:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '无数据'}), 400

    engine = current_app.config['DB_ENGINE']
    try:
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO grading_history
                    (username, filename, ocr_text, feedback_json, result_image)
                    VALUES (:u, :f, :ocr, :fb, :img)
                """),
                {
                    "u": user,
                    "f": data.get('filename', ''),
                    "ocr": data.get('ocr_text', ''),
                    "fb": data.get('feedback_json', ''),
                    "img": data.get('result_image', '')
                }
            )
            conn.commit()
        return jsonify({'status': 'success', 'message': '批改记录已保存'})
    except Exception as e:
        print(f"保存批改记录失败: {e}")
        return jsonify({'status': 'error', 'message': '保存失败'}), 500


@history_bp.route('/api/grading_history')
def api_grading_history():
    """获取当前用户的批改记录列表（按时间倒序）"""
    user = session.get('user')
    if not user:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401

    engine = current_app.config['DB_ENGINE']
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, filename, created_at
                    FROM grading_history
                    WHERE username = :u
                    ORDER BY created_at DESC
                """),
                {"u": user}
            )
            records = []
            for row in result:
                records.append({
                    'id': row[0],
                    'filename': row[1] or '未命名',
                    'created_at': row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else ''
                })
        return jsonify({'status': 'success', 'records': records})
    except Exception as e:
        print(f"获取批改记录失败: {e}")
        return jsonify({'status': 'error', 'message': '获取失败'}), 500


@history_bp.route('/api/grading_history/<int:record_id>')
def api_grading_history_detail(record_id):
    """获取单条批改记录的完整详情"""
    user = session.get('user')
    if not user:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401

    engine = current_app.config['DB_ENGINE']
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, filename, ocr_text, feedback_json,
                           result_image, created_at
                    FROM grading_history
                    WHERE id = :id AND username = :u
                """),
                {"id": record_id, "u": user}
            )
            row = result.fetchone()
            if not row:
                return jsonify({'status': 'error', 'message': '记录不存在'}), 404

            record = {
                'id': row[0],
                'filename': row[1] or '未命名',
                'ocr_text': row[2],
                'feedback_json': row[3],
                'result_image': row[4],
                'created_at': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else ''
            }
        return jsonify({'status': 'success', 'record': record})
    except Exception as e:
        print(f"获取批改记录详情失败: {e}")
        return jsonify({'status': 'error', 'message': '获取失败'}), 500


@history_bp.route('/api/grading_history/<int:record_id>', methods=['DELETE'])
def api_delete_history(record_id):
    """删除指定批改记录"""
    user = session.get('user')
    if not user:
        return jsonify({'status': 'error', 'message': '请先登录'}), 401

    engine = current_app.config['DB_ENGINE']
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM grading_history WHERE id = :id AND username = :u"),
                {"id": record_id, "u": user}
            )
            conn.commit()
            if result.rowcount == 0:
                return jsonify({'status': 'error', 'message': '记录不存在'}), 404
        return jsonify({'status': 'success', 'message': '已删除'})
    except Exception as e:
        print(f"删除批改记录失败: {e}")
        return jsonify({'status': 'error', 'message': '删除失败'}), 500
