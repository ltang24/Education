import json
import re
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    if isinstance(answer, str):
        answer = re.sub(r'^(answer\s*[12]?\s*[:：\-]?\s*)|["\'""]', '', answer, flags=re.IGNORECASE)
        return answer.strip().lower().replace(' ', '')
    # 对于非字符串（如数字、布尔值），直接转换为字符串
    return str(answer).strip().lower().replace(' ', '')

def extract_answer(response):
    """Extract answer content from model response.
       由于Integrated Reasoning题目答案可能包含多个部分，用分隔符（例如逗号）分隔，
       这里简单返回原始响应（后续在人工评估时可以比较）"""
    return response.strip()

# 针对 Integrated Reasoning 两种题型分别生成提示

def generate_zero_shot_prompt_integrated(item):
    subtype = item.get("subtype", "").lower()
    question_text = item.get("question", "")
    difficulty = item.get("difficulty", "")
    
    if subtype == "two part analysis":
        # 选项为列表，取第一个字典
        opts = item.get("options", [{}])[0]
        prompt = ("Please solve the following GRE Data Insight Two Part Analysis question and provide only the final answers "
                  "for each column in EXACT format. For example, if the columns are 'Pilot' and 'Awful', your answer should be:\n"
                  "Pilot: [answer], Awful: [answer]\n\n")
        prompt += f"Question: {question_text}\n\nOptions:\n"
        for col, choices in opts.items():
            prompt += f"{col}: {', '.join(str(c) for c in choices)}\n"
        prompt += "\nImportant: Answer with ONLY the selected answer for each column in the format shown above."
        return prompt
    elif subtype == "graphs and tables":
        # 将表格数据格式化为文本
        table = item.get("table", {})
        table_text = "Table Data:\n"
        headers = list(table.keys())
        # 假设每列为一个列表
        rows = zip(*[table[h] for h in headers])
        table_text += "\t".join(headers) + "\n"
        for row in rows:
            table_text += "\t".join(str(x) for x in row) + "\n"
        # 题中陈述
        statements = item.get("statements", [])
        prompt = ("Please read the following GRE Data Insight Graphs and Tables question. "
                  "Below is a table and several statements. Evaluate each statement and provide your answers as True or False, "
                  "in EXACT format, separated by commas. For example: True, False, True\n\n")
        prompt += table_text + "\n"
        prompt += "Statements:\n"
        for idx, st in enumerate(statements, start=1):
            prompt += f"{idx}. {st}\n"
        prompt += "\nNow, solve the following question and provide only your answers (in order) separated by commas.\n"
        prompt += f"Question: {question_text}\n"
        return prompt
    else:
        # 若未匹配，则作为普通题目处理
        prompt = f"Please solve the following question:\nQuestion: {question_text}"
        return prompt

