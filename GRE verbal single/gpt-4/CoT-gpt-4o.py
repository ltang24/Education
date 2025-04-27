import json
import re
import time
from g4f.client import Client

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
    questions = json.load(f)

# Limit to first 50 questions
questions = questions[:50]

# 2. Define main model and backup models (using only GPT models)
main_model = "gpt-4"
backup_models = ["gpt-4o"]

# 3. Initialize g4f client
client = Client()

print(f"Main Model: {main_model}")
print(f"Backup Models: {', '.join(backup_models)}")
print(f"Number of Test Questions: {len(questions)}")
print(f"Prompting Strategy: Chain of Thought")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer").strip().upper()  # Expected answer is a letter, like "D"
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # Construct Chain of Thought prompt
    prompt = (
        "Please read the following GRE question and use Chain of Thought reasoning to select the most appropriate answer.\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    for letter in sorted(options.keys()):
        prompt += f"{letter}: {options[letter]}\n"
    
    prompt += "\nPlease think through the problem using the following steps:\n"
    prompt += "1. Understand the question: Analyze what the question is asking and what kind of answer is required\n"
    prompt += "2. Identify key information: Extract critical keywords, relationships, and information from the question\n"
    prompt += "3. Evaluate each option: Analyze the validity and relevance of each option to the question\n"
    prompt += "4. Compare best choices: Compare the most likely options and identify key differences\n"
    prompt += "5. Conclude: Clearly state your selected answer (a single letter)\n\n"
    prompt += "Finally, please clearly mark your final answer, for example:\n"
    prompt += "Final Answer: A\n\n"
    prompt += "Be sure to show your complete reasoning process, as this will help make a more accurate selection."
    
    messages = [{"role": "user", "content": prompt}]
    
    # Try main model first
    current_model = main_model
    response = ""
    is_correct = False
    models_tried = []
    
    while not is_correct and (current_model == main_model or backup_models):
        models_tried.append(current_model)  # Record the models tried
        
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=current_model,
                messages=messages,
                timeout=120,  # Increase timeout because CoT reasoning takes more time
                temperature=0.3  # Lower temperature for more rigorous reasoning
            ).choices[0].message.content.strip()
            
            # Extract the answer letter
            answer_extracted = extract_answer(response)
            
            # Check if the answer is correct
            is_correct = (answer_extracted == expected)
            
            # If unable to extract an answer, try another model
            if not answer_extracted:
                is_correct = False
                print(f"  Unable to extract answer from response, model: {current_model}")
                
        except Exception as e:
            print(f"Model {current_model} error on question {question_number}: {e}")
            answer_extracted = ""
        
        runtime = time.perf_counter() - start_time
        
        # If not correct and there are backup models, try the next model
        if not is_correct and backup_models:
            current_model = backup_models.pop(0)
            print(f"  Trying backup model: {current_model}")
        else:
            break
    
    if is_correct:
        correct_count += 1
        print(f"  ✓ Correct ({answer_extracted})")
    else:
        print(f"  ✗ Incorrect (Model: {answer_extracted}, Expected: {expected})")
    
    # Record detailed information
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

accuracy = correct_count / total if total > 0 else 0
print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct Answers: {correct_count}/{total}")
print("-" * 100)

results = {
    "strategy": "Chain of Thought",
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

# Save results
output_file = "CoT-gpt-4o.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing complete. Results saved to: {output_file}")