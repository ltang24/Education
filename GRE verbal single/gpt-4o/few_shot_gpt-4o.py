import json
import re
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison
    （中文注释：去除答案前缀和特殊字符，并转换为小写）"""
    answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?\s*)|["\'“”]', '', answer, flags=re.IGNORECASE)
    return answer.strip().lower().replace(' ', '')

def extract_answer(response):
    """Extract the answer letter from the model's response.
    （中文注释：从模型回答中提取答案字母）"""
    response_upper = response.upper()
    
    # 尝试从明确标记后提取答案
    final_answer_patterns = [
        r'FINAL ANSWER[:：\s]*([A-E])',
        r'ANSWER[:：\s]*([A-E])',
        r'I CHOOSE[:：\s]*([A-E])',
        r'SELECTED ANSWER[:：\s]*([A-E])',
        r'BEST OPTION[:：\s]*([A-E])'
    ]
    
    for pattern in final_answer_patterns:
        match = re.search(pattern, response_upper)
        if match:
            return match.group(1)
    
    # 尝试从第一行提取
    first_line = response_upper.split('\n')[0].strip()
    match = re.match(r'^([A-E])[.:]?$', first_line)
    if match:
        return match.group(1)
    
    match = re.search(r'\b([A-E])\b', first_line)
    if match:
        return match.group(1)
    
    # 在整个回答中查找
    match = re.search(r'\b([A-E])\b', response_upper)
    if match:
        return match.group(1)
    
    match = re.search(r'([A-E])', response_upper)
    if match:
        return match.group(1)
    
    return ""

# 1. Load JSON file（加载题目文件）
json_file = "/home/ltang24/Education/GRE verbal single/GRE_Verbal_single_answer.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Limit to first 50 questions（仅取前50道题目）
questions = questions[:50]

# 2. Define main model and backup models (using only GPT models)
main_model = "gpt-4o"
backup_models = ["gpt-4"]

# 3. Initialize g4f client（初始化客户端）
client = Client()

print(f"Main Model: {main_model}")
print(f"Backup Models: {', '.join(backup_models)}")
print(f"Number of Test Questions: {len(questions)}")
print("Prompting Strategy: 3-shot (final answer only)")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

# 定义3-shot示例（示例中仅展示题目、选项及最终答案，不含链式推理）
three_shot_examples = (
    "Below are three examples of GRE single-answer questions:\n\n"
    "Example 1:\n"
    "Question: Concerned about the growing tendency of universities to sometimes reward celebrity more generously than specialized expertise, many academics have deplored the search for ____________ to which that practice leads.\n"
    "Options:\n"
    "A: pprobation\n"
    "B: ollegiality\n"
    "C: rudition\n"
    "D: enown\n"
    "E: rowess\n"
    "Final Answer: D\n\n"
    
    "Example 2:\n"
    "Question: My grandma has a strong belief in all things _____: she insists, for example, that the house in which she lived as a child was haunted.\n"
    "Options:\n"
    "A: lamorous\n"
    "B: nvidious\n"
    "C: uminous\n"
    "D: mpirical\n"
    "E: onorous\n"
    "Final Answer: C\n\n"
    
    "Example 3:\n"
    "Question: Genetic diversity is the raw material of evolution including the domestication of plants, yet the domestication process typically ____________ diversity because the first domesticates are derived from a very small sample of the individual plants.\n"
    "Options:\n"
    "A: recludes a reduction in\n"
    "B: ncreases the potential for\n"
    "C: nvolves a loss of\n"
    "D: educes the importance of\n"
    "E: bscures the source of\n"
    "Final Answer: C\n\n"
)

# Process each question
for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer").strip().upper()  # 预期答案为单个字母，例如 "D"
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # 构造3-shot提示：先给出3个示例，再附上当前题目；提示中只要求模型返回最终答案
    prompt = (
        three_shot_examples +
        "Now, solve the following question and provide only the final answer in EXACT format as follows:\n"
        "Final Answer: X\n\n" +
        f"Question: {content}\n"
        "Options:\n"
    )
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    messages = [{"role": "user", "content": prompt}]
    
    # 尝试使用主模型和备用模型
    current_model = main_model
    response = ""
    is_correct = False
    models_tried = []
    
    while not is_correct and (current_model == main_model or backup_models):
        models_tried.append(current_model)
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                timeout=120,
                temperature=0.3
            ).choices[0].message.content.strip()
            
            # 提取最终答案字母
            answer_extracted = extract_answer(response)
            is_correct = (answer_extracted == expected)
            
            if not answer_extracted:
                print(f"  Unable to extract answer from response, model: {current_model}")
                
        except Exception as e:
            print(f"Model {current_model} error on question {question_number}: {e}")
            answer_extracted = ""
        
        runtime = time.perf_counter() - start_time
        
        if not answer_extracted and backup_models:
            current_model = backup_models.pop(0)
            print(f"  Trying backup model: {current_model}")
        else:
            break
    
    if is_correct:
        correct_count += 1
        print(f"  ✓ Correct ({answer_extracted})")
    else:
        print(f"  ✗ Incorrect (Model: {answer_extracted}, Expected: {expected})")
    
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
    
    print("-" * 50)

accuracy = correct_count / total if total > 0 else 0
print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct Answers: {correct_count}/{total}")
print("-" * 100)

results = {
    "strategy": "3-shot",
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

output_file = "GRE_Verbal_3shot_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing complete. Results saved to: {output_file}")
