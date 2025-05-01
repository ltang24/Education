import json
import re
import time
import os
import random
import argparse
from datetime import datetime
from g4f.client import Client

# Constants
MAX_RETRIES = 3
RATE_LIMIT_KEYWORD = "限流"  # Rate limit keyword in Chinese
MAX_QUESTIONS = 20  # Total questions to analyze

def extract_answer(response: str) -> str:
    """Extract the answer letter (A-D) or numeric answer from the model's response."""
    if not response:
        return ""
    
    response_upper = response.upper()
    
    # Look for explicit answer patterns for A-D options
    if any(kw in response_upper for kw in ["ANSWER: A", "ANSWER:A", "ANSWER IS A", "FINAL ANSWER: A"]):
        return "A"
    if any(kw in response_upper for kw in ["ANSWER: B", "ANSWER:B", "ANSWER IS B", "FINAL ANSWER: B"]):
        return "B"
    if any(kw in response_upper for kw in ["ANSWER: C", "ANSWER:C", "ANSWER IS C", "FINAL ANSWER: C"]):
        return "C"
    if any(kw in response_upper for kw in ["ANSWER: D", "ANSWER:D", "ANSWER IS D", "FINAL ANSWER: D"]):
        return "D"
    
    # Look for numeric answers
    numeric_answer_patterns = [
        r"ANSWER:\s*(\d+(?:\.\d+)?)",
        r"ANSWER IS\s*(\d+(?:\.\d+)?)",
        r"THE ANSWER IS\s*(\d+(?:\.\d+)?)",
        r"FINAL ANSWER:\s*(\d+(?:\.\d+)?)"
    ]
    
    for pattern in numeric_answer_patterns:
        match = re.search(pattern, response_upper)
        if match:
            return match.group(1)
    
    # Look for last line or standalone letter/number
    lines = response_upper.strip().split('\n')
    if lines:
        last_line = lines[-1].strip()
        if last_line in ["A", "A.", "A:"]:
            return "A"
        if last_line in ["B", "B.", "B:"]:
            return "B"
        if last_line in ["C", "C.", "C:"]:
            return "C"
        if last_line in ["D", "D.", "D:"]:
            return "D"
        
        # Check if last line is just a number
        if re.match(r"^\d+(?:\.\d+)?$", last_line):
            return last_line
    
    # Look for standalone A/B/C/D
    standalone_match = re.search(r'\b([A-D])\b', response_upper)
    if standalone_match:
        return standalone_match.group(1)
    
    # Check for numeric answers in the response
    numeric_match = re.search(r'\b(\d+(?:\.\d+)?)\b', response_upper)
    if numeric_match:
        return numeric_match.group(1)
    
    # Ultimate fallback: any A/B/C/D character
    any_letter_match = re.search(r'[A-D]', response_upper)
    if any_letter_match:
        return any_letter_match.group(0)
    
    return ""

def is_correct_answer(model_answer: str, correct_answer: str) -> bool:
    """Check if the model's answer is correct."""
    if isinstance(correct_answer, list):
        # Handle multiple correct answers
        return model_answer.upper() in [str(ans).upper() for ans in correct_answer]
    
    # For numeric answers, compare the values with some tolerance
    try:
        if re.match(r"^\d+(?:\.\d+)?$", model_answer) and re.match(r"^\d+(?:\.\d+)?$", str(correct_answer)):
            return abs(float(model_answer) - float(correct_answer)) < 0.01
    except:
        pass
    
    # Default string comparison
    return model_answer.upper() == str(correct_answer).upper()

def get_correct_answer(question: dict) -> str:
    """Extract the correct answer from the question data."""
    correct_answer = question.get("correct_answer", "")
    
    # Handle different formats
    if isinstance(correct_answer, list):
        return correct_answer
    
    # Clean up the answer
    return correct_answer

