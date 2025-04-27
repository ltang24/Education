import json
import re
import time
from collections import defaultdict
from g4f.client import Client

def normalize_answer(answer):
    """将答案转为小写、去除空格，便于比较"""
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

# 针对TOEFL阅读理解题目的提示生成函数（零样本）
def generate_zero_shot_prompt_toefl(passage, q_item):
    prompt = ("Please read the following passage carefully:\n\n" +
              passage + "\n\n" +
              "Now answer the following question by selecting the best answer letter (A/B/C/D, etc.):\n")
    prompt += "Question: " + q_item.get("Question", "") + "\n"
    prompt += "Options:\n"
    options = q_item.get("Options", {})
    for letter, text in options.items():
        prompt += f"{letter}: {text}\n"
    prompt += "\nImportant: Answer with ONLY the letter corresponding to your chosen answer."
    return prompt

# 针对TOEFL阅读理解题目的提示生成函数（五样本提示）
def generate_five_shot_prompt_toefl(passage, q_item):
    examples = [
        {
            "question": "Example: According to the passage, which statement best reflects the author's view on language evolution?",
            "options": {
                "A": "Languages are static and unchanging.",
                "B": "Grammar is an inherent, evolving system in all languages.",
                "C": "Only modern languages have complex grammar.",
                "D": "Children have little role in creating language."
            },
            "final_answer": "B"
        },
        {
            "question": "Example: In the passage, what is the primary reason for the development of creoles?",
            "options": {
                "A": "The influence of adult speakers.",
                "B": "The natural creativity of children.",
                "C": "The strict rules of the colonizers' language.",
                "D": "The absence of any grammatical structure."
            },
            "final_answer": "B"
        },
        {
            "question": "Example: What does the passage imply about the Cherokee language?",
            "options": {
                "A": "It is simpler than English.",
                "B": "It distinguishes subtle differences that English does not.",
                "C": "It is not used anymore.",
                "D": "It has no grammatical structure."
            },
            "final_answer": "B"
        },
        {
            "question": "Example: According to the passage, why are sign languages significant?",
            "options": {
                "A": "They are identical to spoken languages.",
                "B": "They develop naturally among children and have complex grammar.",
                "C": "They are learned from written texts.",
                "D": "They are less complex than spoken languages."
            },
            "final_answer": "B"
        },
        {
            "question": "Example: The passage suggests that creoles are formed primarily through:",
            "options": {
                "A": "The copying of adults' language patterns.",
                "B": "The innovative use of language by children.",
                "C": "Formal education in grammar.",
                "D": "The interference of foreign languages."
            },
            "final_answer": "B"
        }
    ]
    prompt = "Below are five examples of TOEFL reading comprehension questions:\n\n"
    for idx, ex in enumerate(examples, start=1):
        prompt += f"Example {idx}:\n"
        prompt += "Question: " + ex["question"] + "\n"
        prompt += "Options:\n"
        for letter, text in ex["options"].items():
            prompt += f"{letter}: {text}\n"
        prompt += "Final Answer: " + ex["final_answer"] + "\n\n"
    prompt += ("Now, read the following passage and answer the question by selecting the best answer letter in EXACT format.\n\n")
    prompt += "Passage:\n" + passage + "\n\n"
    prompt += "Question: " + q_item.get("Question", "") + "\n"
    prompt += "Options:\n"
    options = q_item.get("Options", {})
    for letter, text in options.items():
        prompt += f"{letter}: {text}\n"
    prompt += "\nImportant: Answer with ONLY the letter corresponding to your chosen answer."
    return prompt

# 针对TOEFL阅读理解题目的提示生成函数（Chain-of-Thought调整版）
def generate_cot_prompt_toefl(passage, q_item):
    prompt = ("Please read the following passage carefully and answer the question by providing ONLY the final answer letter (A/B/C/D, etc.) without any explanation.\n\n")
    prompt += "Passage:\n" + passage + "\n\n"
    prompt += "Question: " + q_item.get("Question", "") + "\n"
    prompt += "Options:\n"
    options = q_item.get("Options", {})
    for letter, text in options.items():
        prompt += f"{letter}: {text}\n"
    prompt += "\nImportant: Answer with ONLY the letter corresponding to your chosen answer."
    return prompt

