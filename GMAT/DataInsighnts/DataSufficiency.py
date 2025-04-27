import json
import re
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?\s*)|["\'""]', '', answer, flags=re.IGNORECASE)
    return answer.strip().lower().replace(' ', '')

def extract_answer(response):
    """Extract the answer letter from the model's response"""
    response_upper = response.upper()
    
    # 尝试根据常见标记提取答案
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
    
    # 整体搜索
    match = re.search(r'\b([A-E])\b', response_upper)
    if match:
        return match.group(1)
    match = re.search(r'([A-E])', response_upper)
    if match:
        return match.group(1)
    
    return ""

# 1. 加载 JSON 文件，并提取 "Allquestions" 列表（只处理前50题）
json_file = "/home/ltang24/Education/GMAT/DataInsighnts/DataSufficiency.json"
with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

all_questions = []
if isinstance(data, dict) and "Allquestions" in data:
    all_questions = data["Allquestions"]
else:
    all_questions = data if isinstance(data, list) else list(data.values())

questions = all_questions[:50].copy()

# 2. 定义模型列表和 prompting 策略
models = [
    "gpt-4", "gpt-4o", "llama-3.1-8b", "llama-3.1-70b",
    "llama-3.1-405b", "gemini-1.5-flash", "command-r"
]
prompting_strategies = ["zero-shot", "five-shot", "chain-of-thought"]

# 3. 初始化 g4f 客户端
client = Client()

def generate_zero_shot_prompt(content, options, passage=None):
    # 对于数据充分性题目一般不包含 passage
    prompt = "Please solve the following GRE Data Sufficiency question and provide only the SINGLE BEST letter answer (A/B/C/D/E).\n\n"
    prompt += f"Question: {content}\nOptions:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    prompt += "\nImportant: Answer with ONLY the selected letter (A/B/C/D/E)."
    return prompt

def generate_five_shot_prompt(content, options, passage=None):
    # 五个示例，这里采用与之前类似的格式（示例为数据充分性题目的示例）
    examples = [
        {
            "question": "In a certain class, a teacher distributed a few candies and a few bars among the students such that each student got an equal number of candies and an equal number of bars and no candies or bars remained undistributed. How many students were there in the class?\n\n(1) The teacher distributed 180 candies and 40 bars.\n(2) The total number of items received by each student was less than 20.",
            "options": {
                "A": "Statement (1) ALONE is sufficient, but statement (2) ALONE is not sufficient to answer the question asked.",
                "B": "Statement (2) ALONE is sufficient, but statement (1) ALONE is not sufficient to answer the question asked.",
                "C": "BOTH statements (1) and (2) TOGETHER are sufficient to answer the question asked, but NEITHER statement ALONE is sufficient to answer the question asked.",
                "D": "EACH statement ALONE is sufficient to answer the question asked.",
                "E": "Statements (1) and (2) TOGETHER are NOT sufficient to answer the question asked, and additional data specific to the problem are needed."
            },
            "final_answer": "C"
        },
        {
            "question": "If no bulk purchase discount applies, what is the price of 13 oranges and 12 apples?\n\n(1) The price of 39 oranges and 36 apples is $111.\n(2) The price of 3 oranges and 2 apples is $7.",
            "options": {
                "A": "Statement (1) ALONE is sufficient, but statement (2) ALONE is not sufficient to answer the question asked.",
                "B": "Statement (2) ALONE is sufficient, but statement (1) ALONE is not sufficient to answer the question asked.",
                "C": "BOTH statements (1) and (2) TOGETHER are sufficient to answer the question asked, but NEITHER statement ALONE is sufficient to answer the question asked.",
                "D": "EACH statement ALONE is sufficient to answer the question asked.",
                "E": "Statements (1) and (2) TOGETHER are NOT sufficient to answer the question asked, and additional data specific to the problem are needed."
            },
            "final_answer": "A"
        },
        {
            "question": "What is the price of an orange?\n\n(1) The price of 3 oranges and 2 apples is $7.\n(2) The price of an orange and the price of an apple are both integers.",
            "options": {
                "A": "Statement (1) ALONE is sufficient, but statement (2) ALONE is not sufficient to answer the question asked.",
                "B": "Statement (2) ALONE is sufficient, but statement (1) ALONE is not sufficient to answer the question asked.",
                "C": "BOTH statements (1) and (2) TOGETHER are sufficient to answer the question asked, but NEITHER statement ALONE is sufficient to answer the question asked.",
                "D": "EACH statement ALONE is sufficient to answer the question asked.",
                "E": "Statements (1) and (2) TOGETHER are NOT sufficient to answer the question asked, and additional data specific to the problem are needed."
            },
            "final_answer": "C"
        },
        {
            "question": "A trader purchased three products - Product X, Product Y, and Product Z - for a sum of $500,000. Did the trader pay more than $200,000 for Product Z?\n\n(1) The sum the trader paid for Product X and Product Y combined was 3 times the sum the trader paid for Product X.\n(2) The trader paid more to purchase Product Z than to purchase Product Y.",
            "options": {
                "A": "Statement (1) ALONE is sufficient, but statement (2) ALONE is not sufficient to answer the question asked.",
                "B": "Statement (2) ALONE is sufficient, but statement (1) ALONE is not sufficient to answer the question asked.",
                "C": "BOTH statements (1) and (2) TOGETHER are sufficient to answer the question asked, but NEITHER statement ALONE is sufficient to answer the question asked.",
                "D": "EACH statement ALONE is sufficient to answer the question asked.",
                "E": "Statements (1) and (2) TOGETHER are NOT sufficient to answer the question asked, and additional data specific to the problem are needed."
            },
            "final_answer": "C"
        },
        {
            "question": "A teacher distributed pens, pencils, and erasers among the students of his class, such that all students got an equal number of pens, an equal number of pencils, and an equal number of erasers. If no pens, pencils, or erasers remained with the teacher, how many students were in the class?\n\n(1) Each student got pens, pencils, and erasers in the ratio 3:4:5, respectively.\n(2) The teacher distributed a total of 27 pens, 36 pencils, and 45 erasers.",
            "options": {
                "A": "Statement (1) ALONE is sufficient, but statement (2) ALONE is not sufficient to answer the question asked.",
                "B": "Statement (2) ALONE is sufficient, but statement (1) ALONE is not sufficient to answer the question asked.",
                "C": "BOTH statements (1) and (2) TOGETHER are sufficient to answer the question asked, but NEITHER statement ALONE is sufficient to answer the question asked.",
                "D": "EACH statement ALONE is sufficient to answer the question asked.",
                "E": "Statements (1) and (2) TOGETHER are NOT sufficient to answer the question asked, and additional data specific to the problem are needed."
            },
            "final_answer": "E"
        }
    ]
    
    prompt = "Below are five examples of GRE Data Sufficiency questions:\n\n"
    for idx, ex in enumerate(examples, start=1):
        prompt += f"Example {idx}:\n"
        prompt += f"Question: {ex['question']}\n"
        prompt += "Options:\n"
        for letter in sorted(ex['options'].keys()):
            prompt += f"{letter}: {ex['options'][letter]}\n"
        prompt += f"Final Answer: {ex['final_answer']}\n\n"
    
    prompt += "Now, solve the following question and provide only the final answer in EXACT format as follows:\n"
    prompt += "Final Answer: X\n\n"
    prompt += f"Question: {content}\n"
    prompt += "Options:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    return prompt

def generate_cot_prompt(content, options, passage=None):
    prompt = "Please read the following GRE Data Sufficiency question and use Chain of Thought reasoning to select the most appropriate answer.\n\n"
    prompt += f"Question: {content}\n"
    prompt += "Options:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    prompt += "\nPlease think through the problem using the following steps:\n"
    prompt += "1. Understand the question and the data given.\n"
    prompt += "2. Analyze the sufficiency of each statement.\n"
    prompt += "3. Compare the statements and decide if one, both, or neither are sufficient.\n"
    prompt += "4. Conclude by selecting the correct option (a single letter).\n\n"
    prompt += "Finally, please clearly mark your final answer, for example:\n"
    prompt += "Final Answer: A\n\n"
    prompt += "Show your complete reasoning process."
    return prompt

# 存储结果的字典
all_results = {}

# 对每个模型和每种 prompting 策略进行测试
for model in models:
    all_results[model] = {}
    for strategy in prompting_strategies:
        print(f"\n{'='*50}\nTesting Model: {model} with Strategy: {strategy.upper()}\n{'='*50}")
        
        test_questions = questions.copy()  # 前50题
        total_processed = 0
        correct_count = 0
        
        # 使用字典统计各难度题目情况（如 challenging, moderate, easy）
        difficulty_stats = {}
        details = []
        
        for item in test_questions:
            question_id = item.get("question_id", "")
            content = item.get("question")
            options = item.get("options")
            expected = item.get("correct_answer").strip().upper()
            difficulty = item.get("difficulty", "moderate").lower()
            
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = {"total": 0, "correct": 0}
            difficulty_stats[difficulty]["total"] += 1
            
            # 对于 Data Sufficiency 类型的题目一般没有 passage
            passage = item.get("passage", None)
            
            if strategy == "zero-shot":
                prompt = generate_zero_shot_prompt(content, options, passage)
            elif strategy == "five-shot":
                prompt = generate_five_shot_prompt(content, options, passage)
            else:  # chain-of-thought
                prompt = generate_cot_prompt(content, options, passage)
            
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
                print(f"Model {model} with strategy {strategy} error on question {question_id}: {e}")
            
            if answer_found:
                total_processed += 1
                is_correct = (answer_extracted == expected)
                if is_correct:
                    correct_count += 1
                    difficulty_stats[difficulty]["correct"] += 1
                
                print(f"Question {question_id}: Model Answer = {answer_extracted} | Expected = {expected} | {'Correct' if is_correct else 'Incorrect'} (Runtime: {runtime}s)")
                
                details.append({
                    "question_id": question_id,
                    "expected": normalize_answer(expected),
                    "model_answer": answer_extracted,
                    "model_response": best_response,
                    "runtime": runtime,
                    "difficulty": difficulty,
                    "correct": is_correct
                })
            else:
                print(f"  ✗ No answer found for question {question_id}")
        
        overall_accuracy = correct_count / total_processed if total_processed > 0 else 0
        
        difficulty_accuracies = {}
        for diff, stats in difficulty_stats.items():
            acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            difficulty_accuracies[diff] = {"accuracy": acc, "correct": stats["correct"], "total": stats["total"]}
        
        all_results[model][strategy] = {
            "overall_accuracy": overall_accuracy,
            "total_questions_processed": total_processed,
            "difficulty_accuracies": difficulty_accuracies,
            "details": details
        }
        
        print(f"\nResults for Model: {model} with Strategy: {strategy.upper()}:")
        print(f"Overall Accuracy: {overall_accuracy:.2%}")
        for diff, stats in difficulty_accuracies.items():
            print(f"Difficulty '{diff}': Accuracy: {stats['accuracy']:.2%} (Correct: {stats['correct']}/{stats['total']})")

# 保存综合结果到 JSON 文件
output_file = "multi_model_results_data_sufficiency.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Comprehensive results saved to: {output_file}")
