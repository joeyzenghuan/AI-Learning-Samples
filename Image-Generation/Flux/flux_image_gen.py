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
    image = Image.open(BytesIO(base64.b64decode(b64_data)))
    image.show()
    image.save(output_filename)


def save_response(response_data, prompt_text):
    # 创建 generated_images 文件夹（如果不存在）
    os.makedirs("generated_images", exist_ok=True)
    
    data = response_data["data"]
    b64_img = data[0]["b64_json"]
    
    # 获取 prompt 的前10个字符
    prompt_prefix = prompt_text[:10].replace(" ", "_").replace("/", "_").replace("\\", "_")
    
    # 获取当前时间戳（精确到秒）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 生成文件名
    filename = f"generated_images/{prompt_prefix}_{timestamp}.png"
    
    decode_and_save_image(b64_img, filename)
    print(f"Image saved to: '{filename}'")


base_path = f"openai/deployments/{deployment}/images"
params = f"?api-version={api_version}"

generation_url = f"https://jz-fdpo-proj-v2-swn-resource.cognitiveservices.azure.com/{base_path}/generations{params}"
generation_body = {
    "prompt": "Transparent diagram of a mech-style West Highland White Terrier, with visible transformation hinges, compact energy cells, and detailed mechanical annotations. --quality 2 --sref 2007748773 --sw 400 --stylize 500 --v 7 --sv 6",
    "n": 1,
    "size": "1024x1024",
    "output_format": "png",
}
generation_response = requests.post(
    generation_url,
    headers={
        "api-key": subscription_key,
        "Content-Type": "application/json",
    },
    json=generation_body,
).json()
# print(generation_response)
save_response(generation_response, generation_body["prompt"])



# # In addition to generating images, you can edit them.
# edit_url = f"{endpoint}{base_path}/edits{params}"
# edit_body = {"prompt": "a smiling westie dog", "n": 1, "size": "1024x1024"}
# files = {
#     "image": ("generated_images/Transparen_20250805_123456.png", open("generated_images/Transparen_20250805_123456.png", "rb"), "image/png"),
# }
# edit_response = requests.post(
#     edit_url, headers={"Api-Key": subscription_key}, data=edit_body, files=files
# ).json()
# save_response(edit_response, edit_body["prompt"])
