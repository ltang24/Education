import json
import re
import time
import os
import random
import argparse
from datetime import datetime
from g4f.client import Client

# ——— 正确答案字典 ———
central_ideas_details_answers = {
    1: "A", 2: "D", 3: "C", 4: "A", 5: "D",
    6: "B", 7: "D", 8: "B", 9: "A", 10: "A",
    11: "B", 12: "D", 13: "B", 14: "B", 15: "C",
    16: "D", 17: "C", 18: "D", 19: "B", 20: "C"
}
command_of_evidence_answers = {
    21: "B", 22: "A", 23: "C", 24: "D", 25: "C",
    26: "B", 27: "B", 28: "A", 29: "D", 30: "C",
    31: "B", 32: "D", 33: "B", 34: "D", 35: "A",
    36: "D", 37: "C", 38: "C", 39: "D", 40: "C"
}
inferences_answers = {
    41: "B", 42: "D", 43: "B", 44: "A", 45: "A",
    46: "A", 47: "C", 48: "A", 49: "B", 50: "A",
    51: "A", 52: "C", 53: "C", 54: "D", 55: "B",
    56: "D", 57: "C", 58: "C", 59: "A", 60: "D"
}

def extract_answer(response):
    """从模型的回答中提取答案字母(A-D)"""
    if not response:
        return ""
    resp = response.upper()
    patterns = [
        r'FINAL ANSWER[:：\s]*([A-D])',
        r'ANSWER[:：\s]*([A-D])',
        r'THE ANSWER IS[:：\s]*([A-D])',
        r'SELECTED ANSWER[:：\s]*([A-D])',
        r'BEST OPTION[:：\s]*([A-D])',
        r'OPTION\s*([A-D])'
    ]
    for pat in patterns:
        m = re.search(pat, resp)
        if m:
            return m.group(1)
    lines = resp.strip().splitlines()
    for line in (lines[0], lines[-1], resp):
        m = re.search(r'\b([A-D])\b', line)
        if m:
            return m.group(1)
    m = re.search(r'([A-D])', resp)
    return m.group(1) if m else ""

def generate_zero_shot_prompt(q):
    skill = q.get("skill", "")
    prompt = (
        f"Please solve the following {skill or 'reading'} question "
        "(Central Ideas and Details, Command of Evidence, or Inferences) "
        "and select the single best answer (A/B/C/D).\n\n"
    )
    notes = q.get("notes", "")
    if notes:
        prompt += f"Text: {notes}\n\n"
    prompt += f"Question: {q.get('question','')}\n\nOptions:\n"
    for L, T in sorted(q.get("answer_choices", {}).items()):
        prompt += f"{L}: {T}\n"
    prompt += "\nImportant: Provide ONLY the letter of your answer (A, B, C, or D)."
    return prompt

