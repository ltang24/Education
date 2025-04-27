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
    
    # 尝试根据常见的标记提取最终答案
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

# 1. 加载 JSON 文件，并提取所有题目（每个 passage 下的题目带上 passage 内容）
json_file = "/home/ltang24/Education/GMAT/Verbal/ReadingComprehension.json"
with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

all_questions = []
# 顶层键为 "Allquestions"
if isinstance(data, dict) and "Allquestions" in data:
    for passage in data["Allquestions"]:
        passage_text = passage.get("passage", "")
        for q in passage.get("questions", []):
            q_copy = q.copy()
            q_copy["passage"] = passage_text
            all_questions.append(q_copy)
else:
    # 如果不是这种结构，则直接按之前的方式处理
    all_questions = data if isinstance(data, list) else list(data.values())

# 仅使用前50道题
questions = all_questions[:50].copy()

# 2. 定义模型列表和 prompting 策略
models = ["gpt-4o-mini"]
prompting_strategies = ["zero-shot", "five-shot", "chain-of-thought"]

# 3. 初始化 g4f 客户端
client = Client()

def generate_zero_shot_prompt(content, options, passage=None):
    if passage:
        prompt = "Please read the following passage:\n" + passage + "\n\n"
        prompt += "Now, solve the following GRE question and provide only the SINGLE BEST letter answer (A/B/C/D/E).\n\n"
    else:
        prompt = "Please solve the following GRE question and provide only the SINGLE BEST letter answer (A/B/C/D/E).\n\n"
    prompt += f"Question: {content}\nOptions:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    prompt += "\nImportant: Answer with ONLY the selected letter (A/B/C/D/E)."
    return prompt

