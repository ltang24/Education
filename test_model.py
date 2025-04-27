from g4f.client import Client

client = Client()

models = [
    'gpt-4o',
    'gpt-4',
    'blackboxai-pro',
    'blackboxai',
    'gpt-4o-mini',
    "gemini-1.5-pro", 
    "gemini-1.5-flash", 
    'llama-3.1-405b',
    'llama-3.1-70b',
    'llama-3.1-8b',
    'claude-3.5-sonnet',
    
    # Claude models
    'claude-3-opus',
    'claude-3-haiku',
    'claude-3-sonnet',
    'claude-2',
    'claude-instant',
    
    # Anthropic models
    'claude-3.7-sonnet',
    
    # Meta/Llama models
    'llama-2-70b',
    'llama-2-13b',
    'llama-2-7b',
    'llama-3-8b',
    'llama-3-70b',
    
    # Google models
    'gemini-1.0-pro',
    'palm-2',
    
    # Mistral models
    'mistral-7b',
    'mistral-8x7b',
    'mixtral-8x7b',
    'mistral-medium',
    'mistral-small',
    'mistral-large',
    
    # Cohere models
    'command',
    'command-light',
    'command-nightly',
    'command-r',
    'command-r-plus',
    
    # Anthropic additional models
    'claude-instant-1.2',
    
    # Other providers
    'yi-34b',
    'yi-6b',
    'falcon-7b',
    'falcon-40b',
    'qwen-14b',
    'qwen-7b',
    'deepseek-coder',
    'j2-ultra',
    'j2-mid'
]

print("开始测试各个模型是否可用...\n")
available_models = []
for model in models:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "测试是否可用"}],
            timeout=60
        ).choices[0].message.content.strip()
        print(f"模型 {model} 可用, 返回：{response}")
        available_models.append(model)
    except Exception as e:
        print(f"模型 {model} 不可用, 错误：{e}")

print("\n可用模型列表:", available_models)