def generate_five_shot_prompt(question_data, question_type):
    """生成一个包含5个相同类型示例的提示，然后是实际问题"""
    examples = []
    if question_type == "Central Ideas and Details":
        examples = [
            {
                "notes": "Believing that living in an impractical space can heighten awareness and even improve health, conceptual artists Madeline Gins and Shusaku Arakawa designed an apartment building in Japan to be more fanciful than functional. A kitchen counter is chest-high on one side and knee-high on the other; a ceiling has a door to nowhere. The effect is disorienting but invigorating: after four years there, filmmaker Nobu Yamaoka reported significant health benefits.",
                "question": "Which choice best states the main idea of the text?",
                "answer_choices": {
                    "A": "Although inhabiting a home surrounded by fanciful features such as those designed by Gins and Arakawa can be rejuvenating, it is unsustainable.",
                    "B": "Designing disorienting spaces like those in the Gins and Arakawa building is the most effective way to create a physically stimulating environment.",
                    "C": "As a filmmaker, Yamaoka has long supported the designs of conceptual artists such as Gins and Arakawa.",
                    "D": "Although impractical, the design of the apartment building by Gins and Arakawa may improve the well-being of the apartment building's residents."
                },
                "answer": "D"
            },
            {
                "notes": "The most recent iteration of the immersive theater experience Sleep No More, which premiered in New York City in 2011, transforms its performance space—a five-story warehouse—into a 1930s-era hotel. Audience members, who wander through the labyrinthine venue at their own pace and follow the actors as they play out simultaneous, interweaving narrative loops, confront the impossibility of experiencing the production in its entirety. The play's refusal of narrative coherence thus hinges on the sense of spatial fragmentation that the venue's immense and intricate layout generates.",
                "question": "What does the text most strongly suggest about Sleep No More's use of its performance space?",
                "answer_choices": {
                    "A": "The choice of a New York City venue likely enabled the play's creators to experiment with the use of theatrical space in a way that venues from earlier productions could not.",
                    "B": "Audience members likely find the experience of the play disappointing because they generally cannot make their way through the entire venue.",
                    "C": "The production's dependence on a particular performance environment would likely make it difficult to reproduce exactly in a different theatrical space.",
                    "D": "Audience members who navigate the space according to a recommended itinerary will likely have a better grasp of the play's narrative than audience members who depart from that itinerary."
                },
                "answer": "C"
            },
            {
                "notes": "Utah is home to Pando, a colony of about 47,000 quaking aspen trees that all share a single root system. Pando is one of the largest single organisms by mass on Earth, but ecologists are worried that its growth is declining in part because of grazing by animals. The ecologists say that strong fences could prevent deer from eating young trees and help Pando start thriving again.",
                "question": "According to the text, why are ecologists worried about Pando?",
                "answer_choices": {
                    "A": "It isn't growing at the same rate it used to.",
                    "B": "It isn't producing young trees anymore.",
                    "C": "It can't grow into new areas because it is blocked by fences.",
                    "D": "Its root system can't support many more new trees."
                },
                "answer": "A"
            },
            {
                "notes": "The following text is from Jane Austen's 1811 novel Sense and Sensibility. Elinor lives with her younger sisters and her mother, Mrs. Dashwood.\nElinor, this eldest daughter, whose advice was so effectual, possessed a strength of understanding, and coolness of judgment, which qualified her, though only nineteen, to be the counsellor of her mother, and enabled her frequently to counteract, to the advantage of them all, that eagerness of mind in Mrs. Dashwood which must generally have led to imprudence. She had an excellent heart;—her disposition was affectionate, and her feelings were strong; but she knew how to govern them: it was a knowledge which her mother had yet to learn; and which one of her sisters had resolved never to be taught.",
                "question": "According to the text, what is true about Elinor?",
                "answer_choices": {
                    "A": "Elinor often argues with her mother but fails to change her mind.",
                    "B": "Elinor can be overly sensitive with regard to family matters.",
                    "C": "Elinor thinks her mother is a bad role model.",
                    "D": "Elinor is remarkably mature for her age."
                },
                "answer": "D"
            },
            {
                "notes": "Biologists have predicted that birds' feather structures vary with habitat temperature, but this hadn't been tested in mountain environments. Ornithologist Sahas Barve studied feathers from 249 songbird species inhabiting different elevations—and thus experiencing different temperatures—in the Himalaya Mountains. He found that feathers of high-elevation species not only have a greater proportion of warming downy sections to flat and smooth sections than do feathers of low-elevation species, but high-elevation species' feathers also tend to be longer, providing a thicker layer of insulation.",
                "question": "Which choice best states the main idea of the text?",
                "answer_choices": {
                    "A": "Barve's investigation shows that some species of Himalayan songbirds have evolved feathers that better regulate body temperature than do the feathers of other species, contradicting previous predictions.",
                    "B": "Barve found an association between habitat temperature and feather structure among Himalayan songbirds, lending new support to a general prediction.",
                    "C": "Barve discovered that songbirds have adapted to their environment by growing feathers without flat and smooth sections, complicating an earlier hypothesis.",
                    "D": "The results of Barve's study suggest that the ability of birds to withstand cold temperatures is determined more strongly by feather length than feather structure, challenging an established belief."
                },
                "answer": "B"
            }
        ]
    elif question_type == "Command of Evidence":
        examples = [
            {
                "notes": "Scientists have long believed that giraffes are mostly silent and communicate only visually with one another. But biologist Angela Stöger and her team analyzed hundreds of hours of recordings of giraffes in three European zoos and found that giraffes make a very low-pitched humming sound. The researchers claim that the giraffes use these sounds to communicate when it's not possible for them to signal one another visually.",
                "question": "Which finding, if true, would most directly support Stöger and her team's claim?",
                "answer_choices": {
                    "A": "Giraffes have an excellent sense of vision and can see in color.",
                    "B": "The giraffes only produced the humming sounds at night when they couldn't see one another.",
                    "C": "Wild giraffes have never been recorded making humming sounds.",
                    "D": "Researchers observed other animals in European zoos humming."
                },
                "answer": "B"
            },
            {
                "notes": "Many archaeologists will tell you that categorizing excavated fragments of pottery by style, period, and what objects they belong to relies not only on standard criteria, but also on instinct developed over years of practice. In a recent study, however, researchers trained a deep-learning computer model on thousands of images of pottery fragments and found that it could categorize them as accurately as a team of expert archaeologists. Some archaeologists have expressed concern that they might be replaced by such computer models, but the researchers claim that outcome is highly unlikely.",
                "question": "Which finding, if true, would most directly support the researchers' claim?",
                "answer_choices": {
                    "A": "In the researchers' study, the model was able to categorize the pottery fragments much more quickly than the archaeologists could.",
                    "B": "In the researchers' study, neither the model nor the archeologists were able to accurately categorize all the pottery fragments that were presented.",
                    "C": "A survey of archaeologists showed that categorizing pottery fragments limits the amount of time they can dedicate to other important tasks that only human experts can do.",
                    "D": "A survey of archaeologists showed that few of them received dedicated training in how to properly categorize pottery fragments."
                },
                "answer": "C"
            },
            {
                "notes": "Black beans (Phaseolus vulgaris) are a nutritionally dense food, but they are difficult to digest in part because of their high levels of soluble fiber and compounds like raffinose. They also contain antinutrients like tannins and trypsin inhibitors, which interfere with the body's ability to extract nutrients from foods. In a research article, Marisela Granito and Glenda Álvarez from Simón Bolívar University in Venezuela claim that inducing fermentation of black beans using lactic acid bacteria improves the digestibility of the beans and makes them more nutritious.",  
                "question": "Which finding from Granito and Álvarez's research, if true, would most directly support their claim?",
                "answer_choices": {
                    "A": "When cooked, fermented beans contained significantly more trypsin inhibitors and tannins but significantly less soluble fiber and raffinose than nonfermented beans.",
                    "B": "Fermented beans contained significantly less soluble fiber and raffinose than nonfermented beans, and when cooked, the fermented beans also displayed a significant reduction in trypsin inhibitors and tannins.",
                    "C": "When the fermented beans were analyzed, they were found to contain two microorganisms, Lactobacillus casei and Lactobacillus plantarum, that are theorized to increase the amount of nitrogen absorbed by the gut after eating beans.",
                    "D": "Both fermented and nonfermented black beans contained significantly fewer trypsin inhibitors and tannins after being cooked at high pressure."
                },
                "answer": "B"
            },
            {
                "notes": "The novelist Toni Morrison was the first Black woman to work as an editor at the publishing company Random House, from 1967 to 1983. A scholar asserts that one of Morrison's likely aims during her time as an editor was to strengthen the presence of Black writers on the list of Random House's published authors.",
                "question": "Which finding, if true, would most strongly support the scholar's claim?",
                "answer_choices": {
                    "A": "The percentage of authors published by Random House who were Black rose in the early 1970s and stabilized throughout the decade.",
                    "B": "Black authors who were interviewed in the 1980s and 1990s were highly likely to cite Toni Morrison's novels as a principal influence on their work.",
                    "C": "The novels written by Toni Morrison that were published after 1983 sold significantly more copies and received wider critical acclaim than the novels she wrote that were published before 1983.",
                    "D": "Works that were edited by Toni Morrison during her time at Random House displayed stylistic characteristics that distinguished them from works that were not edited by Morrison."
                },
                "answer": "A"
            },
            {
                "notes": "Given that stars and planets initially form from the same gas and dust in space, some astronomers have posited that host stars (such as the Sun) and their planets (such as those in our solar system) are composed of the same materials, with the planets containing equal or smaller quantities of the materials that make up the host star. This idea is also supported by evidence that rocky planets in our solar system are composed of some of the same materials as the Sun.",
                "question": "Which finding, if true, would most directly weaken the astronomers' claim?",
                "answer_choices": {
                    "A": "Most stars are made of hydrogen and helium, but when cooled they are revealed to contain small amounts of iron and silicate.",  
                    "B": "A nearby host star is observed to contain the same proportion of hydrogen and helium as that of the Sun.",  
                    "C": "Evidence emerges that the amount of iron in some rocky planets is considerably higher than the amount in their host star.",  
                    "D": "The method for determining the composition of rocky planets is discovered to be less effective when used to analyze other kinds of planets."  
                },
                "answer": "C"
            }
        ]
    elif question_type == "Inferences":
        examples = [
            {
                "notes": "Musicians have tried the 'pay as you wish' pricing model. One band earned less than expected, while another artist earned more than expected using the same model.",
                "question": "Evaluate the variability in financial success of the 'pay as you wish' pricing strategy.",
                "answer_choices": {
                    "A": "prove financially successful for some musicians but disappointing for others.",
                    "B": "hold greater financial appeal for bands than for individual musicians.",
                    "C": "cause most musicians who use the model to lower the suggested prices of their songs and albums over time.",
                    "D": "more strongly reflect differences in certain musicians' popularity than traditional pricing models do."
                },
                "answer": "A"
            },
            {
                "notes": "A management research team found that workplace interruptions, though commonly viewed as reducing productivity, can increase employees' sense of belonging and satisfaction.",
                "question": "Assess the implications of research findings about workplace interruptions.",
                "answer_choices": {
                    "A": "the interpersonal benefits of some interruptions in the workplace may offset the perceived negative effects.",
                    "B": "in order to maximize productivity, employers should be willing to interrupt employees frequently throughout the day.",
                    "C": "most employees avoid interrupting colleagues because they don't appreciate being interrupted themselves.",
                    "D": "in order to cultivate an ideal workplace environment, interruptions of work should be discouraged."
                },
                "answer": "A"
            },
            {
                "notes": "In the 1800s, Euro-American farmers in the northeastern U.S. used farming techniques similar to those of the Haudenosaunee, despite not having direct contact with Haudenosaunee farms. This suggests indirect transmission of knowledge.",
                "question": "Determine the most logical explanation for how Euro-American farmers adopted Haudenosaunee techniques.",
                "answer_choices": {
                    "A": "those farmers learned the techniques from other people who were more directly influenced by Haudenosaunee practices.",
                    "B": "the crops typically cultivated by Euro-American farmers in the northeastern United States were not well suited to Haudenosaunee farming techniques.",
                    "C": "Haudenosaunee farming techniques were widely used in regions outside the northeastern United States.",
                    "D": "Euro-American farmers only began to recognize the benefits of Haudenosaunee farming techniques late in the nineteenth century."
                },
                "answer": "A"
            },
            {
                "notes": "Shakespeare's tragedies are widely appreciated today for their broad themes, but understanding his history plays requires deep knowledge of English history. Romeo and Juliet remains accessible due to its universal themes.",
                "question": "Compare the accessibility of Shakespeare's tragedies and history plays to modern audiences.",
                "answer_choices": {
                    "A": "many theatergoers and readers today are likely to find Shakespeare's history plays less engaging than the tragedies.",
                    "B": "some of Shakespeare's tragedies are more relevant to today's audiences than twentieth-century plays.",
                    "C": "Romeo and Juliet is the most thematically accessible of all Shakespeare's tragedies.",
                    "D": "experts in English history tend to prefer Shakespeare's history plays to his other works."
                },
                "answer": "A"
            },
            {
                "notes": "Researchers examined how interruptions affect people's enjoyment of experiences. They found that interruptions can increase enjoyment of pleasant experiences and hypothesized the opposite for unpleasant ones. In a study, participants listened to construction noise interrupted by silence breaks or not.",
                "question": "Infer researchers' expectations for the effect of interruptions on unpleasant experiences.",
                "answer_choices": {
                    "A": "find the disruptions more irritating as time went on.",
                    "B": "rate the listening experience as more negative than those whose listening experience was uninterrupted.",
                    "C": "rate the experience of listening to construction noise as lasting for less time than it actually lasted.",
                    "D": "perceive the volume of the construction noise as growing softer over time."
                },
                "answer": "B"
            }
        ]

    prompt = f"I'll show you five examples of {question_type} questions and their answers, then ask you a new question.\n\n"
    for i, ex in enumerate(examples, 1):
        prompt += f"Example {i}:\nText: {ex['notes']}\n\nQuestion: {ex['question']}\nOptions:\n"
        for L in sorted(ex['answer_choices']):
            prompt += f"{L}: {ex['answer_choices'][L]}\n"
        prompt += f"Answer: {ex['answer']}\n\n"
    prompt += "Now, please answer this new question:\n\n"
    prompt += f"Text: {question_data.get('notes','')}\n\nQuestion: {question_data.get('question','')}\nOptions:\n"
    for L, T in sorted(question_data.get('answer_choices', {}).items()):
        prompt += f"{L}: {T}\n"
    prompt += "\nProvide ONLY the letter of your answer (A, B, C, or D)."
    return prompt

