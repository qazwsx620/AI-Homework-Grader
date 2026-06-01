"""
app.py — AI 智能作业批改系统 · 应用入口
负责：创建 Flask 应用、配置数据库引擎、注册蓝图、启动服务
"""
import os
from flask import Flask, render_template
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from api.auth_api import auth_bp
from api.grade_api import grade_bp
from api.history_api import history_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ai_homework_grading_secret_key_2024")
# 尝试从环境变量读取云端数据库 URL (Render 部署时配置)
cloud_db_url = os.environ.get("DATABASE_URL")

if cloud_db_url:
    # 如果是在云服务器上，使用云端提供的 MySQL 数据库
    print("检测到环境变量，正在连接云端 MySQL 数据库...")
    DB_URL = cloud_db_url
else:
    # 如果是在自己的电脑上测试，使用本地数据库
    print("未检测到环境变量，正在连接本地 MySQL 数据库...")
    DB_PASSWORD = quote_plus("251027Wmh#")
    DB_URL = f"mysql+pymysql://root:{DB_PASSWORD}@localhost:3306/studentsdb"

# 初始化数据库引擎 (pool_pre_ping=True 非常重要，可以防止云数据库连接长时间休眠后断开)
app.config['DB_ENGINE'] = create_engine(DB_URL, pool_pre_ping=True)

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(grade_bp)
app.register_blueprint(history_bp)


@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')


if __name__ == '__main__':
    # 获取 Render 分配的端口，本地默认 5000
    port = int(os.environ.get("PORT", 5000))
    print(f"Web 界面启动成功！请在浏览器访问: http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