# 初始化 g4f 客户端
client = Client()

# 加载TOFELPARA.json文件
json_file = "/home/ltang24/Education/TOFEL/TOFELPARA.json"
with open(json_file, "r", encoding="utf-8") as f:
    passages = json.load(f)

# 结果存储结构：以段落的NO和TITLE作为分组，内部按策略统计评测
all_results = {}

# 存储每种策略的整体结果
strategy_results = {
    "zero-shot": {"total_processed": 0, "correct_count": 0, "total_questions": 0, "details": []},
    "five-shot": {"total_processed": 0, "correct_count": 0, "total_questions": 0, "details": []},
    "chain-of-thought": {"total_processed": 0, "correct_count": 0, "total_questions": 0, "details": []}
}

# 最大问题数量（每种策略）
max_questions_per_strategy = 50

# 只使用单个模型进行评测
model = "llama-3.1-405b"
prompting_strategies = ["zero-shot", "five-shot", "chain-of-thought"]

# 遍历每种策略
for strategy in prompting_strategies:
    # 重置该策略的问题计数
    question_count = 0
    
    print(f"\n{'='*50}\nTesting Strategy: {strategy.upper()} (Target: {max_questions_per_strategy} questions)\n{'='*50}")
    
    # 遍历所有段落
    for passage in passages:
        # 如果已经处理了策略所需的问题数量，则跳出循环
        if question_count >= max_questions_per_strategy:
            break
            
        passage_no = passage.get("NO", "Unknown")
        title = passage.get("TITLE", "")
        paragraph_text = passage.get("PARAGRAPH", "")
        questions = passage.get("questions", [])
        
        print(f"\n--- Testing Model: {model} with Strategy: {strategy.upper()} for Passage {passage_no}: {title} ---")
        
        # 确保在all_results中创建需要的结构
        if passage_no not in all_results:
            all_results[passage_no] = {"title": title, "results": {}}
        if strategy not in all_results[passage_no]["results"]:
            all_results[passage_no]["results"][strategy] = {"overall_accuracy": 0, "questions_with_answers": 0, "total_questions": 0, "details": []}
        
        # 段落级别的结果
        total_questions_in_passage = 0  # 该段落中的问题总数
        total_processed_in_passage = 0  # 成功获取答案的问题数
        correct_count_in_passage = 0    # 正确答案数
        details_in_passage = []
        
        for idx, q_item in enumerate(questions, start=1):
            # 如果已经处理了策略所需的问题数量，则跳出循环
            if question_count >= max_questions_per_strategy:
                break
                
            question_count += 1  # 增加策略已处理问题计数
            total_questions_in_passage += 1  # 增加该段落问题计数
            strategy_results[strategy]["total_questions"] += 1  # 增加策略总问题计数
            
            if strategy == "zero-shot":
                prompt = generate_zero_shot_prompt_toefl(paragraph_text, q_item)
            elif strategy == "five-shot":
                prompt = generate_five_shot_prompt_toefl(paragraph_text, q_item)
            elif strategy == "chain-of-thought":
                prompt = generate_cot_prompt_toefl(paragraph_text, q_item)
            else:
                prompt = generate_zero_shot_prompt_toefl(paragraph_text, q_item)
            
            answer_found = False
            best_response = None
            answer_extracted = ""
            runtime = None
            qid = f"{passage_no}-{idx}"
            
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
                if answer_extracted and len(answer_extracted) == 1 and answer_extracted in "ABCDE":
                    answer_found = True
                    best_response = response
                    # 对于CoT策略，不在终端显示详细的推理过程
                    if strategy == "chain-of-thought":
                        best_response = answer_extracted  # 只保留最终答案
            except Exception as e:
                print(f"Model {model} with strategy {strategy} error on question {qid}: {e}")
            
            question_detail = {
                "question_id": qid,
                "expected": str(q_item.get("Answer", "")).strip().upper(),
                "model_answer": answer_extracted if answer_found else "No answer",
                "model_response": best_response,
                "runtime": runtime,
                "correct": False,
                "skipped": not answer_found  # 标记为跳过，不计入准确率
            }
            
            if answer_found:
                total_processed_in_passage += 1
                strategy_results[strategy]["total_processed"] += 1
                
                expected = str(q_item.get("Answer", "")).strip().upper()
                is_correct = (normalize_answer(answer_extracted) == normalize_answer(expected))
                question_detail["correct"] = is_correct
                
                if is_correct:
                    correct_count_in_passage += 1
                    strategy_results[strategy]["correct_count"] += 1
                
                print(f"Passage {passage_no} Q{idx}: Model Answer = {answer_extracted} | Expected = {expected} | {'Correct' if is_correct else 'Incorrect'} (Runtime: {runtime}s)")
            else:
                print(f"  ✗ No answer found for question {qid}")
            
            details_in_passage.append(question_detail)
            strategy_results[strategy]["details"].append(question_detail)
        
        # 计算段落级别的准确率，只考虑成功获取答案的问题
        passage_accuracy = correct_count_in_passage / total_processed_in_passage if total_processed_in_passage > 0 else 0
        
        # 保存段落级别的结果
        all_results[passage_no]["results"][strategy] = {
            "overall_accuracy": passage_accuracy,
            "questions_with_answers": total_processed_in_passage,
            "total_questions": total_questions_in_passage,
            "details": details_in_passage
        }
        
        print(f"\nResults for Model: {model} with Strategy: {strategy.upper()} for Passage {passage_no}:")
        print(f"Passage Accuracy: {passage_accuracy:.2%} ({correct_count_in_passage}/{total_processed_in_passage})")
        print(f"Response Rate: {total_processed_in_passage}/{total_questions_in_passage}")
        print(f"Progress: {question_count}/{max_questions_per_strategy} questions for this strategy")
    
    # 计算并输出策略级别的整体准确率
    strategy_accuracy = (strategy_results[strategy]["correct_count"] / 
                          strategy_results[strategy]["total_processed"] 
                          if strategy_results[strategy]["total_processed"] > 0 else 0)
    
    print(f"\n{'='*50}")
    print(f"OVERALL RESULTS FOR {strategy.upper()} STRATEGY:")
    print(f"Overall Accuracy: {strategy_accuracy:.2%} ({strategy_results[strategy]['correct_count']}/{strategy_results[strategy]['total_processed']})")
    print(f"Response Rate: {strategy_results[strategy]['total_processed']}/{strategy_results[strategy]['total_questions']}")
    print(f"{'='*50}")

# 添加整体结果到最终JSON
all_results["overall_strategy_results"] = {}
for strategy in prompting_strategies:
    accuracy = (strategy_results[strategy]["correct_count"] / 
                strategy_results[strategy]["total_processed"] 
                if strategy_results[strategy]["total_processed"] > 0 else 0)
    
    all_results["overall_strategy_results"][strategy] = {
        "overall_accuracy": accuracy,
        "questions_with_answers": strategy_results[strategy]["total_processed"],
        "total_questions": strategy_results[strategy]["total_questions"],
        "correct_answers": strategy_results[strategy]["correct_count"]
    }

# 保存所有评测结果到JSON文件
output_file = f"{model}_50questions_per_strategy.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Results saved to: {output_file}")
print(f"\nSUMMARY OF RESULTS:")
for strategy in prompting_strategies:
    accuracy = (strategy_results[strategy]["correct_count"] / 
                strategy_results[strategy]["total_processed"] 
                if strategy_results[strategy]["total_processed"] > 0 else 0)
    print(f"{strategy.upper()}: Accuracy = {accuracy:.2%} ({strategy_results[strategy]['correct_count']}/{strategy_results[strategy]['total_processed']})")