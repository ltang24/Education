import os
import re
import json
import time
from g4f.client import Client
from PIL import Image
import base64
import io

def encode_image_to_base64(image_path):
    """Encode an image to base64 string format"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def normalize_answer(answer):
    """Normalize answers for consistent comparison"""
    # Remove spaces and convert to lowercase
    return re.sub(r'\s', '', answer).lower()

def extract_expected_answer(answer_text):
    """Extract the actual answer from formats like '8. C' or 'C'"""
    # Check if the answer is in the format "number. letter"
    match = re.match(r'^\d+\.\s*([A-E,\s]+)$', answer_text)
    if match:
        return match.group(1).strip()
    return answer_text.strip()

def extract_answer(response, question_type):
    """Extract answer based on question type from model response"""
    if question_type == "Compare two quantities":
        # Look for A, B, or C (equal) or D (cannot be determined)
        pattern = r'(?:answer|choice|option|quantity)(?:is|:|\s)\s*([A-D])\.?'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        # Look for keywords
        if re.search(r'\bquantity\s*a\s*(?:is)?\s*greater', response, re.IGNORECASE):
            return "A"
        if re.search(r'\bquantity\s*b\s*(?:is)?\s*greater', response, re.IGNORECASE):
            return "B"
        if re.search(r'\bequal\b|\bsame\b|\bidentical\b', response, re.IGNORECASE):
            return "C"
        if re.search(r'\bcannot\s*(?:be)?\s*determined\b|\binsufficient\b', response, re.IGNORECASE):
            return "D"
    
    elif question_type == "Single answer":
        # Look for A, B, C, D, or E
        pattern = r'(?:answer|choice|option)(?:is|:|\s)\s*([A-E])\.?'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        # Try to find standalone letter
        standalone = re.search(r'\b([A-E])\b', response, re.IGNORECASE)
        if standalone:
            return standalone.group(1).upper()
    
    elif question_type == "Multiple answers":
        # Look for multiple options like "A, C, E" or "A and C"
        pattern = r'(?:answers|choices|options)(?:are|is|:|\s)\s*([A-E](?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E](?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E]?(?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E]?(?:\s*,\s*|\s+and\s+|\s+&\s+)[A-E]?)'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            answer_text = match.group(1)
            options = re.findall(r'[A-E]', answer_text, re.IGNORECASE)
            return ",".join([opt.upper() for opt in options])
        
        # Fallback: just extract all A-E options mentioned
        all_options = re.findall(r'\b([A-E])\b', response, re.IGNORECASE)
        if all_options:
            unique_options = []
            for opt in all_options:
                if opt.upper() not in unique_options:
                    unique_options.append(opt.upper())
            return ",".join(unique_options)
    
    elif question_type == "Enter exact number":
        # Look for a number in the response
        number_pattern = r'(?:answer|result|value)(?:is|:|\s)\s*(-?\d+\.?\d*)'
        match = re.search(number_pattern, response, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Try to find standalone number
        standalone = re.search(r'\b(-?\d+\.?\d*)\b', response)
        if standalone:
            return standalone.group(1)
    
    elif "Graphs" in question_type or "tables" in question_type or "charts" in question_type:
        # Same as Single answer for now
        pattern = r'(?:answer|choice|option)(?:is|:|\s)\s*([A-E])\.?'
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        # Try to find standalone letter
        standalone = re.search(r'\b([A-E])\b', response, re.IGNORECASE)
        if standalone:
            return standalone.group(1).upper()
    
    # If no answer found, return empty string
    return ""

def classify_question_type(response):
    """Classify the question type based on the model's response"""
    # Check for comparison between quantities
    if re.search(r'quantity\s*a|quantity\s*b|quantit(?:y|ies)\s*(?:is|are)\s*(?:greater|equal|less)|compar(?:e|ing)\s*(?:the)?\s*(?:two)?\s*quantit(?:y|ies)', response, re.IGNORECASE):
        return "Compare two quantities"
    
    # Check for multiple answers
    if re.search(r'(?:select|choose|pick)\s*(?:all|every|each)\s*(?:that|which|option)', response, re.IGNORECASE) or \
       re.search(r'(?:multiple|several)\s*(?:answers|options|choices)', response, re.IGNORECASE):
        return "Multiple answers"
    
    # Check for exact number
    if re.search(r'(?:enter|type|write|give)\s*(?:an?)?\s*(?:exact|precise|specific)?\s*(?:number|value|answer)', response, re.IGNORECASE) or \
       re.search(r'(?:numerical|numeric)\s*(?:answer|value|response)', response, re.IGNORECASE):
        return "Enter exact number"
    
    # Check for graphs, tables, charts
    if re.search(r'(?:graph|table|chart|diagram|figure)', response, re.IGNORECASE):
        return "Graphs, tables, charts"
    
    # Default to single answer
    return "Single answer"