def format_options(options):
    """Format options for the prompt based on different possible structures."""
    # Handle case where options are "no options" (string)
    if isinstance(options, str) and options.lower() in ["no options", "no option"]:
        return "This question requires a numeric answer."
    
    result = ""
    
    # Handle list of dictionaries with 'label' and 'text'
    if isinstance(options, list) and options and isinstance(options[0], dict) and 'label' in options[0] and 'text' in options[0]:
        for option in options:
            result += f"{option['label']}: {option['text']}\n"
        return result
    
    # Handle dictionary with A, B, C, D keys
    if isinstance(options, dict) and any(k in options for k in ['A', 'B', 'C', 'D', 'a', 'b', 'c', 'd']):
        for label in sorted(options.keys()):
            result += f"{label}: {options[label]}\n"
        return result
    
    # Return as is if we don't recognize the format
    return str(options)

def generate_zero_shot_prompt(question: dict) -> str:
    """Generate a simple direct prompt for the geometry/trigonometry question."""
    prompt = "Please solve the following geometry/trigonometry question. "
    
    # Check if there are options
    has_options = isinstance(question.get('options'), dict) or (
        isinstance(question.get('options'), str) and 
        question.get('options').lower() not in ["no options", "no option"]
    )
    
    if has_options:
        prompt += "Provide ONLY the letter of your answer (A, B, C, or D).\n\n"
    else:
        prompt += "Provide ONLY your final numeric answer.\n\n"
    
    # Add question text
    prompt += f"Question: {question['question']}\n\n"
    
    # Add options if present
    if 'options' in question and question['options']:
        options_text = format_options(question['options'])
        if options_text:
            prompt += "Options:\n"
            prompt += options_text
    
    # Add final instruction
    if has_options:
        prompt += "\nProvide your answer as a single letter (A, B, C, or D)."
    else:
        prompt += "\nProvide only your final numeric answer without any units or explanation."
    
    return prompt

def generate_five_shot_prompt(question: dict, examples: list) -> str:
    """Generate a prompt with five examples followed by the actual question."""
    prompt = "I'll show you examples of geometry/trigonometry questions and their answers, then ask you a new question.\n\n"
    
    # Add examples
    for i, example in enumerate(examples, 1):
        prompt += f"Example {i}:\n"
        prompt += f"Question: {example['question']}\n"
        
        # Add options if present
        if 'options' in example and example['options']:
            options_text = format_options(example['options'])
            if options_text:
                prompt += "Options:\n"
                prompt += options_text
        
        prompt += f"Answer: {get_correct_answer(example)}\n\n"
    
    # Check if the new question has options
    has_options = isinstance(question.get('options'), dict) or (
        isinstance(question.get('options'), str) and 
        question.get('options').lower() not in ["no options", "no option"]
    )
    
    # Add the actual question
    prompt += "Now, please solve this new question:\n\n"
    prompt += f"Question: {question['question']}\n\n"
    
    # Add options if present
    if 'options' in question and question['options']:
        options_text = format_options(question['options'])
        if options_text:
            prompt += "Options:\n"
            prompt += options_text
    
    # Add final instruction
    if has_options:
        prompt += "\nProvide your answer as a single letter (A, B, C, or D)."
    else:
        prompt += "\nProvide only your final numeric answer without any units or explanation."
    
    return prompt

