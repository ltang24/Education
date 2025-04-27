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

def extract_answer(response: str) -> str:
    """Extract the answer letter (A-D) from the model's response."""
    if not response:
        return ""
    
    response_upper = response.upper()
    
    # Look for explicit answer patterns
    if any(kw in response_upper for kw in ["ANSWER: A", "ANSWER:A", "ANSWER IS A", "FINAL ANSWER: A"]):
        return "A"
    if any(kw in response_upper for kw in ["ANSWER: B", "ANSWER:B", "ANSWER IS B", "FINAL ANSWER: B"]):
        return "B"
    if any(kw in response_upper for kw in ["ANSWER: C", "ANSWER:C", "ANSWER IS C", "FINAL ANSWER: C"]):
        return "C"
    if any(kw in response_upper for kw in ["ANSWER: D", "ANSWER:D", "ANSWER IS D", "FINAL ANSWER: D"]):
        return "D"
    
    # Look for last line or standalone letter
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
    
    # Last resort: any standalone A/B/C/D
    standalone_match = re.search(r'\b([A-D])\b', response_upper)
    if standalone_match:
        return standalone_match.group(1)
    
    # Ultimate fallback: any A/B/C/D character
    any_letter_match = re.search(r'[A-D]', response_upper)
    if any_letter_match:
        return any_letter_match.group(0)
    
    return ""

def is_correct_answer(model_answer: str, correct_answer: str) -> bool:
    """Check if the model's answer is correct."""
    if isinstance(correct_answer, list):
        # Handle multiple correct answers
        return model_answer.upper() in [ans.upper() for ans in correct_answer]
    return model_answer.upper() == correct_answer.upper()

def get_correct_answer(question: dict) -> str:
    """Extract the correct answer from the question data."""
    correct_answer = question.get("correct_answer", "")
    
    # Handle different formats
    if isinstance(correct_answer, list):
        return correct_answer
    
    # Clean up the answer if needed
    if correct_answer and correct_answer.upper() in ["A", "B", "C", "D"]:
        return correct_answer.upper()
    
    return correct_answer

def format_options(options):
    """Format options for the prompt based on different possible structures."""
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
    """Generate a simple direct prompt for the SAT Advanced Math question."""
    prompt = "Please solve the following SAT Advanced Math question. Provide ONLY the letter of your answer (A, B, C, or D).\n\n"
    
    # Add question text
    prompt += f"Question: {question['question']}\n\n"
    
    # Add options
    prompt += "Options:\n"
    prompt += format_options(question['options'])
    
    # Add instruction
    prompt += "\nProvide your answer as a single letter (A, B, C, or D)."
    
    return prompt

def generate_five_shot_prompt(question: dict, examples: list) -> str:
    """Generate a prompt with five examples followed by the actual question."""
    prompt = "I'll show you five examples of SAT Advanced Math questions and their answers, then ask you a new question.\n\n"
    
    # Add examples
    for i, example in enumerate(examples, 1):
        prompt += f"Example {i}:\n"
        prompt += f"Question: {example['question']}\n"
        prompt += "Options:\n"
        prompt += format_options(example['options'])
        prompt += f"Answer: {get_correct_answer(example)}\n\n"
    
    # Add the actual question
    prompt += "Now, please solve this new question:\n\n"
    prompt += f"Question: {question['question']}\n\n"
    
    # Add options
    prompt += "Options:\n"
    prompt += format_options(question['options'])
    
    # Add instruction
    prompt += "\nProvide your answer as a single letter (A, B, C, or D)."
    
    return prompt

def generate_cot_prompt(question: dict) -> str:
    """Generate a prompt that encourages step-by-step reasoning."""
    prompt = "Please solve the following SAT Advanced Math question using step-by-step reasoning.\n\n"
    
    # Add question text
    prompt += f"Question: {question['question']}\n\n"
    
    # Add options
    prompt += "Options:\n"
    prompt += format_options(question['options'])
    
    # Add reasoning instructions
    prompt += "\nPlease think through your solution step by step:\n"
    prompt += "1. Understand what the question is asking\n"
    prompt += "2. Set up the mathematical approach to solve it\n"
    prompt += "3. Work through the calculations carefully\n"
    prompt += "4. Check your work and verify the answer\n\n"
    prompt += "After your analysis, clearly state your final answer as: Final Answer: [letter]"
    
    return prompt

