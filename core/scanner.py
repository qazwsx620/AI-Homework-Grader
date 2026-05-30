"""
core/scanner.py — 文档扫描与图像增强模块
负责：自动检测纸张边缘 → 透视变换拉正 → 对比度增强与锐化
"""
import cv2
import numpy as np


def order_points(pts):
    """
    将四个角点按 左上、右上、右下、左下 排序
    :param pts: 原始四点坐标
    :return: 排序后的 (4, 2) 数组
    """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def four_point_transform(image, pts):
    """
    透视变换：将检测到的倾斜纸张拉正为矩形
    :param image: 原始图像
    :param pts: 纸张四个角点
    :return: 拉正后的图像
    """
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    return warped


def scan_and_enhance_document(image_bytes):
    """
    核心函数：接收图片字节流，执行文档扫描与增强
    流程：边缘检测 → 寻找最大四边形轮廓 → 透视变换拉正 → 对比度增强 → 锐化
    :param image_bytes: 原始图片字节流
    :return: 处理后的 JPG 字节流
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    orig = image.copy()

    ratio = image.shape[0] / 500.0
    orig_height, orig_width = image.shape[:2]

    if orig_height < 500:
        ratio = 1.0
        resized = image
    else:
        resized = cv2.resize(image, (int(orig_width / ratio), 500))

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 75, 200)

    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
    screenCnt = None

    for c in cnts:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            screenCnt = approx
            break

    if screenCnt is not None:
        warped = four_point_transform(orig, screenCnt.reshape(4, 2) * ratio)
    else:
        warped = orig

    enhanced = cv2.convertScaleAbs(warped, alpha=1.2, beta=10)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    enhanced = cv2.filter2D(enhanced, -1, kernel)

    is_success, buffer = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if is_success:
        return buffer.tobytes()
    return image_bytes
