import os
import time
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.rag import rag_engine
import logging

logging.basicConfig(level=logging.ERROR)

questions = [
    "Patient name",
    "Age",
    "Diagnosis",
    "Medicines",
    "Blood pressure",
    "Temperature",
    "HbA1c",
    "Follow-up advice"
]

def run_test():
    total_time = 0
    print("Starting Benchmark...\n")
    for q in questions:
        start = time.perf_counter()
        try:
            answer, sources = rag_engine.generate_answer(q, 1)
            elapsed = time.perf_counter() - start
            total_time += elapsed
            print(f"Q: {q}")
            print(f"A: {answer}")
            for src in sources:
                print(f"  [Page {src['page']}] {src['content'][:50]}...")
            print(f"Time: {elapsed:.2f}s")
            print("-" * 40)
        except Exception as e:
            print(f"Q: {q}\nError: {e}")
            
    print(f"\nAverage Time: {total_time / len(questions):.2f}s")

if __name__ == "__main__":
    run_test()
