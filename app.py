"""
app.py — AI 智能作业批改系统 · 应用入口
负责：创建 Flask 应用、配置数据库引擎、注册蓝图、启动服务
"""
from flask import Flask, render_template
from sqlalchemy import create_engine
from urllib.parse import quote_plus

app = Flask(__name__)
app.secret_key = "ai_homework_grading_secret_key_2024"

# 数据库引擎
DB_PASSWORD = quote_plus("251027Wmh#")
DB_URL = f"mysql+pymysql://root:{DB_PASSWORD}@localhost:3306/studentsdb"
app.config['DB_ENGINE'] = create_engine(DB_URL, pool_pre_ping=True)

# 看门狗（网页关闭后自动退出）
from core.watchdog import start_watchdog, heartbeat
start_watchdog()
app.add_url_rule('/api/heartbeat', 'heartbeat', heartbeat)

# 注册蓝图
from api.auth_api import auth_bp
from api.grade_api import grade_bp
from api.history_api import history_bp
app.register_blueprint(auth_bp)
app.register_blueprint(grade_bp)
app.register_blueprint(history_bp)


@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')


if __name__ == '__main__':
    print("Web 界面启动成功！请在浏览器访问: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
