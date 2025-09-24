import requests
import json
import os
import sys
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

import configparser
config = configparser.ConfigParser()
config.read('C:\GitRepo\OpenAI-examples\.config')
aoai_endpointname = 'jz-fdpo-swn'
AZURE_OPENAI_KEY = config.get('AOAIEndpoints', aoai_endpointname)

@dataclass
class TokenUsage:
    """Token使用统计数据类"""
    round_num: int
    input_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens

@dataclass
class APIResponse:
    """API响应数据类"""
    id: str
    output: List[Dict[str, Any]]
    usage: TokenUsage
    raw_response: Dict[str, Any]
    apim_request_id: Optional[str] = None

class ResponsesAPIClient:
    """Azure OpenAI Responses API 客户端类"""
    
    def __init__(self, api_key: str, endpoint: str, model: str = "gpt-5-globalstandard", 
                 max_rounds: int = 10, timeout: int = 300):
        """
        初始化客户端
        
        Args:
            api_key: Azure OpenAI API密钥
            endpoint: API端点URL
            model: 使用的模型名称
            max_rounds: 最大调用轮数（防止无限循环）
            timeout: 请求超时时间
        """
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.max_rounds = max_rounds
        self.timeout = timeout
        self.function_handlers = {}
        self.token_stats = []
        
        # API配置
        self.url = f"{endpoint}/openai/v1/responses"
        self.headers = {
            "Content-Type": "application/json",
            "api-key": api_key
        }
        self.params = {"api-version": "preview"}
    
    def register_function(self, name: str, handler: Callable, description: str, parameters: Dict[str, Any]):
        """
        注册函数调用处理器
        
        Args:
            name: 函数名
            handler: 处理函数
            description: 函数描述
            parameters: 函数参数定义
        """
        self.function_handlers[name] = {
            "handler": handler,
            "definition": {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具定义"""
        return [func_info["definition"] for func_info in self.function_handlers.values()]
    
    def execute_function_call(self, function_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行函数调用
        
        Args:
            function_call: 函数调用信息
            
        Returns:
            函数调用结果
        """
        name = function_call.get('name')
        call_id = function_call.get('call_id')
        
        if name not in self.function_handlers:
            return {
                "call_id": call_id,
                "output": f"未知函数: {name}",
                "type": "function_call_output"
            }
        
        try:
            args = json.loads(function_call.get('arguments', '{}'))
            handler = self.function_handlers[name]["handler"]
            
            # 如果是图片搜索函数，添加call_id参数
            if name == 'search_image_by_keyword':
                args['call_id'] = call_id
            
            result = handler(**args)
            
            return {
                "call_id": call_id,
                "output": result,
                "type": "function_call_output"
            }
        except Exception as e:
            return {
                "call_id": call_id,
                "output": f"执行错误: {str(e)}",
                "type": "function_call_output"
            }
    
    def call_api(self, input_data: Any, previous_response_id: Optional[str] = None) -> Optional[APIResponse]:
        """
        调用API
        
        Args:
            input_data: 输入数据
            previous_response_id: 前一个响应的ID
            
        Returns:
            API响应数据
        """
        data = {
            "model": self.model,
            "user": "joeyzeng",
            "store": True,
            "max_output_tokens": 10000,
            "stream": False,
            "text": {"verbosity": "medium"},
            "reasoning": {"effort": "high", "summary": "detailed"},
            "tools": self.get_tool_definitions(),
            "parallel_tool_calls": False,
            "input": input_data
        }
        
        if previous_response_id:
            data["previous_response_id"] = previous_response_id
        
        try:
            print(f"发送API请求...")
            response = requests.post(
                self.url, headers=self.headers, params=self.params,
                json=data, timeout=self.timeout
            )
            
            # 获取apim-request-id
            apim_request_id = response.headers.get('apim-request-id', 'N/A')
            
            print(f"响应状态码: {response.status_code}")
            print(f"APIM Request ID: {apim_request_id}")
            
            if response.status_code == 200:
                result = response.json()
                
                # 解析token使用情况
                usage_data = result.get('usage', {})
                token_usage = TokenUsage(
                    round_num=len(self.token_stats) + 1,
                    input_tokens=usage_data.get('input_tokens', 0),
                    cached_tokens=usage_data.get('input_tokens_details', {}).get('cached_tokens', 0),
                    reasoning_tokens=usage_data.get('output_tokens_details', {}).get('reasoning_tokens', 0),
                    output_tokens=usage_data.get('output_tokens', 0),
                    total_tokens=usage_data.get('total_tokens', 0)
                )
                
                api_response = APIResponse(
                    id=result.get('id', ''),
                    output=result.get('output', []),
                    usage=token_usage,
                    raw_response=result,
                    apim_request_id=apim_request_id
                )
                
                self.token_stats.append(token_usage)
                return api_response
            else:
                print(f"请求失败: {response.status_code}")
                print(f"错误信息: {response.text}")
                return None
                
        except Exception as e:
            print(f"API调用异常: {e}")
            return None
    
    def extract_function_calls(self, output: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从输出中提取函数调用"""
        return [item for item in output if item.get('type') == 'function_call']
    
    def run_conversation(self, initial_input: Any, image_mode: str = 'full') -> List[APIResponse]:
        """
        运行完整的对话，自动处理所有function calls
        
        Args:
            initial_input: 初始输入
            image_mode: 图片处理模式
                - 'none': 完全不包含特殊处理
                - 'text': 只返回文本描述
                - 'full': 返回文本描述和图片（默认）
            
        Returns:
            所有API响应的列表
        """
        responses = []
        current_input = initial_input
        previous_response_id = None
        round_num = 1
        
        while round_num <= self.max_rounds:
            print(f"\n=== 第{round_num}轮调用 ===")
            
            # 调用API
            response = self.call_api(current_input, previous_response_id)
            if not response:
                print(f"第{round_num}轮调用失败")
                break
                
            responses.append(response)
            print("请求成功!")
            
            # 提取函数调用
            function_calls = self.extract_function_calls(response.output)
            if not function_calls:
                print(f"第{round_num}轮调用没有产生function call，开始总结轮次")
                
                # 添加总结轮次
                summary_input = [
                    {
                        "role": "user",
                        "content": "总结一下"
                    }
                ]
                
                print(f"\n=== 第{round_num + 1}轮调用 (总结轮次) ===")
                summary_response = self.call_api(summary_input, response.id)
                if summary_response:
                    responses.append(summary_response)
                    print("总结轮次完成!")
                else:
                    print("总结轮次调用失败")
                
                break
            
            print(f"发现 {len(function_calls)} 个function call，开始执行...")
            
            # 执行所有函数调用
            function_results = []
            for fc in function_calls:
                print(f"执行函数: {fc.get('name')}")
                result = self.execute_function_call(fc)
                function_results.append(result)
                
                # 特殊处理图片搜索
                if fc.get('name') == 'search_image_by_keyword':
                    call_id = fc.get('call_id', 'image1')
                    image_filename = f"{call_id}.jpg"
                    
                    if image_mode == 'text':
                        # 仅添加文本描述
                        function_results.append({
                            "role": "user",
                            "content": f"I can see {image_filename} already."
                        })
                        print(f"添加图片文本描述到下一轮调用: {image_filename}")
                    elif image_mode == 'full':
                        # 添加文本描述和图片
                        function_results.append({
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": f"I can see {image_filename} already."},
                                {"type": "input_image", 
                                 "image_url": "https://puui.qpic.cn/vpic_cover/v3528jnid6d/v3528jnid6d_1692796767_hz.jpg"}
                            ]
                        })
                        print(f"添加图片信息到下一轮调用: {image_filename}")
                    # image_mode == 'none' 时不添加任何特殊处理
                    elif image_mode == 'none':
                        print(f"跳过图片特殊处理: {image_filename}")
            
            # 准备下一轮调用
            current_input = function_results
            previous_response_id = response.id
            round_num += 1
        
        if round_num > self.max_rounds:
            print(f"达到最大轮数限制 ({self.max_rounds})，停止对话")
        
        return responses
    
    def print_token_statistics(self, image_mode: str = 'full'):
        """打印token使用统计"""
        if not self.token_stats:
            print("没有token统计数据")
            return
        
        mode_desc = {
            'none': '无图片处理',
            'text': '仅图片文本',
            'full': '包含图片信息'
        }
        
        print("\n" + "="*80)
        print(f"TOKEN 使用统计表 ({mode_desc.get(image_mode, '未知模式')})")
        print("="*80)
        
        # 表头
        print(f"{'调用轮数':<10} {'Input Tokens':<12} {'Cached Tokens':<13} {'Reasoning Tokens':<16} {'Output Tokens':<13} {'Total Tokens':<12}")
        print("-" * 80)
        
        # 数据行和统计
        total_input = sum(stat.input_tokens for stat in self.token_stats)
        total_cached = sum(stat.cached_tokens for stat in self.token_stats)
        total_reasoning = sum(stat.reasoning_tokens for stat in self.token_stats)
        total_output = sum(stat.output_tokens for stat in self.token_stats)
        total_all = sum(stat.total_tokens for stat in self.token_stats)
        
        for stat in self.token_stats:
            print(f"第{stat.round_num}轮{'':<6} {stat.input_tokens:<12} {stat.cached_tokens:<13} {stat.reasoning_tokens:<16} {stat.output_tokens:<13} {stat.total_tokens:<12}")
        
        # 合计行
        print("-" * 80)
        print(f"{'合计':<10} {total_input:<12} {total_cached:<13} {total_reasoning:<16} {total_output:<13} {total_all:<12}")
        
        print("\n" + "="*80)
        print("统计分析:")
        print(f"• 总轮数: {len(self.token_stats)} 轮")
        print(f"• 总计消耗 tokens: {total_all}")
        if total_all > 0:
            print(f"• 输入 tokens: {total_input} ({total_input/total_all*100:.1f}%)")
            print(f"• 缓存 tokens: {total_cached} ({total_cached/total_all*100:.1f}% - 节省成本)")
            print(f"• 推理 tokens: {total_reasoning} ({total_reasoning/total_all*100:.1f}%)")
            print(f"• 输出 tokens: {total_output} ({total_output/total_all*100:.1f}%)")
        if total_cached > 0:
            print(f"• 缓存效率: 节省了 {total_cached} tokens，相当于节省 {total_cached/(total_input+total_cached)*100:.1f}% 的输入成本")
        print("="*80)

def get_file_content_by_filename(filename):
    """
    从当前目录读取文件内容
    """
    try:
        # 获取当前脚本所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, filename)
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"文件 {filename} 的内容：\n{content}"
        else:
            return f"错误：文件 {filename} 不存在于目录 {current_dir} 中"
    except Exception as e:
        return f"读取文件 {filename} 时发生错误：{str(e)}"

# 函数处理器
def search_image_by_keyword(keyword: str, count: int = 1, call_id: str = None) -> str:
    """模拟图片搜索函数"""
    print(f"搜索关键词: {keyword}, 数量: {count}")
    
    # 使用call_id作为文件名，如果没有则使用默认名称
    image_filename = f"{call_id}.jpg" if call_id else "image1.jpg"
    
    return f"找到 {count} 张关于'{keyword}'的图片，已保存为 {image_filename}"

def create_client_with_default_functions() -> ResponsesAPIClient:
    """创建配置了默认函数的客户端"""
    endpoint = "https://jz-fdpo-swn.openai.azure.com"
    client = ResponsesAPIClient(
        api_key=AZURE_OPENAI_KEY,
        endpoint=endpoint,
        model="gpt-5-globalstandard",
        max_rounds=10
    )
    
    # 注册函数处理器
    client.register_function(
        name="get_file_content_by_filename",
        handler=get_file_content_by_filename,
        description="输入filename,返回file content",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "要读取的文件名，例如：example.txt"
                }
            },
            "required": ["filename"]
        }
    )
    
    client.register_function(
        name="search_image_by_keyword",
        handler=search_image_by_keyword,
        description="通过关键词进行网页图片搜索并返回相关图片",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "用于搜索图片的关键词，例如：猫、风景、科技"
                }
                ,
                "count": {
                    "type": "integer",
                    "description": "返回的图片数量，永远返回1，因为每次只能搜一张图"
                }
            },
            "required": ["keyword", "count"]
        }
    )
    
    return client

def main():
    """主函数 - 使用新的响应式API客户端"""
    # 解析命令行参数
    image_mode = 'full'  # 默认为完整模式
    max_rounds = 10
    
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.lower() in ['false', '0', 'no', 'without-image', 'none']:
            image_mode = 'none'
        elif arg.lower() in ['true', '1', 'yes', 'with-image', 'full']:
            image_mode = 'full'
        elif arg.lower() in ['text', 'text-only']:
            image_mode = 'text'
        elif arg.startswith('--image-mode='):
            mode = arg.split('=')[1].lower()
            if mode in ['none', 'text', 'full']:
                image_mode = mode
            else:
                print(f"无效的image-mode值: {mode}，支持的值: none, text, full")
        elif arg.startswith('--max-rounds='):
            try:
                max_rounds = int(arg.split('=')[1])
            except ValueError:
                print(f"无效的max-rounds值: {arg}")
        elif arg.isdigit():
            max_rounds = int(arg)
    
    mode_desc = {
        'none': '无图片处理',
        'text': '仅图片文本描述',
        'full': '完整图片信息'
    }
    
    print("Azure OpenAI Responses API 智能对话客户端")
    print("="*60)
    print(f"图片模式: {mode_desc.get(image_mode, '未知模式')}")
    print(f"最大轮数: {max_rounds}")
    print("="*60)
    
    # 创建客户端
    client = create_client_with_default_functions()
    client.max_rounds = max_rounds
    
    # 初始对话输入
    initial_input = [
        {
            "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user", 
            # "content": "kkk.txt的主题，再去网上搜索一张这个主题的照片。"
            "content": "kkk.txt的主题，再去网上搜索三张这个主题的照片。"
        }
    ]
    
    print("开始智能对话...")
    print("初始请求: 读取kkk.txt的主题，并搜索相关图片")
    
    try:
        # 运行完整对话
        responses = client.run_conversation(initial_input, image_mode)
        
        print(f"\n{'='*60}")
        print(f"对话完成! 总共进行了 {len(responses)} 轮API调用")
        
        # 显示每轮的简要结果
        for i, response in enumerate(responses, 1):
            print(f"第{i}轮: ID={response.id[:8]}..., Tokens={response.usage.total_tokens}, APIM-ID={response.apim_request_id}")
        
        # 显示详细的token统计
        client.print_token_statistics(image_mode)
        
    except Exception as e:
        print(f"运行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

def demo_custom_usage():
    """演示如何自定义使用客户端"""
    print("\n" + "="*60)
    print("自定义使用演示")
    print("="*60)
    
    # 创建客户端
    client = create_client_with_default_functions()
    
    # 自定义对话
    custom_input = [
        {
            "role": "system",
            "content": "You are a helpful coding assistant."
        },
        {
            "role": "user",
            "content": "请读取当前目录下的Python文件，分析其功能。"
        }
    ]
    
    # 只允许3轮对话
    client.max_rounds = 3
    
    print("开始自定义对话...")
    responses = client.run_conversation(custom_input, image_mode='none')
    
    print(f"自定义对话完成! 进行了 {len(responses)} 轮调用")
    client.print_token_statistics(image_mode='none')

if __name__ == "__main__":
    # 显示使用说明
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help', 'help']:
        print("Azure OpenAI Responses API 智能对话客户端")
        print("="*50)
        print("使用说明:")
        print("python simple_responses_api_call.py [参数]")
        print("")
        print("参数选项:")
        print("  图片模式控制:")
        print("    full / with-image / true / 1    - 完整图片信息（默认）")
        print("    text / text-only               - 仅图片文本描述")
        print("    none / without-image / false   - 无图片处理")
        print("    --image-mode=MODE              - 明确指定模式(none|text|full)")
        print("  其他选项:")
        print("    --max-rounds=N / N             - 设置最大调用轮数（默认10）")
        print("    -h / --help / help             - 显示此帮助信息")
        print("    --demo                         - 运行自定义使用演示")
        print("")
        print("示例:")
        print("  python simple_responses_api_call.py")
        print("  python simple_responses_api_call.py full")
        print("  python simple_responses_api_call.py text --max-rounds=5")
        print("  python simple_responses_api_call.py none")
        print("  python simple_responses_api_call.py --image-mode=text")
        print("  python simple_responses_api_call.py --demo")
        print("")
        print("新功能:")
        print("  ✓ 支持任意多轮function call，自动执行直到完成")
        print("  ✓ 可复用的ResponsesAPIClient类")
        print("  ✓ 灵活的函数注册机制")
        print("  ✓ 智能token统计和缓存分析")
        print("  ✓ 可配置的最大轮数限制")
        sys.exit(0)
    
    # 检查是否运行演示
    if '--demo' in sys.argv:
        main()
        demo_custom_usage()
    else:
        main()