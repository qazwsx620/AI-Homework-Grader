@echo off
echo ==========================================
echo 正在启动 AI 批改系统——Windows高并发模式
echo ==========================================

echo [1/2] 正在检查并安装项目依赖库
pip install flask waitress
pip install opencv-python-headless

echo.
echo [2/2] 启动 Waitress 多线程服务器
echo 请在浏览器中访问: http://127.0.0.1:5000
echo 按“Ctrl+C”可以关闭服务器
echo ------------------------------------------

waitress-serve --threads=8 --listen=0.0.0.0:5000 app:app

pause
