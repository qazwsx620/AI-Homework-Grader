"""
api/ocr_api.py — OCR 文字识别模块
负责：图片校验与压缩 → 上传至公网图床 → 夸克 OCR 接口识别
"""
import os
import sys
import base64
import time
import requests
import json
import uuid
import hashlib
import io
from PIL import Image

# Windows 终端编码修复：避免 GBK 无法编码 Unicode 字符导致崩溃
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 请在这里填入夸克 Client ID 和 Secret
QUARK_CLIENT_ID = "**********"
QUARK_CLIENT_SECRET = "**********"


def get_signature(client_id, client_secret, business, sign_method, sign_nonce, timestamp):
    """根据夸克官方规范生成安全签名"""
    raw_str = f"{client_id}_{business}_{sign_method}_{sign_nonce}_{timestamp}_{client_secret}"
    utf8_bytes = raw_str.encode("utf-8")

    if sign_method.lower() == "sha256":
        digest = hashlib.sha256(utf8_bytes).hexdigest()
    elif sign_method.lower() == "sha1":
        digest = hashlib.sha1(utf8_bytes).hexdigest()
    elif sign_method.lower() == "md5":
        digest = hashlib.md5(utf8_bytes).hexdigest()
    elif sign_method.lower() in ["sha3-256", "sha3_256"]:
        digest = hashlib.sha3_256(utf8_bytes).hexdigest()
    else:
        raise ValueError("Unsupported sign method")

    return digest.lower()



# 绕过代理的配置（避免 HTTP_PROXY/HTTPS_PROXY 环境变量干扰图床上传）
_NO_PROXY = {"http": "", "https": ""}


def upload_to_temp_host(image_bytes):
    """
    多节点智能中转引擎：将本地图片临时上传至免费的公网图床
    节点 1: FreeImage.host（base64 上传）
    节点 2: Catbox.moe（multipart 上传，兜底）
    """
    print("正在将图片上传至临时中转图床...")

    # ================= 节点 1: FreeImage.host =================
    try:
        print("  -> 正在尝试节点 1 (FreeImage)...")
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
        response = requests.post(
            "https://freeimage.host/api/1/upload",
            data={
                "key": "6d207e02198a847aa98d0a2a901485a5",
                "action": "upload",
                "source": b64_img,
                "format": "json"
            },
            proxies=_NO_PROXY,
            timeout=10
        )
        if response.status_code == 200:
            res_json = response.json()
            public_url = res_json.get("image", {}).get("url")
            if public_url:
                print(f"节点 1 上传成功: {public_url}")
                return public_url
    except Exception as e:
        print(f"节点 1 连接失败 ({e})，正在切换备用节点...")

    # ================= 节点 2: Catbox.moe =================
    try:
        print("  -> 正在尝试节点 2 (Catbox)...")
        response = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": ("upload.jpg", image_bytes, "image/jpeg")},
            proxies=_NO_PROXY,
            timeout=15
        )
        if response.status_code == 200 and response.text.startswith("http"):
            public_url = response.text.strip()
            print(f"节点 2 上传成功: {public_url}")
            return public_url
    except Exception as e:
        print(f"节点 2 连接失败 ({e})")

    print("所有临时图床节点均超时失败。请检查您的网络连接（或尝试使用代理）。")
    return None


