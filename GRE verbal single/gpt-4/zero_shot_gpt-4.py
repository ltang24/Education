import json
import re
import time
from g4f.client import Client

def extract_answer(response):
    """Extract the answer letter from the model's response"""
    response_upper = response.upper()
    
    # First try to find a standalone letter at the beginning of the response
    first_line = response_upper.split('\n')[0].strip()
    match = re.match(r'^([A-E])[.:]?$', first_line)
    if match:
        return match.group(1)
    
    # Then try to find any standalone letter in the first line
    match = re.search(r'\b([A-E])\b', first_line)
    if match:
        return match.group(1)
    
    # If that fails, try to find any standalone letter in the entire response
    match = re.search(r'\b([A-E])\b', response_upper)
    if match:
        return match.group(1)
    
    # Last resort: try to find any letter (even if not standalone)
    match = re.search(r'([A-E])', response_upper)
    if match:
        return match.group(1)
    
    return ""

# 1. 加载 JSON 文件
json_file = "/home/ltang24/Education/GRE verbal single/GRE_Verbal_single_answer.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# 限制为前 50 个问题
questions = questions[:50]

# 2. 定义主模型和备用模型（只使用 GPT 模型）
main_model = "gpt-4"
backup_models = ["gpt-4o", "gpt-3.5-turbo", "gpt-4-0125-preview"]

# 3. 初始化 g4f 客户端
client = Client()

print(f"主模型: {main_model}")
print(f"备用模型: {', '.join(backup_models)}")
print(f"测试题目数量: {len(questions)}")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer").strip().upper()  # 预期答案为字母，如 "D"
    
    print(f"处理问题 {i+1}/{total} (Q{question_number})...")
    
    # 构造更明确的提示
    prompt = (
        "请阅读下面的GRE题目，选择最合适的答案。\n\n"
        f"题目：{content}\n"
        "选项：\n"
    )
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\n重要提示：请按照以下格式回答：\n"
    prompt += "A\n"
    prompt += "解释：此处填写您的解释\n\n"
    prompt += "您的答案必须是单独的一个大写字母（A/B/C/D/E），不要有任何额外的字符或标点。"
    
    messages = [{"role": "user", "content": prompt}]
    
    # 先尝试主模型
    current_model = main_model
    response = ""
    is_correct = False
    models_tried = []
    
    while not is_correct and (current_model == main_model or backup_models):
        models_tried.append(current_model)  # 记录尝试过的模型
        
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                timeout=60
            ).choices[0].message.content.strip()
            
            # 提取答案字母
            answer_extracted = extract_answer(response)
            
            # 检查答案是否正确
            is_correct = (answer_extracted == expected)
            
            # 如果无法提取答案，需要尝试另一个模型
            if not answer_extracted:
                is_correct = False
                
        except Exception as e:
            print(f"模型 {current_model} 在题目 {question_number} 处理出错: {e}")
            answer_extracted = ""
        
        runtime = time.perf_counter() - start_time
        
        # 如果不正确并且还有备用模型，尝试下一个模型
        if not is_correct and backup_models:
            current_model = backup_models.pop(0)
            print(f"  尝试备用模型: {current_model}")
        else:
            break
    
    if is_correct:
        correct_count += 1
    
    # 记录详细信息
    details.append({
        "question_number": question_number,
        "expected": expected,
        "models_tried": models_tried,
        "model_used": current_model,
        "model_answer": answer_extracted,
        "model_response": response,
        "runtime": round(runtime, 2),
        "correct": is_correct
    })

accuracy = correct_count / total if total > 0 else 0
print(f"总体准确率: {accuracy:.2%}")
print(f"正确答案数: {correct_count}/{total}")
print("-" * 100)

results = {
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

# 保存结果
output_file = "zero_shot_gpt-4o.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"测试完成。结果已保存到: {output_file}")