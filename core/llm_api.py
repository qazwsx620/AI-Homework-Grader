"""
core/llm_api.py — 大模型批改模块
负责：将 OCR 文本发送给大模型（千问 qwen-plus）进行批改，
返回结构化的 JSON 批改结果（题号、正误、答案、解析）
"""
import json
import requests

# 大模型 API 密钥（千问 DashScope）
api_key = "**********"


def correction_work(work):
    """
    调用千问大模型批改作业
    :param work: OCR 提取的作业文本
    :return: dict，包含 feedback 字段（题号、正误判断、正确答案、正确解法）
    """
    prompt = f"你是一名中小学老师。请识别作业内容，提取题目和学生答案。作业内容如下：{work}。批改完成后请返回包含feedback的JSON格式。注：feedback内容的先后顺序为：题号、正误判断、正确答案、正确解法。"

    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "qwen-plus",
        "input": {
            "messages": [
                {"role": "system", "content": "你是一名负责批改中小学生作业的老师"},
                {"role": "user", "content": prompt}
            ]
        },
        "parameters": {
            "result_format": "message"
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        try:
            content = response.json()["output"]["choices"][0]["message"]["content"]
            result_dict = json.loads(content)
            return result_dict
        except Exception as e:
            print(f"解析响应失败：{e}")
    else:
        print(f"HTTP请求失败，错误码：{response.status_code}")


if __name__ == "__main__":
    test_q = ("已知 x + 2 = 5，求 x 的值。解：x = 3")
    print("正在呼叫大模型老师进行批改，请稍候...")
    result = correction_work(test_q)
    print("\n批改完成！结果是：")
    print(result)
