import json
import re
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison
    （中文注释：去除答案前缀和特殊字符，并转换为小写，保留内部空格）"""
    answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?)|["\'“”]', '', answer, flags=re.IGNORECASE)
    return answer.strip().lower()

def extract_answers(response):
    """Extract two answers using improved pattern matching.
    （中文注释：使用正则表达式从模型回答中提取两个答案，并返回剩余解释）"""
    # 优先使用正则匹配"final answer"格式，允许捕获多个单词
    final_answer_pattern = r'(?i)final\s*answer[:：\-]?\s*([a-zA-Z ]+)[,，]\s*([a-zA-Z ]+)(?:\n|$)'
    match = re.search(final_answer_pattern, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        explanation = response
        return normalize_answer(ans1), normalize_answer(ans2), explanation

    # 如果上面未匹配，尝试从回答第一行提取（整行）
    first_line = response.split('\n')[0].strip() if response else ""
    if first_line and ',' in first_line:
        parts = first_line.split(',', 1)
        if len(parts) == 2:
            potential_ans1 = parts[0].strip()
            potential_ans2 = parts[1].strip()
            return normalize_answer(potential_ans1), normalize_answer(potential_ans2), response[len(first_line):].strip()

    # Fallback: 在整个回答中寻找"word1, word2"模式（允许多个单词）
    answer_pattern = r'([a-zA-Z ]+),\s*([a-zA-Z ]+)'
    match = re.search(answer_pattern, response)
    if match:
        ans1 = match.group(1).strip()
        ans2 = match.group(2).strip()
        explanation = response[match.end():].strip()
        return normalize_answer(ans1), normalize_answer(ans2), explanation

    # Last resort: 提取至少两个单词
    words = re.findall(r'\b([a-zA-Z]+)\b', response)
    if len(words) >= 2:
        return normalize_answer(" ".join(words[:2])), "", ""
    
    return "", "", ""

# 1. Load JSON file（加载题目文件）
json_file = "/home/ltang24/Education/GRE Verbal two answers/GRE_Verbal_array_of_2_answers.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Limit to first 50 questions（仅取前50道题目）
questions = questions[:50]

# 2. Define main model and backup models (using only GPT models)
main_model = "gpt-4o"
backup_models = ["gpt-4", "gpt-4o-mini"]

# 3. Initialize client（初始化客户端）
client = Client()

print(f"Main Model: {main_model}")
print(f"Backup Models: {', '.join(backup_models)}")
print(f"Number of Test Questions: {len(questions)}")
print("Prompting Strategy: 3-shot (Final Answer Only)")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

# 定义3-shot示例（示例中只展示题目、选项及最终答案，无中间推理）
three_shot_examples = (
    "Below are three examples of GRE sentence equivalence questions with two blanks. For each, only the final answer is provided.\n\n"
    "Example 1:\n"
    "Question: The (i)_____ of molecular oxygen on Earth-sized planets around other stars in the universe would not be (ii)_____ sign of life.\n"
    "Options for Blank(i): dearth; presumption; detection\n"
    "Options for Blank(ii): a controversial; an unambiguous; a possible\n"
    "Final Answer: detection, an unambiguous\n\n"
    
    "Example 2:\n"
    "Question: Given the (i)_____ the committees and the (ii)_____ nature of its investigation, it would be unreasonable to gainsay the committee's conclusions at first glance.\n"
    "Options for Blank(i): sterling reputation of; lack of finding of; ad hoc existence of\n"
    "Options for Blank(ii): superficial; spontaneous; exhaustive\n"
    "Final Answer: sterling reputation of, exhaustive\n\n"
    
    "Example 3:\n"
    "Question: The economic recovery was somewhat lopsided: (i)_____ in some of the industrial economies while (ii)_____ in others.\n"
    "Options for Blank(i): unexpected; feeble; swift\n"
    "Options for Blank(ii): robust; turbulent; predictable\n"
    "Final Answer: feeble, robust\n\n"
)

# Process each question
for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer")  # 预期答案为数组，例如 ["detection", "an unambiguous"]
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # 构造3-shot提示：先给出3个示例，再附上当前题目；提示中只要求返回最终答案
    prompt = (
        three_shot_examples +
        "Now, solve the following GRE sentence equivalence question and provide ONLY your final answer in EXACT format (e.g., 'word1, word2'):\n\n" +
        f"Question: {content}\n"
    )
    for blank in sorted(options.keys()):
        prompt += f"{blank} options: " + "; ".join(options[blank]) + "\n"
    
    prompt += "\nFinal Answer:"
    
    messages = [{"role": "user", "content": prompt}]
    
    current_model = main_model
    response = ""
    is_correct = False
    model_tried = []
    
    while not is_correct and (current_model == main_model or backup_models):
        model_tried.append(current_model)
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                timeout=120,
                temperature=0.2
            ).choices[0].message.content.strip()
            
            # 提取两个答案和解释
            ans1, ans2, explanation = extract_answers(response)
            expected_normalized = [normalize_answer(e) for e in expected]
            
            # 检查答案是否正确（忽略顺序）
            answers_match = (
                (ans1 == expected_normalized[0] and ans2 == expected_normalized[1]) or
                (ans1 == expected_normalized[1] and ans2 == expected_normalized[0])
            )
            
            if ans1 and ans2:
                is_correct = answers_match
            else:
                print(f"  Unable to extract clear answers from {current_model}")
                
        except Exception as e:
            print(f"Error with {current_model} on Q{question_number}: {e}")
            ans1, ans2, explanation = "", "", ""
        
        runtime = time.perf_counter() - start_time
        
        if not (ans1 and ans2) and backup_models:
            current_model = backup_models.pop(0)
            print(f"  Trying backup model: {current_model}")
        else:
            break
    
    if is_correct:
        correct_count += 1
        print(f"  ✓ Correct ({ans1}, {ans2})")
    else:
        print(f"  ✗ Incorrect (Model answer: [{ans1}, {ans2}], Expected: {expected})")
    
    details.append({
        "question_number": question_number,
        "expected": expected,
        "models_tried": model_tried,
        "model_used": current_model,
        "model_answer": [ans1, ans2] if ans1 and ans2 else [],
        "model_explanation": explanation,
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

output_file = "GRE_Verbal_array_of_2_answers_3shot_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing complete. Results saved to: {output_file}")