def generate_five_shot_prompt_integrated(item):
    # 五-shot 示例（以下示例为虚构，仅供参考）
    subtype = item.get("subtype", "").lower()
    if subtype == "two part analysis":
        examples = [
            {
                "question": "Example: A coded message contains the words 'alpha' and 'bravo'. In the table below, which could be their coded versions?\nMake only one selection in each column.",
                "options": {
                    "Alpha": ["delta", "echo", "foxtrot", "golf"],
                    "Bravo": ["hotel", "india", "juliet", "kilo"]
                },
                "final_answer": {"Alpha": "delta", "Bravo": "hotel"}
            },
            {
                "question": "Example: In a puzzle, the words 'cat' and 'dog' are encoded. Which of the following selections for each column is correct?\nMake only one selection in each column.",
                "options": {
                    "Cat": ["red", "blue", "green", "yellow"],
                    "Dog": ["circle", "square", "triangle", "hexagon"]
                },
                "final_answer": {"Cat": "green", "Dog": "square"}
            },
            {
                "question": "Example: A message contains the words 'sun' and 'moon'. Their coded versions are to be selected from the options below.\nMake only one selection in each column.",
                "options": {
                    "Sun": ["bright", "dull", "warm", "cold"],
                    "Moon": ["lunar", "solar", "stellar", "galactic"]
                },
                "final_answer": {"Sun": "warm", "Moon": "lunar"}
            },
            {
                "question": "Example: A secret note includes the words 'first' and 'last'. Choose the correct coded versions from the options provided.\nMake only one selection in each column.",
                "options": {
                    "First": ["alpha", "beta", "gamma", "delta"],
                    "Last": ["omega", "sigma", "theta", "lambda"]
                },
                "final_answer": {"First": "alpha", "Last": "omega"}
            },
            {
                "question": "Example: In a cipher, the words 'east' and 'west' are encoded. Select the correct answers from the table below.\nMake only one selection in each column.",
                "options": {
                    "East": ["sunrise", "noon", "sunset", "midnight"],
                    "West": ["sunrise", "noon", "sunset", "midnight"]
                },
                "final_answer": {"East": "sunrise", "West": "sunset"}
            }
        ]
        prompt = "Below are five examples of GRE Data Insight Two Part Analysis questions:\n\n"
        for idx, ex in enumerate(examples, start=1):
            prompt += f"Example {idx}:\n"
            prompt += f"Question: {ex['question']}\nOptions:\n"
            for col, choices in ex["options"].items():
                prompt += f"{col}: {', '.join(str(c) for c in choices)}\n"
            # 输出答案格式
            answer_parts = [f"{col}: {ex['final_answer'][col]}" for col in ex["final_answer"]]
            prompt += "Final Answer: " + ", ".join(answer_parts) + "\n\n"
        # 接下来加入待测试题目
        prompt += "Now, solve the following question and provide only the final answers in EXACT format as shown above.\n\n"
        subtype_indicator = "Two Part Analysis"
        prompt += f"Question: {item.get('question','')}\nOptions:\n"
        opts = item.get("options", [{}])[0]
        for col, choices in opts.items():
            prompt += f"{col}: {', '.join(str(c) for c in choices)}\n"
        return prompt
    elif subtype == "graphs and tables":
        examples = [
            {
                "question": "Example: Evaluate the following statements based on the table provided on metal production.\n",
                "table": {
                    "Country": ["X", "Y"],
                    "Output": [100, 50]
                },
                "statements": ["X produces more than Y.", "Y produces less than half of X."],
                "final_answer": ["True", "True"]
            },
            {
                "question": "Example: Based on the provided table of sales, evaluate the statements below.\n",
                "table": {
                    "Product": ["A", "B"],
                    "Sales": [200, 150]
                },
                "statements": ["Product A outsells Product B.", "Product B sales are less than Product A sales."],
                "final_answer": ["True", "True"]
            },
            {
                "question": "Example: Read the table of student scores and evaluate the following statements.\n",
                "table": {
                    "Student": ["John", "Mary"],
                    "Score": [85, 90]
                },
                "statements": ["Mary scored higher than John.", "John did not score above 90."],
                "final_answer": ["True", "True"]
            },
            {
                "question": "Example: Analyze the following table of distances and evaluate the statements provided.\n",
                "table": {
                    "City": ["M", "N"],
                    "Distance": [300, 500]
                },
                "statements": ["City M is closer than City N.", "City N is farther than City M."],
                "final_answer": ["True", "True"]
            },
            {
                "question": "Example: Given the table on production figures, evaluate the following statements.\n",
                "table": {
                    "Factory": ["F1", "F2"],
                    "Units": [1000, 800]
                },
                "statements": ["F1 produces more than F2.", "F2 produces less than F1."],
                "final_answer": ["True", "True"]
            }
        ]
        prompt = "Below are five examples of GRE Data Insight Graphs and Tables questions:\n\n"
        for idx, ex in enumerate(examples, start=1):
            prompt += f"Example {idx}:\n"
            prompt += f"Question: {ex['question']}\n"
            # 格式化表格
            table = ex.get("table", {})
            headers = list(table.keys())
            table_text = "\t".join(headers) + "\n"
            rows = zip(*[table[h] for h in headers])
            for row in rows:
                table_text += "\t".join(str(x) for x in row) + "\n"
            prompt += "Table:\n" + table_text + "\n"
            prompt += "Statements:\n"
            for s in ex.get("statements", []):
                prompt += s + "\n"
            prompt += "Final Answer: " + ", ".join(ex["final_answer"]) + "\n\n"
        prompt += ("Now, solve the following question and provide only your answers (in order) separated by commas, "
                   "in EXACT format.\n\n")
        # 加入当前题目的表格和陈述
        table = item.get("table", {})
        if table:
            headers = list(table.keys())
            table_text = "\t".join(headers) + "\n"
            rows = zip(*[table[h] for h in headers])
            for row in rows:
                table_text += "\t".join(str(x) for x in row) + "\n"
            prompt += "Table:\n" + table_text + "\n"
        statements = item.get("statements", [])
        prompt += "Statements:\n"
        for s in statements:
            prompt += s + "\n"
        prompt += "\nQuestion: " + item.get("question", "") + "\n"
        return prompt
    else:
        # 若 subtype 未知，返回普通提示
        prompt = f"Please solve the following question:\nQuestion: {item.get('question','')}"
        return prompt

