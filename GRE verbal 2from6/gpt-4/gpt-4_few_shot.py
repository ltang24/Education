import json
import re
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison
    （中文注释：去除所有非字母数字字符，并转换为大写）"""
    # 将答案中所有非字母数字字符（包括点、空格、标点等）移除
    answer = re.sub(r'[^\w]', '', answer)
    return answer.strip().upper()

def extract_option_answers(response):
    """Extract two letter options (A-F) from the model's response.
    （中文注释：使用正则表达式从模型回答中提取两个选项）"""
    simple_pattern = r'([A-F])\.?\s*,\s*([A-F])\.?'
    simple_match = re.search(simple_pattern, response, re.IGNORECASE)
    if simple_match:
        return [normalize_answer(simple_match.group(1)), normalize_answer(simple_match.group(2))]
    
    period_pattern = r'([A-F])\..*?([A-F])\.'
    period_match = re.search(period_pattern, response, re.IGNORECASE)
    if period_match:
        return [normalize_answer(period_match.group(1)), normalize_answer(period_match.group(2))]
    
    line_pattern = r'(?:^|\n)([A-F])\.?.*?(?:^|\n)([A-F])\.?'
    line_match = re.search(line_pattern, response, re.IGNORECASE | re.MULTILINE)
    if line_match:
        return [normalize_answer(line_match.group(1)), normalize_answer(line_match.group(2))]
    
    # 如果未匹配，返回空字符串
    return ["", ""]

# 1. Load JSON file（加载题目文件）
json_file = "/home/ltang24/Education/GRE verbal 2from6/GRE_Verbal_array_of_two_options_from_6_answers.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Limit to first 50 questions（仅取前50道题目）
questions = questions[:50]

# 2. Define main model and backup models
main_model = "gpt-4"
backup_models = ["gpt-4o", "gpt-4o-mini"]

# 3. Initialize client（初始化客户端）
client = Client()

print(f"Main model: {main_model}")
print(f"Backup models: {', '.join(backup_models)}")
print(f"Testing {len(questions)} questions")
print("Prompting Strategy: 5-shot (Final Answer Only)")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

# 定义5-shot示例（示例中只展示题目、选项及最终答案，无中间推理）
five_shot_examples = (
    "Below are five examples of GRE sentence equivalence questions with two blanks. For each, ONLY the final answer is provided in EXACT format (do NOT include any additional explanation).\n\n"
    
    "Example 1:\n"
    "Question: The beauty of the scientific approach is that even when individual researchers do _____ bias or partiality, others can correct them using a framework of evidence on which everyone broadly agrees.\n"
    "Options:\n"
    "A: verreact to\n"
    "B: eviate from\n"
    "C: uccumb to\n"
    "D: ecoil from\n"
    "E: ield to\n"
    "F: hrink from\n"
    "Final Answer: C, E\n\n"
    
    "Example 2:\n"
    "Question: The reconstruct known work is beautiful and also probably _____: it is the only Hebrew verse written by a woman.\n"
    "Options:\n"
    "A: ingular\n"
    "B: nique\n"
    "C: rchaic\n"
    "D: counterfeit\n"
    "E: aluable\n"
    "F: ake\n"
    "Final Answer: A, B\n\n"
    
    "Example 3:\n"
    "Question: In a book that inclines to _____, an epilogue arguing that ballet is dead arrives simply as one more overstatement.\n"
    "Options:\n"
    "A: essimism\n"
    "B: isinterpretation\n"
    "C: mprecision\n"
    "D: agueness\n"
    "E: xaggeration\n"
    "F: yperbole\n"
    "Final Answer: E, F\n\n"
    
    "Example 4:\n"
    "Question: The political upheaval caught most people by surprise: despite the _____ warnings of some commentators, it had never seemed that imminent.\n"
    "Options:\n"
    "A: tern\n"
    "B: rescient\n"
    "C: rophetic\n"
    "D: ndifferent\n"
    "E: epeated\n"
    "F: pathetic\n"
    "Final Answer: B, C\n\n"
    
    "Example 5:\n"
    "Question: Members of the union's negotiating team insisted on several changes to the company's proposal before they would support it, making it clear that they would _____ no compromise.\n"
    "Options:\n"
    "A: isclose\n"
    "B: eject\n"
    "C: rook\n"
    "D: olerate\n"
    "E: epudiate\n"
    "F: eigh\n"
    "Final Answer: C, D\n\n"
)

# Process each question
for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer")  # 预期答案为数组，例如 ["C.", "E."]
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # 构造5-shot提示：先给出5个示例，再附上当前题目；提示中要求模型仅返回最终答案（不附加任何解释）
    prompt = (
        five_shot_examples +
        "Now, solve the following GRE sentence equivalence question and provide ONLY your final answer in EXACT format (e.g., 'X, Y') with no additional text:\n\n" +
        f"Question: {content}\n"
    )
    for key, value in options.items():
        prompt += f"{key}: {value}\n"
    
    prompt += "\nFinal Answer:"
    
    messages = [{"role": "user", "content": prompt}]
    
    current_model = main_model
    response = ""
    is_correct = False
    models_tried = []
    best_answers = ["", ""]
    best_response = ""
    best_model = ""
    runtime = 0
    
    available_models = [main_model] + backup_models
    for model in available_models:
        models_tried.append(model)
        
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=60,
                temperature=0.3
            ).choices[0].message.content.strip()
            
            # 提取两个答案
            answers = extract_option_answers(response)
            # 对提取答案进行归一化处理并排序（忽略顺序）
            expected_normalized = sorted([normalize_answer(e) for e in expected])
            if len(answers) == 2 and all(a for a in answers):
                if sorted(answers) == expected_normalized:
                    is_correct = True
                best_answers = answers
            
        except Exception as e:
            print(f"Error with {model} on Q{question_number}: {e}")
            best_answers = ["", ""]
        
        runtime = time.perf_counter() - start_time
        
        if is_correct:
            best_model = model
            break
        elif not best_answers[0] and not best_answers[1] and backup_models:
            current_model = backup_models.pop(0)
            print(f"  Trying backup model: {current_model}")
        else:
            break
    
    if is_correct:
        correct_count += 1
        print(f"  ✓ Correct ({best_answers[0]}, {best_answers[1]})")
    else:
        print(f"  ✗ Incorrect (Model answer: {best_answers}, Expected: {expected})")
    
    details.append({
        "question_number": question_number,
        "expected": expected_normalized,
        "models_tried": models_tried,
        "model_used": best_model if best_model else current_model,
        "model_answer": best_answers if best_answers[0] and best_answers[1] else [],
        "model_response": best_response if best_response else response,
        "runtime": round(runtime, 2),
        "correct": is_correct
    })
    
    print("-" * 50)

accuracy = correct_count / total if total > 0 else 0
print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct Answers: {correct_count}/{total}")
print("-" * 100)

results = {
    "strategy": "5-shot",
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

output_file = "5shot_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")
