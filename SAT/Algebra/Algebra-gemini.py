import json
import re
import time
import os
from datetime import datetime
import sys
import argparse
from g4f.client import Client
import logging

class SATAlgebraSolver:
    def __init__(self, client=None, logger=None):
        self.client = client or Client()
        self.logger = logger or self._setup_logger()

    def _setup_logger(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('sat_algebra_solver.log')
            ]
        )
        return logging.getLogger(__name__)

    @staticmethod
    def normalize_answer(answer):
        if not answer:
            return ""
        answer = str(answer)
        answer = re.sub(
            r'^(answer\s*[12]?\s*[:：\-]?\s*)|["\']',
            '',
            answer,
            flags=re.IGNORECASE
        )
        answer = answer.strip().upper()
        if re.match(r'^[\d\./]+$', answer):
            if '/' in answer:
                try:
                    num, denom = answer.split('/')
                    return str(float(num) / float(denom))
                except:
                    return answer
            return answer
        return answer

    @staticmethod
    def extract_answer(response):
        if not response:
            return ""
        resp = response.upper()
        patterns = [
            r'FINAL ANSWER[:：\s]*([A-D]|[\d\./]+)',
            r'ANSWER[:：\s]*([A-D]|[\d\./]+)',
            r'THE ANSWER IS[:：\s]*([A-D]|[\d\./]+)',
            r'SELECTED ANSWER[:：\s]*([A-D]|[\d\./]+)',
            r'BEST OPTION[:：\s]*([A-D]|[\d\./]+)',
            r'OPTION\s*([A-D])'
        ]
        for pat in patterns:
            m = re.search(pat, resp)
            if m:
                return m.group(1)
        lines = resp.strip().split('\n')
        last = lines[-1].strip()
        m = re.match(r'^([A-D]|[\d\./]+)[.:]?$', last)
        if m:
            return m.group(1)
        m = re.search(r'\b([A-D])\b', resp)
        if m:
            return m.group(1)
        m = re.search(r'[\d\./]+', resp)
        if m:
            return m.group(0).strip()
        return ""

    def generate_prompt(self, question_data, strategy='zero-shot'):
        if strategy == 'zero-shot':
            return self._generate_zero_shot_prompt(question_data)
        elif strategy == 'five-shot':
            return self._generate_five_shot_prompt(question_data)
        else:
            return self._generate_cot_prompt(question_data)

    def _generate_zero_shot_prompt(self, question_data):
        q = question_data.get("question", "")
        num = question_data.get("number", "")
        prompt = (
            "Please solve the following SAT Algebra question and provide ONLY the letter or numeric answer.\n\n"
            f"Question {num}: {q}\n\n"
        )
        choices = question_data.get("choices") or question_data.get("options")
        if choices:
            prompt += "Options:\n"
            if isinstance(choices, dict):
                for L, C in choices.items():
                    prompt += f"{L}: {C}\n"
            elif isinstance(choices, list):
                for idx, C in enumerate(choices):
                    letter = chr(65 + idx)
                    prompt += f"{letter}: {C}\n"
        prompt += "\nImportant: Provide ONLY the letter (A, B, C, or D) or numeric answer without explanation."
        return prompt

    def _generate_five_shot_prompt(self, question_data):
        examples = [
            {
                "question": "What value of p satisfies the equation 5p + 180 = 250?",
                "choices": {"A": "14", "B": "65", "C": "86", "D": "250"},
                "answer": "A"
            },
            {
                "question": "4x + 5 = 165. What is the solution?",
                "answer": "40"
            },
            {
                "question": "John paid $165 via down payment $37 + p payments of $16. Which eqn?",
                "choices": {"A": "16p - 37 = 165", "B": "37p - 16 = 165", "C": "16p + 37 = 165", "D": "37p + 16 = 165"},
                "answer": "C"
            },
            {
                "question": "f(x)=4x+28 has x‑int (a,0) and y‑int (0,b). What is a+b?",
                "choices": {"A": "21", "B": "28", "C": "32", "D": "35"},
                "answer": "A"
            },
            {
                "question": "Line k: y=-17/3 x+5. Line j ⟂ k. Slope of j?",
                "answer": "3/17"
            }
        ]
        prompt = "I'll show you five examples of SAT Algebra questions and their answers, then ask you a new question.\n\n"
        for i, ex in enumerate(examples, 1):
            prompt += f"Example {i}:\nQuestion: {ex['question']}\n"
            if "choices" in ex:
                prompt += "Options:\n"
                for L, C in ex["choices"].items():
                    prompt += f"  {L}: {C}\n"
            prompt += f"Answer: {ex['answer']}\n\n"

        q = question_data.get("question", "")
        num = question_data.get("number", "")
        prompt += f"Now, please answer this new question:\n\nQuestion {num}: {q}\n"
        choices = question_data.get("choices") or question_data.get("options")
        if choices:
            prompt += "Options:\n"
            if isinstance(choices, dict):
                for L, C in choices.items():
                    prompt += f"  {L}: {C}\n"
            elif isinstance(choices, list):
                for idx, C in enumerate(choices):
                    letter = chr(65 + idx)
                    prompt += f"  {letter}: {C}\n"
        prompt += "\nProvide ONLY the letter (A–D) or numeric answer without explanation."
        return prompt

    def _generate_cot_prompt(self, question_data):
        q = question_data.get("question", "")
        num = question_data.get("number", "")
        prompt = (
            "Please solve the following SAT Algebra question using step-by-step reasoning.\n\n"
            f"Question {num}: {q}\n\n"
        )
        choices = question_data.get("choices") or question_data.get("options")
        if choices:
            prompt += "Options:\n"
            if isinstance(choices, dict):
                for L, C in choices.items():
                    prompt += f"{L}: {C}\n"
            elif isinstance(choices, list):
                for idx, C in enumerate(choices):
                    letter = chr(65 + idx)
                    prompt += f"{letter}: {C}\n"
        prompt += (
            "\nPlease think through this problem carefully using the following steps:\n"
            "1. Understand what the question is asking\n"
            "2. Set up the appropriate equations or approach\n"
            "3. Solve step by step\n"
            "4. Verify your answer\n"
            "5. Select the correct option or provide the numeric answer\n\n"
            "After your analysis, clearly indicate your final answer with 'Final Answer: [letter or number]'"
        )
        return prompt

    def solve_question(self, question, model_name='gpt-4', strategy='zero-shot',
                       timeout=120, temperature=0.3):
        start = time.time()
        try:
            prompt = self.generate_prompt(question, strategy)
            resp = self.client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
                temperature=temperature
            )
            response = resp.choices[0].message.content.strip()
            duration = round(time.time() - start, 2)

            model_ans = self.extract_answer(response)
            norm_model = self.normalize_answer(model_ans)
            raw = question.get("correct_answer", "")
            norm_correct = self.normalize_answer(str(raw).strip().upper())
            is_corr = (norm_model == norm_correct)

            return {
                "question_number": question.get("number", ""),
                "skill": question.get("skill", ""),
                "difficulty": question.get("question_difficulty", "Medium"),
                "correct_answer": question.get("correct_answer", ""),
                "model_answer": model_ans,
                "normalized_model_answer": norm_model,
                "normalized_correct_answer": norm_correct,
                "is_correct": is_corr,
                "runtime": duration
            }
        except Exception as e:
            self.logger.error(f"Error solving question: {e}")
            return {
                "question_number": question.get("number", ""),
                "skill": question.get("skill", ""),
                "difficulty": question.get("question_difficulty", "Medium"),
                "correct_answer": question.get("correct_answer", ""),
                "model_answer": None,
                "is_correct": False,
                "runtime": 0.0
            }