def generate_cot_prompt(question: dict) -> str:
    """Generate a prompt that encourages step-by-step reasoning."""
    prompt = "Please solve the following geometry/trigonometry question using step-by-step reasoning.\n\n"
    
    # Add question text
    prompt += f"Question: {question['question']}\n\n"
    
    # Check if there are options
    has_options = isinstance(question.get('options'), dict) or (
        isinstance(question.get('options'), str) and 
        question.get('options').lower() not in ["no options", "no option"]
    )
    
    # Add options if present
    if 'options' in question and question['options']:
        options_text = format_options(question['options'])
        if options_text:
            prompt += "Options:\n"
            prompt += options_text
    
    # Add reasoning instructions
    prompt += "\nPlease think through your solution step by step:\n"
    prompt += "1. Understand what the question is asking\n"
    prompt += "2. Set up the mathematical approach to solve it\n"
    prompt += "3. Work through the calculations carefully\n"
    prompt += "4. Check your work and verify the answer\n\n"
    
    if has_options:
        prompt += "After your analysis, clearly state your final answer as: Final Answer: [letter]"
    else:
        prompt += "After your analysis, clearly state your final answer as: Final Answer: [number]"
    
    return prompt

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate LLM on Geometry and Trigonometry questions"
    )
    parser.add_argument(
        "--input",
        default="/home/ltang24/Education/SAT/Geometry/Geometry_and_Trigonometry.json",
        help="Path to input JSON file with questions"
    )
    parser.add_argument(
        "--output", default="results_geometry",
        help="Output directory for results"
    )
    parser.add_argument(
        "--models", nargs="+", default=["gpt-4o-mini"],
        help="List of models to evaluate"
    )
    parser.add_argument(
        "--strategies", nargs="+",
        default=["zero-shot", "five-shot", "chain-of-thought"],
        help="List of prompting strategies to use"
    )
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="Timeout in seconds for model responses"
    )
    parser.add_argument(
        "--temp", type=float, default=0.3,
        help="Temperature setting for model calls"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose output with full model responses"
    )
    args = parser.parse_args()

    # Create output directory if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    # Initialize client
    client = Client()

    # Load questions
    print(f"Loading questions from {args.input}")
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        print(f"Loaded raw data with {len(raw_data)} items")
        
        # Filter out questions that require images
        questions = [q for q in raw_data if "img" not in q]
        print(f"Filtered to {len(questions)} questions without images")
        
        # Limit to MAX_QUESTIONS
        if len(questions) > MAX_QUESTIONS:
            questions = random.sample(questions, MAX_QUESTIONS)
        print(f"Selected {len(questions)} questions for evaluation")
            
    except Exception as e:
        print(f"Error loading questions: {e}")
        return

    # Store all results
    all_results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Test each model and strategy
    for model_name in args.models:
        all_results[model_name] = {}
        
        for strat in args.strategies:
            print("\n" + "-"*80)
            print(f"Testing model: {model_name} with strategy: {strat}")
            print("-"*80 + "\n")

            # Initialize statistics
            stats = {
                "total": 0,
                "correct": 0,
                "by_difficulty": {},
                "details": []
            }

            # Get examples for five-shot prompting
            examples = []
            if strat == "five-shot" and len(questions) > 5:
                examples = random.sample(questions, 5)
                # Ensure we're not testing the examples
                test_questions = [q for q in questions if q not in examples]
                if len(test_questions) < len(questions) - 5:
                    # If we don't have enough test questions, select randomly
                    test_questions = random.sample(questions, len(questions) - 5)
            else:
                test_questions = questions
            
            # Process each question
            for q in test_questions:
                # Extract question data
                num = q.get("number", 0)
                diff = q.get("difficulty", "Medium")
                correct = get_correct_answer(q)
                
                # Initialize counters if needed
                if diff not in stats["by_difficulty"]:
                    stats["by_difficulty"][diff] = {"total": 0, "correct": 0}
                
                # Update totals
                stats["total"] += 1
                stats["by_difficulty"][diff]["total"] += 1

                # Generate appropriate prompt
                if strat == "zero-shot":
                    prompt = generate_zero_shot_prompt(q)
                elif strat == "five-shot":
                    prompt = generate_five_shot_prompt(q, examples)
                else:  # chain-of-thought
                    prompt = generate_cot_prompt(q)

                # Call model with retries
                resp = None
                for attempt in range(1, MAX_RETRIES+1):
                    try:
                        t0 = time.time()
                        content = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": prompt}],
                            timeout=args.timeout,
                            temperature=args.temp
                        ).choices[0].message.content.strip()
                        rt = round(time.time() - t0, 2)
                        
                        # Check for rate limiting
                        if RATE_LIMIT_KEYWORD in content:
                            print(f"  [Attempt {attempt}/{MAX_RETRIES}] Rate limit detected, waiting 120s...")
                            time.sleep(120)
                            continue
                            
                        # Print full response in verbose mode
                        if args.verbose:
                            print(f"Full response:\n{content}\n")
                            
                        resp = content
                        break
                    except Exception as e:
                        print(f"  [Attempt {attempt}/{MAX_RETRIES}] Error: {e}")
                        time.sleep(5)
                else:
                    # All retries failed
                    print(f"  Question {num} failed after multiple retries, skipping\n")
                    stats["details"].append({
                        "number": num,
                        "difficulty": diff,
                        "correct_answer": correct,
                        "model_answer": None,
                        "is_correct": False,
                        "error": "rate_limited"
                    })
                    continue

                # Extract and evaluate answer
                ans = extract_answer(resp)
                is_correct = is_correct_answer(ans, correct)
                
                # Handle different types of correct answers for display
                if isinstance(correct, (list, tuple)):
                    correct_display = ", ".join(str(c) for c in correct)
                else:
                    correct_display = str(correct)
                
                print(f"Q{num} ({diff}): {q['question'][:50]}...")
                print(f"  Model answer: {ans}, Correct answer: {correct_display}")
                print(f"  {'✓ Correct' if is_correct else '✗ Incorrect'} (Runtime: {rt}s)\n")

                # Update statistics
                if is_correct:
                    stats["correct"] += 1
                    stats["by_difficulty"][diff]["correct"] += 1

                # Store result details
                stats["details"].append({
                    "number": num,
                    "difficulty": diff,
                    "question": q['question'],
                    "correct_answer": correct,
                    "model_answer": ans,
                    "model_full_response": resp[:500] if args.verbose else "",
                    "is_correct": is_correct,
                    "runtime": rt
                })

            # Calculate accuracy metrics
            total = stats["total"]
            correct = stats["correct"]
            accuracy = correct/total if total else 0.0
            stats["accuracy"] = accuracy
            
            # Calculate overall accuracy by difficulty
            for d, data in stats["by_difficulty"].items():
                t = data["total"]; c = data["correct"]
                a = c/t if t else 0
                data["accuracy"] = a

            # Generate summary text
            lines = []
            lines.append(f"{model_name} with {strat} strategy summary:")
            lines.append(f"Overall accuracy: {accuracy:.2%} ({correct}/{total})\n")
            
            for d, data in sorted(stats["by_difficulty"].items()):
                t = data["total"]; c = data["correct"]
                a = data["accuracy"]
                lines.append(f"  {d} difficulty: {a:.2%} ({c}/{t})")
            lines.append("")  # blank line
                
            stats["summary_text"] = "\n".join(lines)

            # Print summary
            print(stats["summary_text"])

            # Store results for this strategy
            all_results[model_name][strat] = stats

    # Save results to file
    out_path = os.path.join(args.output, f"geometry_results_{timestamp}.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"All results saved to {out_path}")

    # Generate CSV summary for easy viewing
    csv_path = os.path.join(args.output, f"geometry_summary_{timestamp}.csv")
    
    with open(csv_path, "w", encoding="utf-8") as f:
        # Write header
        f.write("Model,Strategy,Overall Accuracy\n")
        
        # Write data
        for model_name in args.models:
            for strat in args.strategies:
                if model_name in all_results and strat in all_results[model_name]:
                    model_strat = all_results[model_name][strat]
                    f.write(f"{model_name},{strat},{model_strat['accuracy']:.2%}\n")
    
    print(f"CSV summary saved to {csv_path}")

if __name__ == "__main__":
    main()