def flatten_json_data(data):
    """Recursively flatten potentially nested JSON data."""
    flattened = []
    
    if isinstance(data, list):
        for item in data:
            if isinstance(item, list):
                flattened.extend(flatten_json_data(item))
            elif isinstance(item, dict) and "question" in item:
                flattened.append(item)
            elif isinstance(item, dict) and "number" in item:
                flattened.append(item)
    elif isinstance(data, dict) and ("question" in data or "number" in data):
        flattened.append(data)
        
    return flattened

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate LLM on SAT Advanced Math questions"
    )
    parser.add_argument(
        "--input",
        default="/home/ltang24/Education/SAT/Advance_Math /Advanced_maths.json",
        help="Path to input JSON file with questions"
    )
    parser.add_argument(
        "--output", default="results_sat_advanced_math",
        help="Output directory for results"
    )
    parser.add_argument(
        "--models", nargs="+", default=["gpt-4o"],
        help="List of models to evaluate"
    )
    parser.add_argument(
        "--strategies", nargs="+",
        default=["zero-shot", "five-shot", "chain-of-thought"],
        help="List of prompting strategies to use"
    )
    parser.add_argument(
        "--questions_per_skill", type=int, default=10,
        help="Number of questions to test per skill"
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
            
        print(f"Loaded raw data with {len(raw_data)} top-level items")
        
        # Flatten the structure
        questions = flatten_json_data(raw_data)
        print(f"Flattened to {len(questions)} questions")
            
    except Exception as e:
        print(f"Error loading questions: {e}")
        return

    # Group questions by skill
    questions_by_skill = {}
    for q in questions:
        # Ensure this is a valid question
        if not isinstance(q, dict) or "question" not in q:
            continue
            
        skill = q.get("skill", "Unknown")
        if skill not in questions_by_skill:
            questions_by_skill[skill] = []
        questions_by_skill[skill].append(q)
    
    print(f"Found {len(questions_by_skill)} different skills:")
    for skill, qs in questions_by_skill.items():
        print(f"  - {skill}: {len(qs)} questions")
        
        # Sample questions if needed
        if len(qs) > args.questions_per_skill:
            questions_by_skill[skill] = random.sample(qs, args.questions_per_skill)
            print(f"    Sampled {args.questions_per_skill} questions for testing")

    # Store all results
    all_results = {}

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
                "by_skill": {s: {"total": 0, "correct": 0, "by_difficulty": {}} for s in questions_by_skill},
                "by_difficulty": {},
                "details": []
            }

            # Process each skill type
            for skill, qs in questions_by_skill.items():
                print(f"Testing skill: {skill}\n")
                
                # Get examples for five-shot prompting
                examples = []
                if strat == "five-shot":
                    # Get examples from all skills to ensure diversity
                    for s, skill_qs in questions_by_skill.items():
                        if s != skill and skill_qs:  # Don't use questions from the same skill
                            examples.extend(random.sample(skill_qs, min(2, len(skill_qs))))
                    
                    # If we don't have enough examples, add some from the same skill
                    if len(examples) < 5 and len(qs) > 5:
                        unused = [q for q in qs if q not in examples]
                        examples.extend(random.sample(unused, min(5 - len(examples), len(unused))))
                    
                    # Ensure we have exactly 5 examples
                    examples = examples[:5]
                    
                    if len(examples) < 5:
                        print(f"Warning: Only have {len(examples)} examples for five-shot prompting")
                
                # Process each question for this skill
                for q in qs:
                    # Extract question data
                    num = q.get("number", 0)
                    diff = q.get("difficulty", "Medium")
                    correct = get_correct_answer(q)
                    
                    # Initialize counters if needed
                    if diff not in stats["by_difficulty"]:
                        stats["by_difficulty"][diff] = {"total": 0, "correct": 0}
                    if diff not in stats["by_skill"][skill]["by_difficulty"]:
                        stats["by_skill"][skill]["by_difficulty"][diff] = {"total": 0, "correct": 0}
                    
                    # Update totals
                    stats["total"] += 1
                    stats["by_skill"][skill]["total"] += 1
                    stats["by_difficulty"][diff]["total"] += 1
                    stats["by_skill"][skill]["by_difficulty"][diff]["total"] += 1

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
                            "skill": skill,
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
                    
                    correct_display = correct if isinstance(correct, str) else ", ".join(correct)
                    
                    print(f"Q{num} ({skill}, {diff}): {q['question'][:50]}...")
                    print(f"  Model answer: {ans}, Correct answer: {correct_display}")
                    print(f"  {'✓ Correct' if is_correct else '✗ Incorrect'} (Runtime: {rt}s)\n")

                    # Update statistics
                    if is_correct:
                        stats["correct"] += 1
                        stats["by_skill"][skill]["correct"] += 1
                        stats["by_difficulty"][diff]["correct"] += 1
                        stats["by_skill"][skill]["by_difficulty"][diff]["correct"] += 1

                    # Store result details
                    stats["details"].append({
                        "number": num,
                        "skill": skill,
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
            
            # Calculate accuracy by skill and difficulty
            for s, data in stats["by_skill"].items():
                t = data["total"]; c = data["correct"]
                a = c/t if t else 0
                data["accuracy"] = a
                
                for d, dd in data["by_difficulty"].items():
                    tt = dd["total"]; cc = dd["correct"]
                    aa = cc/tt if tt else 0
                    dd["accuracy"] = aa
            
            # Calculate overall accuracy by difficulty
            for d, data in stats["by_difficulty"].items():
                t = data["total"]; c = data["correct"]
                a = c/t if t else 0
                data["accuracy"] = a

            # Generate summary text
            lines = []
            lines.append(f"{model_name} with {strat} strategy summary:")
            lines.append(f"Overall accuracy: {accuracy:.2%} ({correct}/{total})\n")
            
            for s, data in sorted(stats["by_skill"].items()):
                t = data["total"]; c = data["correct"]
                a = data["accuracy"]
                lines.append(f"  {s} accuracy: {a:.2%} ({c}/{t})")
                
                for d, dd in sorted(data["by_difficulty"].items()):
                    tt = dd["total"]; cc = dd["correct"]
                    aa = dd["accuracy"]
                    lines.append(f"    {d} difficulty: {aa:.2%} ({cc}/{tt})")
                lines.append("")  # blank line
                
            stats["summary_text"] = "\n".join(lines)

            # Print summary
            print(stats["summary_text"])

            # Store results for this strategy
            all_results[model_name][strat] = stats

    # Save results to file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.output, f"advanced_math_results_{ts}.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"All results saved to {out_path}")

    # Generate CSV summary for easy viewing
    csv_path = os.path.join(args.output, f"advanced_math_summary_{ts}.csv")
    
    with open(csv_path, "w", encoding="utf-8") as f:
        # Write header
        f.write("Model,Strategy,Overall Accuracy")
        for skill in questions_by_skill:
            f.write(f",{skill} Accuracy")
        f.write("\n")
        
        # Write data
        for model_name in args.models:
            for strat in args.strategies:
                if model_name in all_results and strat in all_results[model_name]:
                    model_strat = all_results[model_name][strat]
                    f.write(f"{model_name},{strat},{model_strat['accuracy']:.2%}")
                    
                    for skill in questions_by_skill:
                        if skill in model_strat["by_skill"]:
                            skill_acc = model_strat["by_skill"][skill]["accuracy"]
                            f.write(f",{skill_acc:.2%}")
                        else:
                            f.write(",N/A")
                    
                    f.write("\n")
    
    print(f"CSV summary saved to {csv_path}")

if __name__ == "__main__":
    main()