def generate_cot_prompt_integrated(item):
    # 与 zero-shot 类似，但要求展示推理过程
    subtype = item.get("subtype", "").lower()
    if subtype == "two part analysis":
        opts = item.get("options", [{}])[0]
        prompt = ("Please solve the following GRE Data Insight Two Part Analysis question using Chain of Thought reasoning. "
                  "Show your complete reasoning process and then provide only the final answers for each column in EXACT format. "
                  "For example: Pilot: [answer], Awful: [answer]\n\n")
        prompt += f"Question: {item.get('question','')}\n\nOptions:\n"
        for col, choices in opts.items():
            prompt += f"{col}: {', '.join(str(c) for c in choices)}\n"
        return prompt
    elif subtype == "graphs and tables":
        table = item.get("table", {})
        headers = list(table.keys())
        table_text = "\t".join(headers) + "\n"
        rows = zip(*[table[h] for h in headers])
        for row in rows:
            table_text += "\t".join(str(x) for x in row) + "\n"
        prompt = ("Please read the following GRE Data Insight Graphs and Tables question and use Chain of Thought reasoning "
                  "to evaluate the statements. Show your complete reasoning process and then provide your answers (True/False) "
                  "for each statement in EXACT order, separated by commas.\n\n")
        prompt += "Table:\n" + table_text + "\n"
        prompt += "Statements:\n"
        for s in item.get("statements", []):
            prompt += s + "\n"
        prompt += "\nQuestion: " + item.get("question", "") + "\n"
        return prompt
    else:
        prompt = f"Please solve the following question using Chain of Thought reasoning:\nQuestion: {item.get('question','')}"
        return prompt

# 加载 Integrated Reasoning JSON 文件，并提取 "Allquestions" 列表（只处理前50题）
json_file_ir = "/home/ltang24/Education/GMAT/DataInsighnts/IntergratedReasoning.json"
with open(json_file_ir, "r", encoding="utf-8") as f:
    data_ir = json.load(f)

if isinstance(data_ir, dict) and "Allquestions" in data_ir:
    all_questions_ir = data_ir["Allquestions"]
else:
    all_questions_ir = data_ir if isinstance(data_ir, list) else list(data_ir.values())

questions_ir = all_questions_ir[:50].copy()

# 定义模型和提示策略（与前面一致）
models = [
    "gpt-4", "gpt-4o", "llama-3.1-8b", "llama-3.1-70b",
    "llama-3.1-405b", "gemini-1.5-flash", "command-r"
]
prompting_strategies = ["zero-shot", "five-shot", "chain-of-thought"]

# 初始化 g4f 客户端
client = Client()

all_results = {}

for model in models:
    all_results[model] = {}
    for strategy in prompting_strategies:
        print(f"\n{'='*50}\nTesting Model: {model} with Strategy: {strategy.upper()} (Integrated Reasoning)\n{'='*50}")
        
        test_questions = questions_ir.copy()
        total_processed = 0
        correct_count = 0
        
        difficulty_stats = {}
        details = []
        
        for item in test_questions:
            qid = item.get("question_id", "")
            difficulty = item.get("difficulty", "moderate").lower()
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = {"total": 0, "correct": 0}
            difficulty_stats[difficulty]["total"] += 1
            
            # 根据策略和题型生成提示
            if strategy == "zero-shot":
                prompt = generate_zero_shot_prompt_integrated(item)
            elif strategy == "five-shot":
                prompt = generate_five_shot_prompt_integrated(item)
            elif strategy == "chain-of-thought":
                prompt = generate_cot_prompt_integrated(item)
            else:
                prompt = generate_zero_shot_prompt_integrated(item)
            
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
                # 对于 Two Part Analysis，期望答案为字典；对于 Graphs and Tables，期望答案为列表
                expected = None
                subtype = item.get("subtype", "").lower()
                if subtype == "two part analysis":
                    # 将各列答案连接为统一字符串，例如 "Pilot: hated, Awful: pilot"
                    expected = ", ".join([f"{k}: {v}" for k, v in item.get("correct_answer", {}).items()])
                elif subtype == "graphs and tables":
                    # 期望答案列表，连接为逗号分隔的字符串
                    expected = ", ".join(item.get("answers", []))
                else:
                    expected = str(item.get("correct_answer", ""))
                
                is_correct = (normalize_answer(answer_extracted) == normalize_answer(expected))
                if is_correct:
                    correct_count += 1
                    difficulty_stats[difficulty]["correct"] += 1
                
                print(f"Question {qid}: Model Answer = {answer_extracted} | Expected = {expected} | {'Correct' if is_correct else 'Incorrect'} (Runtime: {runtime}s)")
                
                details.append({
                    "question_id": qid,
                    "expected": expected,
                    "model_answer": answer_extracted,
                    "model_response": best_response,
                    "runtime": runtime,
                    "difficulty": difficulty,
                    "correct": is_correct
                })
            else:
                print(f"  ✗ No answer found for question {qid}")
        
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
        
        print(f"\nResults for Model: {model} with Strategy: {strategy.upper()} (Integrated Reasoning):")
        print(f"Overall Accuracy: {overall_accuracy:.2%}")
        for diff, stats in difficulty_accuracies.items():
            print(f"Difficulty '{diff}': Accuracy: {stats['accuracy']:.2%} (Correct: {stats['correct']}/{stats['total']})")

# 保存综合结果到 JSON 文件
output_file = "multi_model_results_integrated_reasoning.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Comprehensive results saved to: {output_file}")
