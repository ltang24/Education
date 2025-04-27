import json
import re
import time
import os
import random
import argparse
from datetime import datetime
from g4f.client import Client

# Helper function to get the answer letter from options and correct answer
def get_answer_letter(q):
    """Find the letter corresponding to the correct answer."""
    correct = q.get("correct_answer", "").strip().lower()
    if correct in ["a", "b", "c", "d"]:
        return correct.upper()
    for letter, text in q.get("options", {}).items():
        if text.strip().lower() == correct:
            return letter.upper()
    return ""

# Constants
MAX_RETRIES = 3
RATE_LIMIT_KEYWORD = "限流"  # Rate limit keyword

def extract_conventions_answer(response: str) -> str:
    """Extract the answer letter (a-d) from the model's response."""
    if not response:
        return ""
    response_lower = response.lower()

    # Look for explicit answer patterns
    if any(kw in response_lower for kw in ["answer: a", "answer:a", "answer is a"]):
        return "A"
    if any(kw in response_lower for kw in ["answer: b", "answer:b", "answer is b"]):
        return "B"
    if any(kw in response_lower for kw in ["answer: c", "answer:c", "answer is c"]):
        return "C"
    if any(kw in response_lower for kw in ["answer: d", "answer:d", "answer is d"]):
        return "D"
    
    # Look for last line
    lines = response_lower.strip().split('\n')
    if lines:
        last_line = lines[-1].strip()
        if last_line in ["a", "a.", "a:"]:
            return "A"
        if last_line in ["b", "b.", "b:"]:
            return "B"
        if last_line in ["c", "c.", "c:"]:
            return "C"
        if last_line in ["d", "d.", "d:"]:
            return "D"
    
    # Last resort: any standalone a/b/c/d
    for letter in ["a", "b", "c", "d"]:
        if letter in response_lower:
            return letter.upper()
    return ""

def generate_zero_shot_prompt(q: dict) -> str:
    """Generate a zero-shot prompt."""
    prompt = (
        "Please select the best option to fill in the blank in the following sentence. "
        "Choose the option that conforms to the conventions of Standard English. "
        "Provide ONLY the letter of your answer (A, B, C, or D).\n\n"
        f"{q['question']}\n\n"
        "Options:\n"
    )
    for letter, text in sorted(q['options'].items()):
        prompt += f"{letter}: {text}\n"
    prompt += "\nAnswer: "
    return prompt

def generate_five_shot_prompt(q: dict, skill: str, pool: list) -> str:
    """Generate a five-shot prompt."""
    examples = random.sample(pool, min(5, len(pool)))
    prompt = f"I'll show you five examples for skill {skill} and then ask you to answer a new question.\n\n"
    for i, ex in enumerate(examples, 1):
        prompt += f"Example {i}:\n"
        prompt += f"Question: {ex['question']}\nOptions:\n"
        for letter, text in ex['options'].items():
            prompt += f"{letter}: {text}\n"
        prompt += f"Answer: {get_answer_letter(ex)}\n\n"
    prompt += "Now your turn:\n\n"
    prompt += f"Question: {q['question']}\nOptions:\n"
    for letter, text in q['options'].items():
        prompt += f"{letter}: {text}\n"
    prompt += "\nProvide ONLY the letter of your answer (A, B, C, or D):"
    return prompt

def generate_cot_prompt(q: dict, skill: str) -> str:
    """Generate a chain-of-thought prompt."""
    prompt = (
        f"Solve the following {skill} problem with step-by-step reasoning.\n\n"
        f"Question: {q['question']}\n\n"
        "Options:\n"
    )
    for letter, text in q['options'].items():
        prompt += f"{letter}: {text}\n"
    prompt += (
        "\nPlease think through your reasoning in numbered steps, "
        "then provide your final answer as:\n"
        "Final Answer: [letter]"
    )
    return prompt