def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM performance on SAT Algebra questions")
    parser.add_argument("--input", default="Algebra.json", help="Path to input JSON file")
    parser.add_argument("--output", default="results", help="Output directory for results")
    parser.add_argument("--models", nargs="+", default=["gemini-1.5-flash"], help="Models to evaluate")
    parser.add_argument(
        "--strategies", nargs="+", default=["zero-shot", "five-shot", "chain-of-thought"],
        help="Prompting strategies"
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of questions")
    parser.add_argument("--timeout", type=int, default=120, help="Response timeout (s)")
    parser.add_argument("--temp", type=float, default=0.3, help="Model temperature")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    solver = SATAlgebraSolver()
    solver.logger.info(f"Loading questions from {args.input}")
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            questions = json.load(f)
        if args.limit:
            questions = questions[:args.limit]
        solver.logger.info(f"Loaded {len(questions)} questions")
    except Exception as e:
        solver.logger.error(f"Error loading questions: {e}")
        return

    all_results = {}
    for model in args.models:
        all_results[model] = {}
        for strat in args.strategies:
            solver.logger.info(f"Testing model: {model} with strategy: {strat}")
            stats = {"total": 0, "correct": 0, "by_difficulty": {}, "details": []}
            diff_counts = {}

            for q in questions:
                res = solver.solve_question(
                    q,
                    model_name=model,
                    strategy=strat,
                    timeout=args.timeout,
                    temperature=args.temp
                )
                stats["total"] += 1
                stats["details"].append(res)

                # Per-question terminal output
                mark = "✓" if res["is_correct"] else "✗"
                print(
                    f"Question {res['question_number']} "
                    f"(Skill: {res['skill']}, Difficulty: {res['difficulty']}):"
                )
                print(
                    f"  Model answer: {res['model_answer']}, "
                    f"Correct answer: {res['correct_answer']}"
                )
                print(
                    f"  {mark} "
                    f"{'Correct' if res['is_correct'] else 'Incorrect'} "
                    f"(Runtime: {res['runtime']}s)\n"
                )

                # Update stats
                if res["is_correct"]:
                    stats["correct"] += 1
                d = res["difficulty"]
                diff_counts.setdefault(d, {"total": 0, "correct": 0})
                diff_counts[d]["total"] += 1
                if res["is_correct"]:
                    diff_counts[d]["correct"] += 1

            # Summary
            overall_acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0
            print(f"Summary for {model} with {strat}:")
            print(f"Overall Accuracy: {overall_acc:.2%} ({stats['correct']}/{stats['total']})\n")
            print("  By Difficulty:")
            for d, cnt in diff_counts.items():
                acc = cnt["correct"] / cnt["total"] if cnt["total"] > 0 else 0.0
                print(f"    {d}: {acc:.2%} ({cnt['correct']}/{cnt['total']})")
            print("\n" + "="*50 + "\n")

            stats["accuracy"] = overall_acc
            stats["by_difficulty"] = {
                d: {
                    "total": cnt["total"],
                    "correct": cnt["correct"],
                    "accuracy": cnt["correct"] / cnt["total"] if cnt["total"] > 0 else 0
                }
                for d, cnt in diff_counts.items()
            }
            all_results[model][strat] = stats

    # Save full results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(args.output, f"algebra_results_{timestamp}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    solver.logger.info(f"All results saved to {out_file}")

if __name__ == "__main__":
    main()
