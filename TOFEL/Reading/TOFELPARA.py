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
    # 先尝试用正则表达式提取 “Final Answer:” 后面的字母（假设答案仅为 A-E）
    match = re.search(r"final\s*answer\s*[:：]?\s*([A-Ea-e])", response, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip().upper()  # 直接返回答案字母大写形式
    # 如果没有匹配到，则直接返回整个响应（转换为大写，方便比较）
    return response.strip().upper()

# 针对TOEFL阅读理解题目的提示生成函数
def generate_zero_shot_prompt_toefl(passage, q_item):
    # passage: 整个段落文本
    # q_item: 一个题目对象，包含 "Question", "Options" 等
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

def generate_five_shot_prompt_toefl(passage, q_item):
    # 下面提供5个示例（示例内容为通用示例，实际使用时可调整）
    examples = [
        {
            "question": "Example: According to the passage, which statement best reflects the author’s view on language evolution?",
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
                "A": "The copying of adults’ language patterns.",
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
    return prompt

def generate_cot_prompt_toefl(passage, q_item):
    prompt = ("Please read the following passage and use a detailed Chain of Thought to answer the question. "
              "Show your reasoning and then state only the final answer letter in EXACT format.\n\n")
    prompt += "Passage:\n" + passage + "\n\n"
    prompt += "Question: " + q_item.get("Question", "") + "\n"
    prompt += "Options:\n"
    options = q_item.get("Options", {})
    for letter, text in options.items():
        prompt += f"{letter}: {text}\n"
    prompt += "\nFor example, you may conclude: Final Answer: B"
    return prompt

# 初始化 g4f 客户端
client = Client()

# 加载TOFELPARA.json文件
json_file = "/home/ltang24/Education/TOFEL/TOFELPARA.json"
with open(json_file, "r", encoding="utf-8") as f:
    passages = json.load(f)

# 结果存储结构：以段落的NO和TITLE作为分组，内部按模型和策略统计评测
all_results = {}

# 定义使用的模型和提示策略
models = [
    "gpt-4", "gpt-4o", "llama-3.1-8b", "llama-3.1-70b",
    "llama-3.1-405b", "gemini-1.5-flash", "command-r"
]
prompting_strategies = ["zero-shot", "five-shot", "chain-of-thought"]

for passage in passages:
    passage_no = passage.get("NO", "Unknown")
    title = passage.get("TITLE", "")
    paragraph_text = passage.get("PARAGRAPH", "")
    questions = passage.get("questions", [])
    
    print(f"\n{'='*50}\nProcessing Passage {passage_no}: {title}\n{'='*50}")
    all_results[passage_no] = {"title": title, "results": {}}
    # 对于每个模型和提示策略在该段落下分别评测
    for model in models:
        if model not in all_results[passage_no]["results"]:
            all_results[passage_no]["results"][model] = {}
        for strategy in prompting_strategies:
            print(f"\n--- Testing Model: {model} with Strategy: {strategy.upper()} for Passage {passage_no} ---")
            total_processed = 0
            correct_count = 0
            details = []
            for idx, q_item in enumerate(questions, start=1):
                # 根据策略生成提示
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
                    if answer_extracted:
                        answer_found = True
                        best_response = response
                except Exception as e:
                    print(f"Model {model} with strategy {strategy} error on question {qid}: {e}")
                
                if answer_found:
                    total_processed += 1
                    expected = str(q_item.get("Answer", "")).strip().upper()
                    is_correct = (normalize_answer(answer_extracted) == normalize_answer(expected))
                    if is_correct:
                        correct_count += 1
                    print(f"Passage {passage_no} Q{idx}: Model Answer = {answer_extracted} | Expected = {expected} | {'Correct' if is_correct else 'Incorrect'} (Runtime: {runtime}s)")
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
            all_results[passage_no]["results"].setdefault(model, {})[strategy] = result_entry
            print(f"\nResults for Model: {model} with Strategy: {strategy.upper()} for Passage {passage_no}:")
            print(f"Overall Accuracy: {overall_accuracy:.2%} ({correct_count}/{total_processed})")

# 保存所有评测结果到JSON文件
output_file = "multi_model_results_toefl_para.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Comprehensive results saved to: {output_file}")