def extract_text(image_bytes):
    """
    核心 OCR 函数：使用夸克 RecognizeQuestion 接口提取试卷文字
    流程：图片校验 → 自动压缩 → 上传图床 → 调用夸克 API → 递归提取文本
    """
    # ==========================================
    # 智能图片规范校验与自动压缩引擎
    # ==========================================
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img_format = img.format if img.format else "JPEG"
            valid_formats = ['PNG', 'JPG', 'JPEG', 'BMP', 'GIF', 'TIFF', 'WEBP']
            if img_format.upper() not in valid_formats:
                return f"OCR识别失败：不支持的图片格式 {img_format}。建议使用 JPG/JPEG 格式。"

            width, height = img.size
            if width < 15 or height < 15:
                return f"OCR识别失败：图片尺寸 ({width}x{height}) 太小，长宽均需大于 15 像素。"

            max_side, min_side = max(width, height), min(width, height)
            if min_side > 0 and (max_side / min_side) >= 50:
                return f"OCR识别失败：图片长宽比例异常 ({(max_side / min_side):.2f})，长宽比必须小于 50。"

            if width > 8192 or height > 8192:
                ratio = 8192.0 / max(width, height)
                new_w, new_h = int(width * ratio), int(height * ratio)
                resample_filter = getattr(Image, 'Resampling', Image).LANCZOS if hasattr(Image,
                                                                                         'Resampling') else getattr(
                    Image, 'ANTIALIAS', 1)
                img = img.resize((new_w, new_h), resample_filter)

            if img.mode != 'RGB':
                img = img.convert('RGB')

            buffered = io.BytesIO()
            quality = 95
            img.save(buffered, format="JPEG", quality=quality)

            while len(buffered.getvalue()) > 5 * 1024 * 1024 and quality > 30:
                quality -= 10
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG", quality=quality)

            if len(buffered.getvalue()) > 10 * 1024 * 1024:
                return "OCR识别失败：图片包含的信息过于庞大，经过极限压缩仍超过了 10MB 的最高限制。"

            image_bytes = buffered.getvalue()

    except Exception as e:
        return f"OCR识别失败：无法解析图片格式或尺寸，图片可能已损坏 ({str(e)})"

    # ==========================================
    # 获取公开的图片 URL
    # ==========================================
    public_url = upload_to_temp_host(image_bytes)
    if not public_url:
        return "OCR识别失败：无法将图片中转至公网，请检查您的网络连接。"

    # ==========================================
    # 发起夸克 API 请求
    # ==========================================
    url = "https://scan-business.quark.cn/vision"

    try:
        business = "vision"
        sign_method = "SHA3-256"
        sign_nonce = uuid.uuid4().hex
        timestamp = int(time.time() * 1000)
        req_id = uuid.uuid4().hex

        signature = get_signature(QUARK_CLIENT_ID, QUARK_CLIENT_SECRET, business, sign_method, sign_nonce, timestamp)

        param = {
            "dataUrl": public_url,
            "dataType": "image",
            "serviceOption": "structure",
            "inputConfigs": '{"function_option": "RecognizeQuestion"}',
            "outputConfigs": '{"need_return_image": "False"}',
            "reqId": req_id,
            "clientId": QUARK_CLIENT_ID,
            "signMethod": sign_method,
            "signNonce": sign_nonce,
            "timestamp": timestamp,
            "signature": signature
        }

        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=param, headers=headers, proxies=_NO_PROXY)
        response.encoding = "utf-8"

        if response.status_code == 200:
            res_json = response.json()
            import json as _json
            print("夸克接口原始返回数据：", _json.dumps(res_json, ensure_ascii=False, indent=2, default=str))

            code = str(res_json.get("code", ""))
            if code not in ["200", "0", "00000"]:
                error_msg = res_json.get("message") or res_json.get("msg") or "未知错误"
                return f"OCR识别失败，夸克报错: {error_msg} (错误码: {code})"

            data_field = res_json.get("data")
            if not data_field:
                return "OCR识别成功，但未提取到任何文字内容"

            parsed_text = _extract_all_texts(data_field)
            if parsed_text:
                return parsed_text

            return str(data_field)

        else:
            return f"夸克 OCR 接口请求失败，HTTP 状态码: {response.status_code}"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"运行异常: {e}"


def _extract_all_texts(data):
    """
    辅助函数：递归提取夸克 API 返回的嵌套 JSON 中的文本
    自动探测 'Value' / 'content' / 'text' / 'words' 等字段
    """
    lines = []
    if isinstance(data, dict):
        text = data.get("Value") or data.get("content") or data.get("text") or data.get("words")
        if text and isinstance(text, str):
            lines.append(text.strip())

        for key, val in data.items():
            if isinstance(val, (dict, list)):
                sub_text = _extract_all_texts(val)
                if sub_text:
                    lines.append(sub_text)

    elif isinstance(data, list):
        for item in data:
            sub_text = _extract_all_texts(item)
            if sub_text:
                lines.append(sub_text)

    return "\n".join(lines)


# ================= 本地测试专区 =================
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    image_path = os.path.join(project_root, "images", "1.jpg")

    if not os.path.exists(image_path):
        print(f"找不到测试图片: {image_path}")
    else:
        print("正在发送请求至夸克视觉识别大模型 ...")
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        result_text = extract_text(image_bytes)
        print("\n=== 最终提取结果 ===")
        print(result_text)
