"""
api/auth_api.py — 用户认证模块（Blueprint: auth_bp）
负责：注册、登录、退出登录、检查登录状态
"""
import re
from flask import Blueprint, request, jsonify, session, current_app
from sqlalchemy import text

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/register', methods=['POST'])
def api_register():
    """用户注册：校验用户名密码格式，写入 users_info 表"""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '请提供用户名和密码'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'status': 'error', 'message': '用户名和密码不能为空'}), 400

    if len(username) < 1 or len(username) > 20:
        return jsonify({'status': 'error', 'message': '用户名长度应为1-20个字符'}), 400

    pattern = r"^(?=.*[@$!%*?&#^])(?=.*[A-Z])(?=.*\d)[A-Za-z\d@$!%*?&#^]{8,}$"
    if not re.match(pattern, password):
        return jsonify({'status': 'error', 'message': '密码至少8个字符，至少包含一个大写字母和一个特殊符号'}), 400

    engine = current_app.config['DB_ENGINE']
    try:
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO users_info (username, password) VALUES (:u, :p)"),
                {"u": username, "p": password}
            )
            conn.commit()
        print(f"新用户注册成功: {username}")
        return jsonify({'status': 'success', 'message': '注册成功，请登录'})
    except Exception as e:
        err_msg = str(e)
        if "Duplicate" in err_msg or "UNIQUE" in err_msg:
            return jsonify({'status': 'error', 'message': '用户名已存在，请更换'})
        return jsonify({'status': 'error', 'message': '注册失败'}), 500


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    """用户登录：校验用户名密码，写入 session"""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': '请提供用户名和密码'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'status': 'error', 'message': '用户名和密码不能为空'}), 400

    engine = current_app.config['DB_ENGINE']
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT password FROM users_info WHERE username = :u"),
                {"u": username}
            )
            row = result.fetchone()

        if row is None:
            return jsonify({'status': 'error', 'message': '用户名不存在'}), 401

        stored_password = row[0]
        if password != stored_password:
            return jsonify({'status': 'error', 'message': '密码错误'}), 401

        session['user'] = username
        print(f"用户登录成功: {username}")
        return jsonify({'status': 'success', 'message': '登录成功', 'username': username})

    except Exception as e:
        return jsonify({'status': 'error', 'message': '登录失败'}), 500


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    """用户退出：清除 session 中的用户信息"""
    username = session.pop('user', None)
    if username:
        print(f"用户退出: {username}")
    return jsonify({'status': 'success', 'message': '已退出登录'})


@auth_bp.route('/api/check_login')
def api_check_login():
    """检查当前会话是否已登录"""
    user = session.get('user')
    if user:
        return jsonify({'status': 'success', 'logged_in': True, 'username': user})
    return jsonify({'status': 'success', 'logged_in': False})