# Set up the directory and answer file
image_dir = "/home/ltang24/Education/GRE Math Medium"
answer_file = "/home/ltang24/Education/GRE Math Medium.txt"

# Load answers from the text file
with open(answer_file, "r") as f:
    answers = f.read().strip().split("\n")

# Ensure we have 50 answers
answers = answers[:50]

# Define models
main_model = "gpt-4o"  # Model with vision capabilities
backup_models = ["gpt-4-vision-preview", "claude-3-opus-20240229"]  # Other vision models

# Initialize client
client = Client()

print(f"Main model: {main_model}")
print(f"Backup models: {', '.join(backup_models)}")
print(f"Processing {len(answers)} GRE Math questions from images...")
print("-" * 100)

results = {
    "total_questions": len(answers),
    "correct_count": 0,
    "accuracy": 0,
    "questions": []
}

# Process each question
for i in range(1, len(answers) + 1):
    question_number = i
    image_path = os.path.join(image_dir, f"{i}.png")
    raw_expected_answer = answers[i-1].strip()
    
    # Clean the expected answer by removing question number if present
    expected_answer = extract_expected_answer(raw_expected_answer)
    
    print(f"Processing question {question_number}...")
    print(f"  Raw expected answer: {raw_expected_answer}")
    print(f"  Cleaned expected answer: {expected_answer}")
    
    # Check if image exists
    if not os.path.exists(image_path):
        print(f"  Image not found: {image_path}")
        continue
    
    # Encode the image
    try:
        base64_image = encode_image_to_base64(image_path)
    except Exception as e:
        print(f"  Error encoding image: {e}")
        continue
    
    # First, determine the question type
    classification_prompt = [
        {
            "role": "user", 
            "content": [
                {"type": "text", "text": "Please examine this GRE math question and classify it into one of these categories: 'Compare two quantities', 'Single answer', 'Multiple answers', 'Enter exact number', or 'Graphs, tables, charts'. Just tell me the category name and don't solve the problem yet."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]
    
    try:
        classification_response = client.chat.completions.create(
            model=main_model,
            messages=classification_prompt,
            timeout=60
        ).choices[0].message.content.strip()
        
        question_type = classify_question_type(classification_response)
        print(f"  Classified as: {question_type}")
        
    except Exception as e:
        print(f"  Error classifying question: {e}")
        question_type = "Single answer"  # Default if classification fails
    
    # Now solve the question
    solving_prompt = [
        {
            "role": "user", 
            "content": [
                {"type": "text", "text": f"This is a GRE math question of type '{question_type}'. Please solve it step by step and give your final answer in the format 'Answer: X' where X is the correct option letter, numbers, or expression."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
            ]
        }
    ]
    
    is_correct = False
    models_tried = []
    best_answer = ""
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
                messages=solving_prompt,
                timeout=120
            ).choices[0].message.content.strip()
            
            # Extract answer
            answer = extract_answer(response, question_type)
            
            if answer:
                # For multiple answers, we need to compare sets of answers
                if question_type == "Multiple answers":
                    answer_set = set(answer.split(","))
                    expected_set = set(expected_answer.split(","))
                    current_is_correct = answer_set == expected_set
                else:
                    current_is_correct = normalize_answer(answer) == normalize_answer(expected_answer)
                
                if current_is_correct:
                    is_correct = True
                    best_answer = answer
                    best_response = response
                    best_model = model
                    runtime = time.perf_counter() - start_time
                    break
                elif not best_answer:
                    # If we haven't found any answers yet, store this as the best so far
                    best_answer = answer
                    best_response = response
                    best_model = model
            
        except Exception as e:
            print(f"  Error with {model} on question {question_number}: {e}")
        
        runtime = time.perf_counter() - start_time
    
    if is_correct:
        results["correct_count"] += 1
    
    # Record question details
    question_result = {
        "question_number": question_number,
        "question_type": question_type,
        "expected": expected_answer,  # Store the cleaned expected answer
        "raw_expected": raw_expected_answer,  # Store the original expected answer too
        "models_tried": models_tried,
        "model_used": best_model,
        "model_answer": best_answer,
        "model_response": best_response,
        "runtime": round(runtime, 2),
        "correct": is_correct,
        "image_path": image_path
    }
    
    results["questions"].append(question_result)
    
    # Calculate running accuracy
    current_accuracy = results["correct_count"] / len(results["questions"])
    print(f"  Answer: {best_answer}, Expected: {expected_answer}, Correct: {is_correct}")
    print(f"  Current accuracy: {current_accuracy:.2%}")

# Calculate final accuracy
final_accuracy = results["correct_count"] / results["total_questions"] if results["total_questions"] > 0 else 0
results["accuracy"] = final_accuracy

print(f"Overall Accuracy: {final_accuracy:.2%}")
print(f"Correct answers: {results['correct_count']}/{results['total_questions']}")
print("-" * 100)

# Save results
output_file = "GRE_Math_Medium_results.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=4)

print(f"Testing completed. Results saved to: {output_file}")