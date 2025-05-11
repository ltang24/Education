# Educational Benchmarks & LLM-Evaluation Suite  

A **single-stop repository** for evaluating GPT-family, LLaMA, Gemini and other large-language models on GRE, GMAT, SAT, TOEFL and IELTS style question sets.  
The suite ships:

* Curated JSON datasets for each exam section  
* One **Python driver per dataset per model**   
* A generic **`runtime.py`** summariser that converts those JSON files into latency/accuracy CSV tables  
* Utility scripts for cross-dataset accuracy aggregation and plotting

---

## 1 · Repository Layout

### Folder Naming Rules

| Prefix  | Contains                                |
|---------|-----------------------------------------|
| `GRE *` | Any GRE section (Math/RC/Verbal)        | 
| `GMAT/` | Quant, Verbal, Data Insights            | 
| `SAT/`  | Math & Reading subsections              | 
| `TOFEL/`| TOEFL Reading & Listening               | 
| `IELTS/`| IELTS Reading & Listening               |

---

## 2 · Prerequisites

* Python ≥ 3.10  
* [g4f](https://pypi.org/project/g4f/) — an OpenAI-compatible, key-free wrapper  
* (Optional) `llama-cpp-python`, Gemini SDK, etc. if you plan to run local/other models

##3 · Quick Start
```bash
pip install g4f
# clone
git clone https://github.com/<your-org>/Education.git
cd Education

# virtual environment
python -m venv .venv && source .venv/bin/activate

# run a dataset: GRE Math Medium with GPT-4-o (via g4f)
cd "GRE Math Medium"
python run_gpt4o.py          # ➜ gre_math_medium_gpt4o.json  ← already includes overall accuracy

#Generate Latency CSV
cd ../../tools
python runtime.py ../GRE\ Math\ Medium/gre_math_medium_gpt4o.json \
                  --out ../runtime_gre/gre_math_medium_gpt4o.csv