def generate_cot_prompt(question_data, question_type):
    """生成一个鼓励逐步推理的提示"""
    prompt = f"Please solve the following {question_type} question using step-by-step reasoning.\n\n"
    prompt += f"Text: {question_data.get('notes','')}\n\n"
    prompt += f"Question: {question_data.get('question','')}\n\nOptions:\n"
    for L, T in sorted(question_data.get('answer_choices', {}).items()):
        prompt += f"{L}: {T}\n"
    prompt += "\nPlease think through this problem carefully using the following steps:\n"
    prompt += "1. Understand what the question is asking\n"
    if question_type == "Central Ideas and Details":
        prompt += "2. Analyze the main ideas and important details in the text\n"
        prompt += "3. Identify the central theme or primary information\n"
    elif question_type == "Command of Evidence":
        prompt += "2. Analyze the evidence or relevant information in the text\n"
        prompt += "3. Determine which evidence supports or weakens a particular viewpoint\n"
    elif question_type == "Inferences":
        prompt += "2. Analyze the explicit information in the text\n"
        prompt += "3. Make reasonable inferences based on the text content\n"
    prompt += "4. Evaluate each option carefully\n"
    prompt += "5. Explain your reasoning for selecting or rejecting each option\n"
    prompt += "6. Conclude with your final answer\n\n"
    prompt += "After your analysis, clearly indicate your final answer with 'Final Answer: [letter]'"
    return prompt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/home/ltang24/Education/SAT/Information_Ideas/Information_And_Ideas.json")
    parser.add_argument("--output", default="results")
    parser.add_argument("--models", nargs="+", default=["gpt-4o"])
    parser.add_argument("--strategies", nargs="+",
                        default=["zero-shot","five-shot","chain-of-thought"])
    parser.add_argument("--questions_per_type", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--temp", type=float, default=0.3)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    client = Client()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)
    questions = raw.get("questions", raw)

    by_skill = {}
    for q in questions:
        s = q.get("skill","Unknown")
        by_skill.setdefault(s, []).append(q)
    skill_types = ["Central Ideas and Details","Command of Evidence","Inferences"]
    for s in skill_types:
        pool = by_skill.get(s, [])
        if len(pool) > args.questions_per_type:
            by_skill[s] = random.sample(pool, args.questions_per_type)

    all_results = {}
    for model_name in args.models:
        all_results[model_name] = {}
        for strat in args.strategies:
            print("\n" + "-"*80)
            print(f"测试模型: {model_name} 使用策略: {strat}")
            print("-"*80 + "\n")

            results = {
                "total":0, "correct":0,
                "by_skill":{s:{"total":0,"correct":0,"by_difficulty":{}} for s in skill_types},
                "by_difficulty":{}, "details":[]
            }

            for skill in skill_types:
                print(f"测试技能类型: {skill}\n")
                for q in by_skill.get(skill, []):
                    num  = q.get("number",0)
                    diff = q.get("difficulty","Medium")
                    if skill=="Central Ideas and Details":
                        corr = central_ideas_details_answers.get(num,"")
                    elif skill=="Command of Evidence":
                        corr = command_of_evidence_answers.get(num,"")
                    else:
                        corr = inferences_answers.get(num,"")
                    corr = corr.strip().upper()
                    if not corr:
                        print(f"WARNING: 缺失题 {num} 正确答案，已跳过。")
                        continue

                    results["total"] += 1
                    results["by_skill"][skill]["total"] += 1
                    results["by_difficulty"].setdefault(diff,{"total":0,"correct":0})
                    results["by_skill"][skill]["by_difficulty"].setdefault(diff,{"total":0,"correct":0})
                    results["by_difficulty"][diff]["total"] += 1
                    results["by_skill"][skill]["by_difficulty"][diff]["total"] += 1

                    if strat=="zero-shot":
                        prompt = generate_zero_shot_prompt(q)
                    elif strat=="five-shot":
                        prompt = generate_five_shot_prompt(q, skill)
                    else:
                        prompt = generate_cot_prompt(q, skill)

                    try:
                        t0 = time.time()
                        resp = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role":"user","content":prompt}],
                            timeout=args.timeout,
                            temperature=args.temp
                        ).choices[0].message.content.strip()
                        rt = round(time.time()-t0,2)
                        ans = extract_answer(resp)
                        ok  = (ans==corr)

                        print(f"问题 {num} (技能: {skill}, 难度: {diff}):")
                        print(f"  模型答案: {ans}, 正确答案: {corr}")
                        print(f"  {'✓ 正确' if ok else '✗ 错误'} (运行时间: {rt}s)\n")

                        if ok:
                            results["correct"] += 1
                            results["by_skill"][skill]["correct"] += 1
                            results["by_difficulty"][diff]["correct"] += 1
                            results["by_skill"][skill]["by_difficulty"][diff]["correct"] += 1

                        results["details"].append({
                            "num":num, "skill":skill, "diff":diff,
                            "correct":corr, "model":ans, "ok":ok, "rt":rt
                        })
                    except Exception as e:
                        print(f"Error on Q{num}: {e}\n")
                        results["details"].append({
                            "num":num, "skill":skill, "diff":diff,
                            "correct":corr, "model":None, "ok":False, "error":str(e)
                        })

            # 打印策略摘要
            total = results["total"]
            correct = results["correct"]
            acc = (correct/total if total else 0)
            print(f"{model_name} 使用 {strat} 策略的摘要:")
            print(f"整体准确率: {acc:.2%} ({correct}/{total})\n")
            for s in skill_types:
                bs = results["by_skill"][s]
                t = bs["total"]; c = bs["correct"]
                a = (c/t if t else 0)
                print(f"  {s}准确率: {a:.2%} ({c}/{t})")
                for d, ct in bs["by_difficulty"].items():
                    tt = ct["total"]; cc = ct["correct"]
                    aa = (cc/tt if tt else 0)
                    print(f"    {d}难度: {aa:.2%} ({cc}/{tt})")
                print()
            all_results[model_name][strat] = results

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = os.path.join(args.output, f"sat_reading_results_{ts}.json")
    with open(fn,"w",encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"所有结果已保存到 {fn}")

if __name__ == "__main__":
    main()
