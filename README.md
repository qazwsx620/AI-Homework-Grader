# AI 智能作业批改系统

基于 Flask 的 AI 智能作业批改 Web 应用。用户上传作业图片后，系统自动完成文档扫描增强、OCR 文字识别、大模型智能批改，并将结构化批改结果渲染为可视化图片，支持历史记录管理。

## 功能特性

- **用户认证**：注册、登录、退出登录、基于 Flask Session 的登录态管理
- **文档扫描增强**：OpenCV Canny 边缘检测 + 最大四边形轮廓提取 + 透视变换拉正 + 对比度增强与锐化
- **OCR 文字识别**：对接夸克 RecognizeQuestion 接口，支持 JPG/PNG/BMP/GIF/TIFF/WEBP 多格式图片；自动压缩与尺寸校验；双节点图床中转（FreeImage.host + Catbox.moe 兜底）
- **AI 智能批改**：调用通义千问 qwen-plus 大模型批改作业，以 JSON 格式返回题号、正误判断、标准答案、解题解析
- **批改结果可视化**：将结构化批改结果渲染到图片底部面板，支持 LaTeX 公式清洗转换（分数/根号/上下标/数学符号）、智能自动换行、动态画布高度
- **批改记录管理**：历史记录保存、列表查看、详情查看、删除
- **双环境部署**：支持本地开发模式与云端部署（Render），通过环境变量自动切换

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Flask |
| 数据库 | MySQL (SQLAlchemy) |
| 图像处理 | OpenCV + Pillow |
| OCR | 夸克视觉识别 API |
| AI 批改 | 通义千问 DashScope API |
| 图床中转 | FreeImage.host / Catbox.moe |
| 部署 | Waitress（多线程生产服务器） |

## 项目结构

```
.
├── app.py                  # 应用入口 & Flask 配置
├── start_windows.bat       # Windows 启动脚本
├── requirements.txt        # 依赖清单
├── .gitignore
├── api/
│   ├── auth_api.py         # 用户认证模块
│   ├── grade_api.py        # 作业批改核心接口
│   ├── history_api.py      # 批改记录管理
│   └── ocr_api.py          # OCR 文字识别模块
├── core/
│   ├── scanner.py          # 文档扫描与图像增强
│   ├── image_utils.py      # 批改结果图像绘制
│   └── llm_api.py          # 大模型批改模块
└── templates/
    ├── index.html          # 首页
    ├── login.html          # 登录页
    ├── home.html           # 系统主页
    ├── grading.html        # 批改页面
    └── history.html        # 历史记录页
```

## 快速开始

### 前置要求

- Python 3.8+
- MySQL 数据库
- 夸克 OCR 接口凭证（Client ID & Secret）
- 通义千问 DashScope API 密钥

### 安装与运行

1. **克隆仓库**

```bash
git clone <repo-url>
cd Python期末大作业
```

2. **配置数据库**

创建数据库 `studentsdb`，并执行建表语句：

```sql
CREATE TABLE users_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL
);

CREATE TABLE grading_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    filename VARCHAR(255),
    ocr_text TEXT,
    feedback_json TEXT,
    result_image LONGTEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

3. **配置 API 密钥**

在 `core/llm_api.py` 中填入你的通义千问 API Key：
```python
api_key = "your-dashscope-api-key"
```

在 `api/ocr_api.py` 中填入夸克接口凭证：
```python
QUARK_CLIENT_ID = "your-client-id"
QUARK_CLIENT_SECRET = "your-client-secret"
```

4. **修改数据库密码**

在 `app.py` 中修改 MySQL 连接密码：
```python
DB_PASSWORD = quote_plus("your-password")
```

5. **安装依赖**

```bash
pip install flask sqlalchemy pymysql opencv-python-headless pillow requests
```

6. **启动服务**

```bash
python app.py
```

或使用生产模式：
```
start_windows.bat
```

7. **访问系统**

打开浏览器访问 `https://ai-grader-xpf7.onrender.com`

## 工作流程

1. 用户注册/登录
2. 上传作业图片（支持 JPG/PNG/BMP/GIF 等格式）
3. 系统进行图像自动裁剪与增强（纸张边缘检测 → 透视变换拉正）
4. 夸克 OCR 识别图片中的文字
5. 千问大模型批改作业，返回题号、正误判断、标准答案、解题解析
6. 将批改结果渲染为图片展示给用户
7. 批改记录自动保存，支持历史查看

## 注意事项

- 图片上传建议使用 JPG 格式，单张图片大小不超过 10MB
- OCR 识别需要公网访问（图片会上传至临时图床）
- API 密钥请妥善保管，勿提交至版本控制
