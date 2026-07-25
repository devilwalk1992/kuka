from openai import OpenAI

client = OpenAI(
    api_key="sk-bswllmkgjwhqzgjerxfrlcvnqbbsaptwqwenepfddcuymrmq",  # 👈 替换为你的千问 API Key
    base_url="https://ws-cyvepyy5bit9axlq.cn-beijing.maas.aliyuncs.com/api/v1",
)

response = client.chat.completions.create(
    model="qwen3-vl-flash",  # 图片分析需用视觉模型 qwen-vl-plus 或 qwen-vl-max
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "请仔细观察这张图片，分析图中的产品型号、材质和色彩风格：",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/your-product-image.jpg"  # 替换为你的公开图片链接
                    },
                },
            ],
        }
    ],
)

print(response.choices[0].message.content)
