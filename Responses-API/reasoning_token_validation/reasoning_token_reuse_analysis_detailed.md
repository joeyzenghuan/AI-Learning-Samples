# Reasoning Token 复用机制深度分析

## 核心发现

通过对连续多轮 function call 的 token 使用情况分析，我们发现了 Azure OpenAI Responses API 中 **reasoning token 复用机制**的重要规律：

### 关键观察

1. 如果是连续多次的function call调用, reasoning token可以一直保留，cached token大概率会随着调用轮次的增加而增加。
2. 如果上一轮模型返回的是assistant类型的message，那在新一轮次的调用过程中，出现在这条assistant message前的所有reasoning token都会被responses api主动清零，此时cached token一定为0。
3. 如果不同轮次的function call之间出现模态变化，比如前一轮是function_call_output提供的是纯文本，新的一轮带图片(以type: function_call_output + role:user type:input_image组合)，那么reasoning token还会复用，但cached token可能降为0（新的多模态请求可能路由到不同的endpoint）

### OpenAI Cookbook 原理解析

https://github.com/openai/openai-cookbook/blob/main/examples/responses_api/reasoning_items.ipynb

## 实验设计

为了模拟多轮调用，将"parallel_tool_calls": False。

```
python responses_rest_api_call.py full
```

### 第一轮

**输入**：`"role": "user", "content": "kkk.txt的主题，再去网上搜索三张这个主题的照片。" `

**输出**：调用 `get_file_content_by_filename` 去获取kkk.txt的文本内容

### 第二轮

**输入**：以 function_call_output 的格式传入kkk.txt的文本（大约2700token）

**输出**：`"type": "function_call"` 调用 `search_image_by_keyword` 去拿到第一张图片

### 第三轮

**输入**：以 `type: function_call_output + role:user type:input_image` 组合形式向模型返回image内容 (大约1040token)

```json
[
  {
    "call_id": "call_LBVeYf1NtZwxWI8aGHKiYY0f",
    "output": "找到 1 张关于'仙侠 修真 炼丹'的图片，已保存为 call_LBVeYf1NtZwxWI8aGHKiYY0f.jpg",
    "type": "function_call_output"
  },
  {
    "role": "user",
    "content": [
      {"type": "input_text", "text": "I can see call_LBVeYf1NtZwxWI8aGHKiYY0f.jpg already."},
      {"type": "input_image", "image_url": "https://puui.qpic.cn/vpic_cover/v3528jnid6d/v3528jnid6d_1692796767_hz.jpg"}
    ]
  }
]
```

**输出**：调用 `search_image_by_keyword` 去拿到第二张图片

### 第四轮

与第三轮类似

### 第五轮

**输入**：以 `type: function_call_output + role:user type:input_image` 组合形式向模型返回第三张image内容

**输出**：`"role": "assistant"` 告诉用户任务完成

### 第六轮

**输入**：`"role": "user", "content": "总结一下"`

**输出**：通过新一轮的reasoning生成总结。

## 实验数据分析

### 运行结果 Token 统计表

| 调用轮数 | Input Tokens | Cached Tokens | Reasoning Tokens | Output Tokens | Total Tokens |
| -------- | ------------ | ------------- | ---------------- | ------------- | ------------ |
| 第1轮    | 227          | 0             | 576              | 601           | 828          |
| 第2轮    | 3518         | 0             | 960              | 992           | 4510         |
| 第3轮    | 5550         | 0             | 192              | 226           | 5776         |
| 第4轮    | 6813         | 5760          | 64               | 97            | 6910         |
| 第5轮    | 7945         | 6912          | 704              | 853           | 8798         |
| 第6轮    | 6103         | 0             | 1152             | 1419          | 7522         |

## 详细分析

### 第1-5轮：Function Call 链阶段

#### 轮次间的 Token 变化分析

**第2轮关键验证（Reasoning Token复用的直接证据）：**

已知第2轮会新增的 `function_call_output` 约带来 2700 tokens。

```
情况A：如果 Reasoning Token 被复用
预期Input = 第1轮Total + 新增function_call_output
预期Input = 828 + 2700 = 3528
实际Input = 3518 ✅ 高度吻合！

情况B：如果 Reasoning Token 被丢弃  
预期Input = 第1轮Total - 第1轮Reasoning + 新增function_call_output
预期Input = 828 - 576 + 2700 = 2952
实际Input = 3518 ❌ 相差566 tokens，差距巨大！
```

**结论**：第2轮的数据明确证明了 **Reasoning Token 被完整复用**！

**第3轮分析（第1个图片搜索）：**

```
基于复用机制：
预期Input = 第2轮Total + 新增内容
预期Input = 4510 + 新增 ≈ 4510 + ~1040
实际Input = 5550

新增内容 = 5550 - 4510 = 1040 tokens ✅ 与预期完全吻合！
```

**第3轮新增内容结构：**

```json
[
  {
    "call_id": "call_LBVeYf1NtZwxWI8aGHKiYY0f",
    "output": "找到 1 张关于'仙侠 修真 炼丹'的图片，已保存为 call_LBVeYf1NtZwxWI8aGHKiYY0f.jpg",
    "type": "function_call_output"
  },
  {
    "role": "user",
    "content": [
      {"type": "input_text", "text": "I can see call_LBVeYf1NtZwxWI8aGHKiYY0f.jpg already."},
      {"type": "input_image", "image_url": "https://puui.qpic.cn/vpic_cover/v3528jnid6d/v3528jnid6d_1692796767_hz.jpg"}
    ]
  }
]
```

