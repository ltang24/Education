import json
import re
import time
from collections import defaultdict
from g4f.client import Client

def normalize_answer(answer):
    """Normalize an answer (string or numeric) for consistent comparison."""
    if isinstance(answer, str):
        return re.sub(r'\s+', '', answer.strip().lower())
    return str(answer).strip().lower()

def extract_answer(response):
    """
    Extract answer from response.
    对于Quant题目，通常只需返回答案字母（或数字）即可。
    如果答案中包含 "Final Answer:" 等前缀，则提取后面的答案字母。
    """
    match = re.search(r"final\s*answer\s*[:：]?\s*([A-Ea-e])", response, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip().upper()
    return response.strip().upper()

# 针对Problem Solving题目的prompt生成函数（零样本）
def generate_zero_shot_prompt_PS(item):
    qtype = item.get("subtype-type", "")
    question_text = item.get("question", "")
    options = item.get("options", {})
    prompt = (f"Please solve the following GRE Quantitative Reasoning Problem Solving question "
              f"of type '{qtype}' and provide only the SINGLE BEST letter answer (A/B/C/D/E).\n\n")
    prompt += f"Question: {question_text}\nOptions:\n"
    for letter, opt in options.items():
        prompt += f"{letter}: {opt}\n"
    prompt += "\nImportant: Answer with ONLY the selected letter."
    return prompt

# 针对Problem Solving题目的prompt生成函数（五样本提示）
def generate_five_shot_prompt_PS(item):
    qtype = item.get("subtype-type", "")
    examples = [
        {
            "question": "Example: A city’s population increased and its GDP changed accordingly. What is the percent change in per capita GDP?",
            "options": {
                "A": "10% decrease",
                "B": "15% increase",
                "C": "20% increase",
                "D": "25% increase",
                "E": "30% increase"
            },
            "final_answer": "C"
        },
        {
            "question": "Example: A box contains red and blue balls. What is the probability of drawing one red and one blue?",
            "options": {
                "A": "1/20",
                "B": "1/10",
                "C": "3/10",
                "D": "1/2",
                "E": "3/5"
            },
            "final_answer": "D"
        },
        {
            "question": "Example: Solve the equation 4m + n = 20 for integers m and n. How many solutions exist?",
            "options": {
                "A": "Five",
                "B": "Six",
                "C": "Ten",
                "D": "Eleven",
                "E": "Forty-one"
            },
            "final_answer": "D"
        },
        {
            "question": "Example: Company sales and cost data lead to a profit calculation. What is the profit?",
            "options": {
                "A": "$2,250 loss",
                "B": "$750 loss",
                "C": "No profit or loss",
                "D": "$2,250 profit",
                "E": "$18,000 profit"
            },
            "final_answer": "D"
        },
        {
            "question": "Example: In a parallelogram with sides in ratio 1:2 and given area, find the area of the inscribed rectangle.",
            "options": {
                "A": "36",
                "B": "36√2",
                "C": "72",
                "D": "96",
                "E": "144"
            },
            "final_answer": "C"
        }
    ]
    prompt = (f"Below are five examples of GRE Quantitative Reasoning Problem Solving questions of type '{qtype}':\n\n")
    for idx, ex in enumerate(examples, start=1):
        prompt += f"Example {idx}:\n"
        prompt += f"Question: {ex['question']}\nOptions:\n"
        for letter, opt in ex['options'].items():
            prompt += f"{letter}: {opt}\n"
        prompt += f"Final Answer: {ex['final_answer']}\n\n"
    prompt += ("Now, solve the following question and provide only the final answer in EXACT format as shown in the examples.\n\n")
    prompt += f"Question: {item.get('question','')}\nOptions:\n"
    for letter, opt in item.get("options", {}).items():
        prompt += f"{letter}: {opt}\n"
    return prompt

# 针对Problem Solving题目的prompt生成函数（Chain-of-Thought，不显示过程，仅返回答案）
def generate_cot_prompt_PS(item):
    qtype = item.get("subtype-type", "")
    question_text = item.get("question", "")
    options = item.get("options", {})
    # 修改提示，不要求展示推理过程，仅返回最终答案
    prompt = (f"Please solve the following GRE Quantitative Reasoning Problem Solving question of type '{qtype}' and provide ONLY the final answer letter (A/B/C/D/E) without any explanation.\n\n")
    prompt += f"Question: {question_text}\nOptions:\n"
    for letter, opt in options.items():
        prompt += f"{letter}: {opt}\n"
    prompt += "\nImportant: Answer with ONLY the selected letter."
    return prompt

# 初始化 g4f 客户端
client = Client()

# 加载ProblemSolving.json文件（请确保文件路径正确）
json_file = "/home/ltang24/Education/GMAT/Quant/ProblemSolving.json"
with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# 从顶层键"Allquestions"中提取题目列表
all_questions = data.get("Allquestions", [])

# 按照 "subtype-type" 对题目进行分组
groups = defaultdict(list)
for item in all_questions:
    qtype = item.get("subtype-type", "Unknown")
    groups[qtype].append(item)

# 只使用单个模型进行评测（例如：llama-3.1-8b）
model = "gemini-1.5-flash"
prompting_strategies = ["zero-shot", "five-shot", "chain-of-thought"]

# 结果存储结构：按照题型、提示策略分层存储
all_results = {}

for qtype, questions in groups.items():
    print(f"\n{'='*50}\nProcessing question type: {qtype} (Total questions: {len(questions)})\n{'='*50}")
    all_results[qtype] = {}
    # 针对每个提示策略进行评测
    for strategy in prompting_strategies:
        print(f"\n--- Testing Model: {model} with Strategy: {strategy.upper()} for type '{qtype}' ---")
        total_processed = 0
        correct_count = 0
        details = []
        # 对每个题型仅处理前50题
        for item in questions[:50]:
            qid = item.get("question_id", "")
            # 根据策略生成对应的 prompt
            if strategy == "zero-shot":
                prompt = generate_zero_shot_prompt_PS(item)
            elif strategy == "five-shot":
                prompt = generate_five_shot_prompt_PS(item)
            elif strategy == "chain-of-thought":
                prompt = generate_cot_prompt_PS(item)
            else:
                prompt = generate_zero_shot_prompt_PS(item)
            
            answer_found = False
            best_response = None
            answer_extracted = ""
            runtime = None
            try:
                start_time = time.perf_counter()
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=120,
                    temperature=0.3
                ).choices[0].message.content.strip()
                runtime = round(time.perf_counter() - start_time, 2)
                answer_extracted = extract_answer(response)
                if answer_extracted:
                    answer_found = True
                    best_response = response
            except Exception as e:
                print(f"Model {model} with strategy {strategy} error on question {qid}: {e}")
            
            if answer_found:
                total_processed += 1
                expected = str(item.get("correct_answer", "")).strip().upper()
                is_correct = (normalize_answer(answer_extracted) == normalize_answer(expected))
                if is_correct:
                    correct_count += 1
                print(f"Question {qid}: Model Answer = {answer_extracted} | Expected = {expected} | {'Correct' if is_correct else 'Incorrect'} (Runtime: {runtime}s)")
                details.append({
                    "question_id": qid,
                    "expected": expected,
                    "model_answer": answer_extracted,
                    "model_response": best_response,
                    "runtime": runtime,
                    "correct": is_correct
                })
            else:
                print(f"  ✗ No answer found for question {qid}")
        overall_accuracy = correct_count / total_processed if total_processed > 0 else 0
        result_entry = {
            "overall_accuracy": overall_accuracy,
            "total_questions_processed": total_processed,
            "details": details
        }
        all_results[qtype][strategy] = result_entry
        print(f"\nResults for Model: {model} with Strategy: {strategy.upper()} for type '{qtype}':")
        print(f"Overall Accuracy: {overall_accuracy:.2%} ({correct_count}/{total_processed})")

# 将所有结果保存到JSON文件中
output_file = "gemini-1.5-flash_result.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Comprehensive results saved to: {output_file}")
