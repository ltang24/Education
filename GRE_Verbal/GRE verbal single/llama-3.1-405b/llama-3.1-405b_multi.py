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
    
    # Try to find the final answer after a clear marker
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
    
    # First try to find a standalone letter at the beginning of the response
    first_line = response_upper.split('\n')[0].strip()
    match = re.match(r'^([A-E])[.:]?$', first_line)
    if match:
        return match.group(1)
    
    # Then try to find any standalone letter in the first line
    match = re.search(r'\b([A-E])\b', first_line)
    if match:
        return match.group(1)
    
    # If that fails, try to find any standalone letter in the entire response
    match = re.search(r'\b([A-E])\b', response_upper)
    if match:
        return match.group(1)
    
    # Last resort: try to find any letter (even if not standalone)
    match = re.search(r'([A-E])', response_upper)
    if match:
        return match.group(1)
    
    return ""

# 1. Load JSON file
json_file = "/home/ltang24/Education/GRE verbal single/GRE_Verbal_single_answer.json"
with open(json_file, "r", encoding="utf-8") as f:
    all_questions = json.load(f)

# 2. Define models and strategies
main_models = ["llama-3.1-405b", "llama-3.1-70b", "llama-3.1-8b"]
prompting_strategies = ["zero-shot", "three-shot", "chain-of-thought"]

# 3. Initialize g4f client
client = Client()

# Detailed prompt generation functions (same as previous script)
def generate_zero_shot_prompt(content, options):
    prompt = (
        "Please solve the following GRE question and provide only the SINGLE BEST letter answer (A/B/C/D/E).\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nImportant: Answer with ONLY the selected letter (A/B/C/D/E)."
    return prompt

def generate_three_shot_prompt(content, options):
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
    
    prompt = (
        three_shot_examples +
        "Now, solve the following question and provide only the final answer in EXACT format as follows:\n"
        "Final Answer: X\n\n" +
        f"Question: {content}\n"
        "Options:\n"
    )
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    return prompt

def generate_cot_prompt(content, options):
    prompt = (
        "Please read the following GRE question and use Chain of Thought reasoning to select the most appropriate answer.\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nPlease think through the problem using the following steps:\n"
    prompt += "1. Understand the question: Analyze what the question is asking\n"
    prompt += "2. Identify key information: Extract critical keywords\n"
    prompt += "3. Evaluate each option: Analyze the validity of each option\n"
    prompt += "4. Compare best choices: Identify key differences\n"
    prompt += "5. Conclude: Clearly state your selected answer (a single letter)\n\n"
    prompt += "Finally, please clearly mark your final answer, for example:\n"
    prompt += "Final Answer: A\n\n"
    prompt += "Show your complete reasoning process."
    
    return prompt

# Prepare results storage
all_results = {}

# Process questions for each strategy
for strategy in prompting_strategies:
    print(f"\n{'='*50}\nTesting Strategy: {strategy.upper()}\n{'='*50}")
    
    # Reset questions and tracking variables
    questions = all_questions[:50].copy()
    total_processed = 0
    correct_count = 0
    details = []
    
    for item in questions:
        question_number = item.get("question_number")
        content = item.get("content")
        options = item.get("options")
        expected = item.get("answer").strip().upper()
        
        print(f"Processing question {total_processed+1} (Q{question_number})...")
        
        # Generate prompt based on strategy
        if strategy == "zero-shot":
            prompt = generate_zero_shot_prompt(content, options)
        elif strategy == "three-shot":
            prompt = generate_three_shot_prompt(content, options)
        else:  # chain-of-thought
            prompt = generate_cot_prompt(content, options)
        
        # Try models
        answer_found = False
        models_tried = []
        best_model = None
        best_response = None
        answer_extracted = ""
        
        for current_model in main_models:
            try:
                start_time = time.perf_counter()
                response = client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=120,
                    temperature=0.3
                ).choices[0].message.content.strip()
                
                # Extract answer
                answer_extracted = extract_answer(response)
                runtime = time.perf_counter() - start_time
                
                # Check if answer was extracted
                if answer_extracted:
                    answer_found = True
                    best_model = current_model
                    best_response = response
                    
                    # Check correctness
                    is_correct = (answer_extracted == expected)
                    break
                
                models_tried.append(current_model)
                
            except Exception as e:
                print(f"Model {current_model} error: {e}")
        
        # Only record and process if an answer was found
        if answer_found:
            total_processed += 1
            
            details.append({
                "question_number": question_number,
                "expected": normalize_answer(expected),
                "models_tried": models_tried,
                "model_used": best_model,
                "model_answer": answer_extracted,
                "model_response": best_response,
                "runtime": round(runtime, 2),
                "correct": is_correct
            })
            
            if is_correct:
                correct_count += 1
                print(f"  ✓ Correct ({answer_extracted})")
            else:
                print(f"  ✗ Incorrect (Model: {answer_extracted}, Expected: {expected})")
        else:
            print(f"  ✗ No answer found for question {question_number}")
        
    # Calculate accuracy based only on processed questions
    accuracy = correct_count / total_processed if total_processed > 0 else 0
    
    # Store results for this strategy
    all_results[strategy] = {
        "accuracy": accuracy,
        "correct_count": correct_count,
        "total_questions_processed": total_processed,
        "details": details
    }
    
    print(f"\n{strategy.upper()} Strategy Results:")
    print(f"Accuracy: {accuracy:.2%}")
    print(f"Correct Answers: {correct_count}/{total_processed}")

# Save comprehensive results
output_file = "GRE_Verbal_Llama_Multi_Strategy_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"\nTesting complete. Comprehensive results saved to: {output_file}")