def generate_five_shot_prompt(content, options, passage=None):
    # 五个示例（示例中未包含 passage）
    examples = [
        {
            "question": "Amid the present wave of job redundancies for skilled but unemployed youth, the publication of an encouraging report on the viability of garage startup enterprises has led the Federal government to set up an investment fund, under its Federal light-industry program, to provide capital for such enterprises. This plan has drawn opposition from various quarters; the critics claim that similar funds, also set up under the Federal light-industry program, that aim to stimulate small enterprises frequently end up harming other American social groups unconnected to these enterprises.\n\nWhich of the following best provides support for the claim made by the critics above?",
            "options": {
                "A": "Garage enterprises in Washington State now produce almost 12% of the vehicle components previously imported from South East Asia.",
                "B": "The funding of the Federal light-industry program depends on the reallocation of resources earmarked for disadvantaged groups.",
                "C": "The debate concerning the Federal light-industry program created a backlog in the Federal legislative schedule.",
                "D": "The union for Federal light-Industry workers was the prime source of the claim.",
                "E": "Programs like Federal light-industry programs have yielded great results in past."
            },
            "final_answer": "B"
        },
        {
            "question": "Recently developed tourism infrastructure, including ten-story hotels and neon-lit discos, is obscuring the moonlight, disorienting the female turtles as they seek out beaches to lay their eggs. Often the confusion leads them to assume that the hotel pools are the sea and they end up laying their eggs in the pool flowerbeds. Once the eggs hatch, the hatchlings are unable to find their way to the sea and die. The stringent building regulations that protected the turtles in the past are being flouted openly by organized criminals who either bribe or terrorize officials into turning a blind eye.\n\nWhich of the following can be inferred from the above passage?",
            "options": {
                "A": "Scarcity of turtles results in ecological imbalance of sea.",
                "B": "Chemicals in pool water are not safe for turtles.",
                "C": "Moonlight is the only source of light for turtles.",
                "D": "Turtles are guided by moonlight.",
                "E": "Organized gangs are ignoring building restrictions."
            },
            "final_answer": "D"
        },
        {
            "question": "TMC cars has been undergoing some dramatic changes. Gone is the image of a company focused solely upon the US. Now, both the products and the workforce have begun to reflect the global nature of the company. The new works team is composed of people from all over the world. All of the mechanical engineers are the product of an in-house training scheme although, as yet, none of the engineers specializing in hydraulics has won the prestigious Order of Merit bestowed by the Mechanical Engineers Union. So far, only winners of the Order of Merit have gone on to become department heads.\n\nIf it is determined that all of the information provided by the passage is true, which of the following must also be true of the works team?",
            "options": {
                "A": "All of the department heads have received the Order of Merit.",
                "B": "All of the winners of the Order of Merit have received in-house training.",
                "C": "None of the department heads who have specialized in hydraulics are the product of an in-house training scheme.",
                "D": "None of the department heads are from the US.",
                "E": "None of the non-US mechanical engineers who are the products of in-house training have the Order of Merit."
            },
            "final_answer": "C"
        },
        {
            "question": "The move to shift the fiscal obligation to provide community services away from the Federal government to the local communities is welcomed by its proponents as a step forward on the road to true democracy. They claim that by making communities responsible for funding everything from health, welfare and education to the emergency services and housing, not only will improve these services but also foster a greater sense of community. However, such a move would mean that densely-populated areas, having a greater tax base, would be better off, and sparsely-populated, rural communities would still be dependent on supplemental subsidies from Federal sources.\n\nIn the given argument, the two portions in boldface play which of the following roles?",
            "options": {
                "A": "The first is a claim that the author calls in question, and the second is a claim that goes against the first.",
                "B": "The first is a claim that the author endorses, and the second is a claim that the author calls in question.",
                "C": "The first is a counter-evidence to the second, and the second is the proponents' prediction.",
                "D": "The first is the author's claim, and the second is the proponents’ finding that puts the first questionable.",
                "E": "The first is a prediction that the author elaborates further, and the second is the objection that the argument nullifies."
            },
            "final_answer": "A"
        },
        {
            "question": "Studies reveal that a daily exercise regimen helps stroke survivors regain dexterity in their extremities. Being given an exercise routine and having a consultation with a doctor about the exercise routine have been shown to be effective mechanisms to get patients to exercise daily. From the above information, which of the following statements can be reasonably inferred?",
            "options": {
                "A": "A stroke survivor that is given a detailed exercise plan and consults her physician about the plan will regain full dexterity in her extremities.",
                "B": "If a stroke survivor is not given an exercise plan and does not consult with a doctor, she will not regain dexterity in her extremities",
                "C": "Stroke survivors who are given an exercise routine and consult with a doctor about that routine will sometimes regain dexterity in their extremities",
                "D": "Being given an exercise routine and having a consultation with a doctor about the routine is the best way to help a stroke survivor regain dexterity in their extremities",
                "E": "Only being given an exercise routine is necessary to regenerate dexterity in the extremities of seniors who have suffered a stroke."
            },
            "final_answer": "C"
        }
    ]
    
    prompt = "Below are five examples of GRE single-answer questions:\n\n"
    for idx, ex in enumerate(examples, start=1):
        prompt += f"Example {idx}:\n"
        prompt += f"Question: {ex['question']}\n"
        prompt += "Options:\n"
        for letter in sorted(ex['options'].keys()):
            prompt += f"{letter}: {ex['options'][letter]}\n"
        prompt += f"Final Answer: {ex['final_answer']}\n\n"
    
    if passage:
        prompt += "Please read the following passage:\n" + passage + "\n\n"
    prompt += "Now, solve the following question and provide only the final answer in EXACT format as follows:\n"
    prompt += "Final Answer: X\n\n"
    prompt += f"Question: {content}\n"
    prompt += "Options:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    return prompt

def generate_cot_prompt(content, options, passage=None):
    if passage:
        prompt = "Please read the following passage:\n" + passage + "\n\n"
    else:
        prompt = ""
    prompt += "Please read the following GRE question and use Chain of Thought reasoning to select the most appropriate answer.\n\n"
    prompt += f"Question: {content}\n"
    prompt += "Options:\n"
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    prompt += "\nPlease think through the problem using the following steps:\n"
    prompt += "1. Understand the question: Analyze what the question is asking.\n"
    prompt += "2. Identify key information: Extract critical keywords.\n"
    prompt += "3. Evaluate each option: Analyze the validity of each option.\n"
    prompt += "4. Compare best choices: Identify key differences.\n"
    prompt += "5. Conclude: Clearly state your selected answer (a single letter).\n\n"
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
        
        # 使用字典统计各难度的题目情况
        difficulty_stats = {}
        details = []
        
        for item in test_questions:
            question_id = item.get("question_id", "")
            content = item.get("question")
            options = item.get("options")
            expected = item.get("correct_answer").strip().upper()
            difficulty = item.get("difficulty", "moderate").lower()  # 将难度统一为小写
            
            # 更新难度统计字典
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = {"total": 0, "correct": 0}
            difficulty_stats[difficulty]["total"] += 1
            
            passage = item.get("passage", "")
            
            # 生成对应策略的 prompt，传入 passage 参数
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
                
                # 提取模型回答
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
                
                # 打印每一道题的结果
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
        
        # 构造各难度准确率的结果字典
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
output_file = "RC_GPT_4o-mini.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Comprehensive results saved to: {output_file}")
