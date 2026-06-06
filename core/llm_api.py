"""
core/llm_api.py — 大模型批改模块
负责：将 OCR 文本发送给大模型（千问 qwen-plus）进行批改，
返回结构化的 JSON 批改结果（题号、正误、答案、解析）
"""
import json
import re
import os
import sys
import requests

# Windows 终端编码修复
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 从环境变量读取千问 DashScope API 密钥（避免硬编码泄露）
api_key = os.environ.get("DASHSCOPE_API_KEY", "")


def _estimate_question_count(text):
    """根据 OCR 文本中的题号模式估算题目数量，用于动态调整 max_tokens"""
    patterns = [
        r'(?:^|\n)\s*\d+[.、）\)]',          # "1." "1、" "1）"
        r'(?:^|\n)\s*[（(]\d+[)）]',          # "(1)" "（1）"
        r'第[一二三四五六七八九十百千\d]+[题节条]',   # "第1题" "第一题"
    ]
    matches = set()
    for p in patterns:
        for m in re.finditer(p, text):
            matches.add(m.group().strip())
    count = len(matches)
    return max(count, 1)  # 至少 1 题


def correction_work(work):
    """
    调用千问大模型批改作业
    :param work: OCR 提取的作业文本
    :return: dict，包含 feedback 字段（题号、正误判断、正确答案、正确解法）
    """
    # 根据题目数量动态分配 max_tokens
    question_count = _estimate_question_count(work)
    max_tokens = max(4096, min(16384, question_count * 1024))
    request_timeout = max(120, min(300, max_tokens // 128 * 8))
    print(f"检测到约 {question_count} 道题，动态设置 max_tokens={max_tokens}, timeout={request_timeout}s")

    prompt = (
        f"你是一名中小学老师。请识别作业内容，提取题目和学生答案。作业内容如下：{work}。\n\n"
        "请批改作业中的所有题目，不要遗漏任何一题。\n\n"
        "请严格按照以下JSON格式返回，不要包含任何markdown代码块标记（不要用```json或```），直接返回纯JSON字符串：\n"
        "{\n"
        '  "feedback": [\n'
        "    {\n"
        '      "题号": "1",\n'
        '      "正误判断": "正确" 或 "错误",\n'
        '      "正确答案": "标准答案内容",\n'
        '      "正确解法": "详细的解题步骤和解析"\n'
        "    },\n"
        "    {\n"
        '      "题号": "2",\n'
        '      "正误判断": "正确" 或 "错误",\n'
        '      "正确答案": "标准答案内容",\n'
        '      "正确解法": "详细的解题步骤和解析"\n'
        "    },\n"
        "    ...\n"
        "    请列出所有题目，逐一批改\n"
        "  ]\n"
        "}\n\n"
        "注意：请确保返回的JSON是合法的、可直接被json.loads解析的格式，不要添加任何额外的文字说明。"
    )

    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "qwen-plus",
        "input": {
            "messages": [
                {"role": "system", "content": "你是一名负责批改中小学生作业的老师。请批改识别出的所有题目，不要遗漏任何一题。每道题都必须包含题号、正误判断、正确答案和正确解法。直接返回JSON格式的批改结果，不要使用markdown代码块包裹。"},
                {"role": "user", "content": prompt}
            ]
        },
        "parameters": {
            "result_format": "message",
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "top_p": 0.9
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=request_timeout)

    if response.status_code == 200:
        try:
            content = response.json()["output"]["choices"][0]["message"]["content"]
            # 清理可能存在的 markdown 代码块标记
            content = content.strip()
            if content.startswith("```"):
                # 移除开头的 ```json 或 ``` 及结尾的 ```
                content = content.strip("`").strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            elif "```" in content:
                # 提取 ``` 之间的内容
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
                if match:
                    content = match.group(1).strip()
            result_dict = json.loads(content)
            return result_dict
        except Exception as e:
            print(f"解析响应失败：{e}")
            try:
                print(f"原始响应内容：{content[:500]}")
            except UnicodeEncodeError:
                pass
    else:
        print(f"HTTP请求失败，错误码：{response.status_code}")
        try:
            print(f"响应内容：{response.text[:500]}")
        except UnicodeEncodeError:
            pass