def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM on Standard English Conventions fill-in-the-blank questions")
    parser.add_argument("--input", default="/home/ltang24/Education/SAT/Standard_English_Conventions/Standard_English_Conventions .json", help="Input JSON file")
    parser.add_argument("--output", default="results_conventions", help="Output directory")
    parser.add_argument("--models", nargs="+", default=["gemini-1.5-flash"], help="Models to evaluate")
    parser.add_argument("--strategies", nargs="+", default=["zero-shot", "five-shot", "chain-of-thought"], help="Prompting strategies")
    parser.add_argument("--questions_per_skill", type=int, default=20, help="Questions per skill")
    parser.add_argument("--timeout", type=int, default=120, help="Model timeout")
    parser.add_argument("--temp", type=float, default=0.3, help="Model temperature")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    client = Client()

    print(f"Loading questions from {args.input}")
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            questions = json.load(f)
        print(f"Loaded {len(questions)} questions")
    except Exception as e:
        print(f"Failed to load questions: {e}")
        return

    QUESTIONS_BY_SKILL = {}
    for q in questions:
        skill = q.get("skill", "Unknown")
        QUESTIONS_BY_SKILL.setdefault(skill, []).append(q)

    for skill, qs in QUESTIONS_BY_SKILL.items():
        if len(qs) > args.questions_per_skill:
            QUESTIONS_BY_SKILL[skill] = random.sample(qs, args.questions_per_skill)
        print(f"Testing {len(QUESTIONS_BY_SKILL[skill])} questions for skill: {skill}")

    all_results = {}

    for model_name in args.models:
        all_results[model_name] = {}

        for strat in args.strategies:
            print("\n" + "-"*80)
            print(f"Testing model: {model_name} with strategy: {strat}")
            print("-"*80 + "\n")

            stats = {
                "total": 0,
                "correct": 0,
                "by_skill": {s: {"total": 0, "correct": 0, "by_difficulty": {}} for s in QUESTIONS_BY_SKILL},
                "by_difficulty": {},
                "details": []
            }

            for skill, qs in QUESTIONS_BY_SKILL.items():
                print(f"Skill: {skill}\n")
                pool = QUESTIONS_BY_SKILL[skill]

                for q in qs:
                    num = q.get("number", 0)
                    diff = q.get("difficulty", "Medium")
                    correct = q.get("correct_answer", "").strip()

                    stats["total"] += 1
                    stats["by_skill"][skill]["total"] += 1
                    stats["by_difficulty"].setdefault(diff, {"total": 0, "correct": 0})["total"] += 1
                    stats["by_skill"][skill]["by_difficulty"].setdefault(diff, {"total": 0, "correct": 0})["total"] += 1

                    if strat == "zero-shot":
                        prompt = generate_zero_shot_prompt(q)
                    elif strat == "five-shot":
                        prompt = generate_five_shot_prompt(q, skill, pool)
                    else:
                        prompt = generate_cot_prompt(q, skill)

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

                            if RATE_LIMIT_KEYWORD in content:
                                print(f"Rate limit detected, retrying after 120s...")
                                time.sleep(120)
                                continue

                            if args.verbose:
                                print(f"Response:\n{content}\n")

                            resp = content
                            break
                        except Exception as e:
                            print(f"[Attempt {attempt}/{MAX_RETRIES}] Error: {e}")
                            time.sleep(5)
                    else:
                        print(f"Question {num} failed, skipping")
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

                    ans = extract_conventions_answer(resp)
                    correct_letter = get_answer_letter(q)
                    is_correct = (ans.upper() == correct_letter)

                    print(f"Q{num} (Skill: {skill}, Difficulty: {diff}): Model={ans}, Correct={correct_letter} -> {'✓' if is_correct else '✗'} (Time: {rt}s)\n")

                    if is_correct:
                        stats["correct"] += 1
                        stats["by_skill"][skill]["correct"] += 1
                        stats["by_difficulty"][diff]["correct"] += 1
                        stats["by_skill"][skill]["by_difficulty"][diff]["correct"] += 1

                    stats["details"].append({
                        "number": num,
                        "skill": skill,
                        "difficulty": diff,
                        "correct_answer": correct,
                        "correct_letter": correct_letter,
                        "model_answer": ans,
                        "is_correct": is_correct,
                        "runtime": rt
                    })

            stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] else 0.0

            for s, d in stats["by_skill"].items():
                d["accuracy"] = d["correct"] / d["total"] if d["total"] else 0
                for diff, dd in d["by_difficulty"].items():
                    dd["accuracy"] = dd["correct"] / dd["total"] if dd["total"] else 0

            for diff, dd in stats["by_difficulty"].items():
                dd["accuracy"] = dd["correct"] / dd["total"] if dd["total"] else 0

            all_results[model_name][strat] = stats

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.output, f"conventions_results_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to {out_path}")

    csv_path = os.path.join(args.output, f"conventions_summary_{ts}.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("Model,Strategy,Overall Accuracy")
        for skill in QUESTIONS_BY_SKILL:
            f.write(f",{skill} Accuracy")
        f.write("\n")
        for model_name in args.models:
            for strat in args.strategies:
                if model_name in all_results and strat in all_results[model_name]:
                    data = all_results[model_name][strat]
                    f.write(f"{model_name},{strat},{data['accuracy']:.2%}")
                    for skill in QUESTIONS_BY_SKILL:
                        acc = data["by_skill"].get(skill, {}).get("accuracy", None)
                        f.write(f",{acc:.2%}" if acc is not None else ",N/A")
                    f.write("\n")
    print(f"CSV saved to {csv_path}")

if __name__ == "__main__":
    main()