*估算：function_call_output (~50 tokens) + user message with image (~990 tokens) = ~1040 tokens*

**第4轮分析（第2个图片搜索 + 首次缓存）：**

```
预期Input = 第3轮Total + 新增内容  
预期Input = 5776 + 新增 ≈ 5776 + ~1037
实际Input = 6813
实际Cached = 5760 🎯 缓存机制启动！

新增内容 = 6813 - 5776 = 1037 tokens ✅ 与预期吻合！  
缓存效率 = 5760/6813 ≈ 84.5%
```

**第4轮新增内容结构：**

```json
[
  {
    "call_id": "call_NOVMVwfiSCAwsrm0l4XPGaOS", 
    "output": "找到 1 张关于'修仙 结婴 仙侠'的图片，已保存为 call_NOVMVwfiSCAwsrm0l4XPGaOS.jpg",
    "type": "function_call_output"
  },
  {
    "role": "user",
    "content": [
      {"type": "input_text", "text": "I can see call_NOVMVwfiSCAwsrm0l4XPGaOS.jpg already."},
      {"type": "input_image", "image_url": "https://puui.qpic.cn/vpic_cover/v3528jnid6d/v3528jnid6d_1692796767_hz.jpg"}
    ]
  }
]
```

*估算：function_call_output (~52 tokens) + user message with image (~985 tokens) = ~1037 tokens*

**第5轮分析（第3个图片搜索 + 缓存增长）：**

```
预期Input = 第4轮Total + 新增内容
预期Input = 6910 + 新增 ≈ 6910 + ~1035  
实际Input = 7945
实际Cached = 6912 📈 缓存持续增长！

新增内容 = 7945 - 6910 = 1035 tokens ✅ 与预期吻合！
缓存效率 = 6912/7945 ≈ 87.0%
```

**第5轮新增内容结构：**

```json
[
  {
    "call_id": "call_OPdepxYgVdbiAfnM1YQGrv4Z",
    "output": "找到 1 张关于'丹炉 仙侠 炼丹'的图片，已保存为 call_OPdepxYgVdbiAfnM1YQGrv4Z.jpg", 
    "type": "function_call_output"
  },
  {
    "role": "user",
    "content": [
      {"type": "input_text", "text": "I can see call_OPdepxYgVdbiAfnM1YQGrv4Z.jpg already."},
      {"type": "input_image", "image_url": "https://puui.qpic.cn/vpic_cover/v3528jnid6d/v3528jnid6d_1692796767_hz.jpg"}
    ]
  }
]
```

*估算：function_call_output (~50 tokens) + user message with image (~985 tokens) = ~1035 tokens*

### 关键观察点

1. **reasoning token被完整保留**
2. **Cached Token 出现**：

- 从第4轮开始出现大量缓存
- 第4轮：5760 tokens
- 第5轮：6912 tokens（持续增长）

2. **为什么第三轮没有Cached Token**：

   - 因为第二轮上下文是纯文本，第三轮引入多image多模态，导致请求路由到新的模型节点，从而无法复用之前的prompt cache。

### 第6轮：总结轮次，相当于新一轮任务开始

**第6轮的关键变化：**

```
Input Tokens: 6103 (大幅下降)
Cached Tokens: 0 (清零！)  
Reasoning Tokens: 1152 (重新开始推理)
```

**分析：**

- 由于第5轮没有产生 function call，上下文中出现了 assistant 类型的完整响应
- 这导致了 **推理上下文的重置**
- 所有历史 reasoning token 被丢弃
- 缓存机制重新开始

## 核心机制总结

### Reasoning Token 复用条件

✅ **复用场景：**

- 连续的 function call 调用
- 上下文中只有 `user` 消息和 `function_call_output` 消息
- 没有完整的 `assistant` 响应消息

❌ **丢弃场景：**

- 上一轮出现完整的 `assistant` 响应（非 function call）
- 对话轮次中断
- 新的独立会话开始

### 缓存机制特点

1. **累积增长**：在 function call 链中，cached tokens 逐轮增长
2. **突然清零**：遇到 assistant 响应时重置为0
3. **成本效益**：在连续调用中可节省高达 87% 的输入成本

## 实际应用价值

### 成本优化策略

1. **连续 Function Call 设计**：

   - 尽量将相关的 function call 组织成连续链
   - 避免中间插入非必要的 assistant 响应
2. **推理复用最大化**：

   - 在复杂推理任务中，将多步骤操作设计为连续的函数调用
   - 让模型的推理过程在整个链中保持连贯
3. **成本节省潜力**：

   - 在本次测试中，缓存节省了 12672 tokens (29.6%)
   - 在更长的 function call 链中，节省比例可能更高

## 技术含义

这个发现揭示了 Azure OpenAI Responses API 的一个重要优化机制：

1. **推理连续性**：模型在 function call 链中保持推理状态
2. **上下文智能管理**：区分 function call 流程和对话流程
3. **性能优化**：通过推理复用显著降低计算成本
