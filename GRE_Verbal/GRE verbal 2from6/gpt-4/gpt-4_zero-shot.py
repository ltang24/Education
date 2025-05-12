import re
import json
import time
from g4f.client import Client

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    # Remove dots and spaces
    answer = re.sub(r'[.\s]', '', answer, flags=re.IGNORECASE)
    return answer.strip().upper()

def extract_option_answers(response):
    """Extract two letter options (A-F) from the model's response"""
    # First, look for the simplest pattern: two letters with optional dots
    simple_pattern = r'([A-F])\.?\s*,?\s*([A-F])\.?'
    simple_match = re.search(simple_pattern, response, re.IGNORECASE)
    if simple_match:
        return [normalize_answer(simple_match.group(1)), normalize_answer(simple_match.group(2))]
    
    
    # Look for options written out with periods
    period_pattern = r'([A-F])\..*?([A-F])\.'
    period_match = re.search(period_pattern, response, re.IGNORECASE)
    if period_match:
        return [normalize_answer(period_match.group(1)), normalize_answer(period_match.group(2))]
    
    # Look for options at the start of lines
    line_pattern = r'(?:^|\n)([A-F])\.?.*?(?:^|\n)([A-F])\.?'
    line_match = re.search(line_pattern, response, re.IGNORECASE | re.MULTILINE)
    if line_match:
        return [normalize_answer(line_match.group(1)), normalize_answer(line_match.group(2))]
    
    # Look for options with words in between
    word_pattern = r'([A-F])(?:\.|:)?\s+\S+.*?([A-F])(?:\.|:)?\s+\S+'
    word_match = re.search(word_pattern, response, re.IGNORECASE | re.DOTALL)
    if word_match:
        return [normalize_answer(word_match.group(1)), normalize_answer(word_match.group(2))]
    
    # Look for explicit mentions of options
    explicit_pattern = r'(?:options|answers|choices).*?([A-F]).*?([A-F])'
    explicit_match = re.search(explicit_pattern, response, re.IGNORECASE | re.DOTALL)
    if explicit_match:
        return [normalize_answer(explicit_match.group(1)), normalize_answer(explicit_match.group(2))]
    
    # Last resort: just extract all letters A-F and take the first two distinct ones
    all_options = re.findall(r'\b([A-F])\b', response, re.IGNORECASE)
    unique_options = []
    for opt in all_options:
        opt_norm = normalize_answer(opt)
        if opt_norm not in unique_options:
            unique_options.append(opt_norm)
            if len(unique_options) == 2:
                return unique_options
    
    # If we couldn't find two options, return what we have or empty strings
    while len(unique_options) < 2:
        unique_options.append("")
    
    return unique_options

# 1. Load JSON file
json_file = "/home/ltang24/Education/GRE verbal 2from6/GRE_Verbal_array_of_two_options_from_6_answers.json"
with open(json_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# 2. Define main model and backup models
main_model = "gpt-4"
backup_models = ["gpt-4o", "gpt-4o-mini"]

# 3. Initialize client
client = Client()

print(f"Main model: {main_model}")
print(f"Backup models: {', '.join(backup_models)}")
print(f"Testing {len(questions)} questions")
print("-" * 100)

total = len(questions)
correct_count = 0
details = []

for i, item in enumerate(questions):
    question_number = item.get("question_number")
    content = item.get("content")
    options = item.get("options")
    expected = item.get("answer")
    
    print(f"Processing question {i+1}/{total} (Q{question_number})...")
    
    # Normalize expected answers
    if isinstance(expected, str):
        # Handle cases where the answer is a single string like "A.B"
        expected_normalized = [part.strip() for part in re.findall(r'([A-F])', expected, re.IGNORECASE)]
    else:
        # Handle cases where the answer is a list like ["A.", "B."]
        expected_normalized = [normalize_answer(e) for e in expected]
    
    # Sort expected answers to allow for different order
    expected_normalized.sort()
    
    # Construct prompt
    prompt = (
        "Please carefully read the following GRE text completion question and select the TWO correct answer options:\n\n"
        f"Question: {content}\n"
        "Options:\n"
    )
    
    # Add options
    for key, value in options.items():
        prompt += f"{key}: {value}\n"
    
    prompt += "\nIMPORTANT: Your response MUST follow this EXACT format:\n"
    prompt += "Options: X, Y\n"
    prompt += "Explanation: Your explanation here\n\n"
    prompt += "Replace X and Y with the two correct option letters (e.g., A, C).\n"
    prompt += "Make sure to clearly indicate your two chosen options at the beginning of your response."
    
    messages = [{"role": "user", "content": prompt}]
    
    # Try with main model first
    response = ""
    is_correct = False
    models_tried = []
    best_answers = ["", ""]
    best_response = ""
    best_model = ""
    runtime = 0
    
    # Try each model
    available_models = [main_model] + backup_models
    for model in available_models:
        models_tried.append(model)
        
        start_time = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=60
            ).choices[0].message.content.strip()
            
            # Extract answers
            answers = extract_option_answers(response)
            
            # Sort answers to allow for different order
            answers.sort()
            
            # Check if answers match
            if len(answers) == 2 and all(a for a in answers):
                current_is_correct = (
                    answers[0] == expected_normalized[0] and 
                    answers[1] == expected_normalized[1]
                )
                
                if current_is_correct:
                    is_correct = True
                    best_answers = answers
                    best_response = response
                    best_model = model
                    runtime = time.perf_counter() - start_time
                    break
                elif not best_answers[0] and not best_answers[1]:
                    # If we haven't found any answers yet, store these as the best so far
                    best_answers = answers
                    best_response = response
                    best_model = model
            
        except Exception as e:
            print(f"Error with {model} on Q{question_number}: {e}")
        
        runtime = time.perf_counter() - start_time
    
    if is_correct:
        correct_count += 1
    
    # Record details
    details.append({
        "question_number": question_number,
        "expected": expected_normalized,
        "models_tried": models_tried,
        "model_used": best_model,
        "model_answer": best_answers,
        "model_response": best_response,
        "runtime": round(runtime, 2),
        "correct": is_correct
    })

accuracy = correct_count / total if total > 0 else 0
print(f"Overall Accuracy: {accuracy:.2%}")
print(f"Correct answers: {correct_count}/{total}")
print("-" * 100)

results = {
    "accuracy": accuracy,
    "total_questions": total,
    "correct_count": correct_count,
    "details": details
}

# Save results
output_file = "GRE_Verbal_array_of_two_options_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")