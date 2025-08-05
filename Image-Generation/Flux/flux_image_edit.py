# Install required packages: `pip install requests pillow azure-identity`
import os
import requests
import base64
from PIL import Image
from io import BytesIO
from datetime import datetime

# load environment variables or set them directly
import dotenv

# load .env from specific file path
dotenv.load_dotenv(override=True)

# You will need to set these environment variables or edit the following values.
endpoint = os.getenv(
    "AZURE_OPENAI_ENDPOINT",
    "https://jz-fdpo-proj-v2-swn-resource.cognitiveservices.azure.com/",
)
deployment = os.getenv("DEPLOYMENT_NAME", "FLUX.1-Kontext-pro-globalstandard")
api_version = os.getenv("OPENAI_API_VERSION", "2025-04-01-preview")
subscription_key = os.getenv("AZURE_OPENAI_API_KEY")
# print(f"Using endpoint: {endpoint}, deployment: {deployment}, api_version: {api_version}, key: {subscription_key}")

def decode_and_save_image(b64_data, output_filename):
    """解码base64图像数据并保存到文件"""
    image = Image.open(BytesIO(base64.b64decode(b64_data)))
    image.show()
    image.save(output_filename)

def save_response(response_data, prompt_text):
    """保存API响应中的图像数据"""
    # 创建 edited_images 文件夹（如果不存在）
    os.makedirs("edited_images", exist_ok=True)
    
    data = response_data["data"]
    b64_img = data[0]["b64_json"]
    
    # 获取 prompt 的前10个字符
    prompt_prefix = prompt_text[:10].replace(" ", "_").replace("/", "_").replace("\\", "_")
    
    # 获取当前时间戳（精确到秒）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 生成文件名
    filename = f"edited_images/{prompt_prefix}_{timestamp}.png"
    
    decode_and_save_image(b64_img, filename)
    print(f"Edited image saved to: '{filename}'")

def edit_image(image_path, prompt, size="1024x1024"):
    """编辑指定的图像"""
    # 检查图像文件是否存在
    if not os.path.exists(image_path):
        print(f"Error: Image file '{image_path}' not found!")
        return None
    
    base_path = f"openai/deployments/{deployment}/images"
    params = f"?api-version={api_version}"
    
    # 构建编辑API的URL
    edit_url = f"{endpoint}{base_path}/edits{params}"
    
    # 准备请求体
    edit_body = {
        "prompt": prompt,
        "n": 1,
        "size": size
    }
    
    try:
        # 使用 with 语句确保文件正确关闭
        with open(image_path, "rb") as image_file:
            # 准备文件 - 按照官方示例的格式
            files = {
                "image": (os.path.basename(image_path), image_file, "image/png"),
                "prompt": (None, prompt),
                "n": (None, str(edit_body["n"])),
                "size": (None, size)
            }
            
            # 发送编辑请求 - 使用files参数而不是data参数
            edit_response = requests.post(
                edit_url, 
                headers={"api-key": subscription_key}, 
                files=files
            )
            
        # print url, request body, request header and response
        print(f"Request URL: {edit_url}")
        print(f"Request Body: {edit_body}")
        # print(f"Request Headers: {{\"api-key\": \"{subscription_key}\"}}")
        print(f"Response Status Code: {edit_response.status_code}")
        
        if edit_response.status_code == 200:
            response_json = edit_response.json()
            save_response(response_json, edit_body["prompt"])
            return response_json
        else:
            print(f"Error: {edit_response.status_code}")
            print(edit_response.text)
            return None
            
    except Exception as e:
        print(f"Error during image editing: {e}")
        return None

# 示例使用
if __name__ == "__main__":
    # 指定要编辑的图像路径
    image_to_edit = "generated_images/Transparen_20250805_120446.png"
    
    # 编辑提示词
    edit_prompt = "set the background to white paper"
    
    # 执行图像编辑
    print(f"Editing image: {image_to_edit}")
    print(f"Edit prompt: {edit_prompt}")
    
    result = edit_image(image_to_edit, edit_prompt)
    
    if result:
        print("Image editing completed successfully!")
    else:
        print("Image editing failed!")
