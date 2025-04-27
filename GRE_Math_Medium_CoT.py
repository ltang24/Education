import os
import re
import json
import time
import base64
from g4f.client import Client
from PIL import Image

def encode_image_to_base64(image_path):
    """Encode an image to base64 string format."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def normalize_answer(answer):
    """Normalize answers for consistent comparison.
    （中文注释：去除空格并转换为小写）"""
    return re.sub(r'\s', '', answer).lower()

def extract_expected_answer(answer_text):
    """Extract the actual answer from formats like '8. C' or 'C'
    （中文注释：从答案文本中提取实际答案）"""
    match = re.match(r'^\d+\.\s*([A-E,\s]+)$', answer_text)
    if match:
        return match.group(1).strip()
    return answer_text.strip()

def extract_answer(response, question_type):
    """Extract answer based on question type from model response.
    （中文注释：根据题目类型从模型回答中提取答案）"""
    if question_type == "Compare two quantities":
        pattern = r'(?:answer|choice|option|quantity)(?:is|:|\s)\s*([A-D])\.?'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        if re.search(r'\bquantity\s*a\s*(?:is)?\s*greater', response, re.IGNORECASE):
            return "A"
        if re.search(r'\bquantity\s*b\s*(?:is)?\s*greater', response, re.IGNORECASE):
            return "B"
        if re.search(r'\bequal\b|\bsame\b|\bidentical\b', response, re.IGNORECASE):
            return "C"
        if re.search(r'\bcannot\s*(?:be)?\s*determined\b|\binsufficient\b', response, re.IGNORECASE):
            return "D"
    
    elif question_type == "Single answer":
        pattern = r'(?:answer|choice|option)(?:is|:|\s)\s*([A-E])\.?'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        standalone = re.search(r'\b([A-E])\b', response, re.IGNORECASE)
        if standalone:
            return standalone.group(1).upper()
    
    elif question_type == "Multiple answers":
        pattern = r'(?:answers|choices|options)(?:are|is|:|\s)\s*([A-E](?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E](?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E]?(?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E]?(?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E]?)'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            answer_text = match.group(1)
            options = re.findall(r'[A-E]', answer_text, re.IGNORECASE)
            return ",".join([opt.upper() for opt in options])
        all_options = re.findall(r'\b([A-E])\b', response, re.IGNORECASE)
        if all_options:
            unique_options = []
            for opt in all_options:
                if opt.upper() not in unique_options:
                    unique_options.append(opt.upper())
            return ",".join(unique_options)
    
    elif question_type == "Enter exact number":
        number_pattern = r'(?:answer|result|value)(?:is|:|\s)\s*(-?\d+\.?\d*)'
        match = re.search(number_pattern, response, re.IGNORECASE)
        if match:
            return match.group(1)
        standalone = re.search(r'\b(-?\d+\.?\d*)\b', response)
        if standalone:
            return standalone.group(1)
    
    elif "Graphs" in question_type or "tables" in question_type or "charts" in question_type:
        pattern = r'(?:answer|choice|option)(?:is|:|\s)\s*([A-E])\.?'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        standalone = re.search(r'\b([A-E])\b', response, re.IGNORECASE)
        if standalone:
            return standalone.group(1).upper()
    
    return ""

def classify_question_type(response):
    """Classify the question type based on the model's response.
    （中文注释：根据模型返回的文本对题目类型进行分类）"""
    if re.search(r'quantity\s*a|quantity\s*b|quantit(?:y|ies)\s*(?:is|are)\s*(?:greater|equal|less)|compar(?:e|ing)\s*(?:the)?\s*(?:two)?\s*quantit(?:y|ies)', response, re.IGNORECASE):
        return "Compare two quantities"
    if re.search(r'(?:select|choose|pick)\s*(?:all|every|each)\s*(?:that|which|option)', response, re.IGNORECASE) or \
       re.search(r'(?:multiple|several)\s*(?:answers|options|choices)', response, re.IGNORECASE):
        return "Multiple answers"
    if re.search(r'(?:enter|type|write|give)\s*(?:an?)?\s*(?:exact|precise|specific)?\s*(?:number|value|answer)', response, re.IGNORECASE) or \
       re.search(r'(?:numerical|numeric)\s*(?:answer|value|response)', response, re.IGNORECASE):
        return "Enter exact number"
    if re.search(r'(?:graph|table|chart|diagram|figure)', response, re.IGNORECASE):
        return "Graphs, tables, charts"
    return "Single answer"

def safe_api_call(model, messages, timeout, max_retries=3, delay=2):
    """
    安全地调用API，如果失败则重试。
    （中文注释：当API调用失败时，采用重试策略，延时后再尝试）
    """
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=timeout
            ).choices[0].message.content.strip()
            return response
        except Exception as e:
            print(f"  Error with {model} on attempt {attempt+1}: {e}")
            time.sleep(delay * (attempt + 1))
    return ""

# 设置图片目录和答案文件路径
image_dir = "/home/ltang24/Education/GRE Math Medium"
answer_file = "/home/ltang24/Education/GRE Math Medium.txt"

# 从文本文件中加载答案（只取前50道题目）
with open(answer_file, "r") as f:
    answers = f.read().strip().split("\n")
answers = answers[:50]

# 定义模型
main_model = "gpt-4"  # 具备视觉能力的主模型
backup_models = ["gpt-4o-mini"]  # 备用视觉模型

# 初始化客户端
client = Client()

print(f"Main model: {main_model}")
print(f"Backup models: {', '.join(backup_models)}")
print(f"Processing {len(answers)} GRE Math questions from images...")
print("-" * 100)

results = {
    "total_questions": len(answers),
    "correct_count": 0,
    "accuracy": 0,
    "questions": []
}

answered_count = 0  # 仅记录有答案的题目数

# 处理每道题目
for i in range(1, len(answers) + 1):
    question_number = i
    image_path = os.path.join(image_dir, f"{i}.png")
    raw_expected_answer = answers[i-1].strip()
    expected_answer = extract_expected_answer(raw_expected_answer)
    
    print(f"Processing question {question_number}...")
    print(f"  Raw expected answer: {raw_expected_answer}")
    print(f"  Cleaned expected answer: {expected_answer}")
    
    if not os.path.exists(image_path):
        print(f"  Image not found: {image_path}")
        continue
    
    try:
        base64_image = encode_image_to_base64(image_path)
    except Exception as e:
        print(f"  Error encoding image: {e}")
        continue
    
    # 首先确定题目类型
    classification_prompt = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please examine this GRE math question and classify it into one of these categories: 'Compare two quantities', 'Single answer', 'Multiple answers', 'Enter exact number', or 'Graphs, tables, charts'. Just tell me the category name and don't solve the problem yet."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]
    
    classification_response = safe_api_call(main_model, classification_prompt, timeout=60)
    if classification_response:
        question_type = classify_question_type(classification_response)
        print(f"  Classified as: {question_type}")
    else:
        print("  Error classifying question; defaulting to 'Single answer'")
        question_type = "Single answer"
    
    # 使用链式思考 (CoT) 解决题目，要求模型在第一行给出最终答案
    # 这里优化提示，明确要求分步推理
    solving_prompt = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"This is a GRE math question of type '{question_type}'. Please solve it using chain-of-thought reasoning. Begin your response with your final answer in EXACT format as follows:\nFINAL ANSWER: X\nThen provide a detailed step-by-step explanation of how you solved the problem."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]
    
    is_correct = False
    models_tried = []
    best_answer = ""
    best_response = ""
    best_model = ""
    runtime = 0
    
    available_models = [main_model] + backup_models
    for model in available_models:
        models_tried.append(model)
        start_time = time.perf_counter()
        response = safe_api_call(model, solving_prompt, timeout=120)
        if not response:
            continue
        try:
            answer = extract_answer(response, question_type)
        except Exception as ex:
            print(f"  Error extracting answer with {model} on question {question_number}: {ex}")
            answer = ""
        
        if answer:
            if question_type == "Multiple answers":
                answer_set = set(answer.split(","))
                expected_set = set(expected_answer.split(","))
                current_is_correct = answer_set == expected_set
            else:
                current_is_correct = normalize_answer(answer) == normalize_answer(expected_answer)
            if current_is_correct:
                is_correct = True
                best_answer = answer
                best_response = response
                best_model = model
                runtime = time.perf_counter() - start_time
                break
            elif not best_answer:
                best_answer = answer
                best_response = response
                best_model = model
        runtime = time.perf_counter() - start_time
    
    if best_answer:
        answered_count += 1
        if is_correct:
            results["correct_count"] += 1
    
    question_result = {
        "question_number": question_number,
        "question_type": question_type,
        "expected": expected_answer,
        "raw_expected": raw_expected_answer,
        "models_tried": models_tried,
        "model_used": best_model,
        "model_answer": best_answer,
        "model_response": best_response,
        "runtime": round(runtime, 2),
        "correct": is_correct,
        "image_path": image_path
    }
    
    results["questions"].append(question_result)
    current_accuracy = results["correct_count"] / answered_count if answered_count > 0 else 0
    print(f"  Answer: {best_answer}, Expected: {expected_answer}, Correct: {is_correct}")
    print(f"  Current accuracy (answered only): {current_accuracy:.2%}")

final_accuracy = results["correct_count"] / answered_count if answered_count > 0 else 0
results["total_answered"] = answered_count
results["accuracy"] = final_accuracy

print(f"Overall Accuracy (only for answered questions): {final_accuracy:.2%}")
print(f"Correct answers: {results['correct_count']}/{answered_count}")
print("-" * 100)

output_file = "GRE_Math_Medium_CoT_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")
