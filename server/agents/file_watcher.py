"""
Run separately: python -m agents.file_watcher
Watches the results directory and updates the database.
"""
import time
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import init_database
from database import models

RESULTS_DIR = os.path.expanduser("~/Desktop/agent-workspace/results")
PROCESSED_DIR = os.path.expanduser("~/Desktop/agent-workspace/processed")
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)


def poll_results():
    print("[WATCHER] Polling for agent results...")
    while True:
        if not os.path.exists(RESULTS_DIR):
            time.sleep(5)
            continue

        for filename in os.listdir(RESULTS_DIR):
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(RESULTS_DIR, filename)
            task_id = filename.replace(".json", "")

            try:
                with open(filepath, "r") as f:
                    result = json.load(f)

                # Update task in database
                models.update_task_status(task_id, "agent_completed")
                models.store_agent_feedback(
                    task_id=task_id,
                    output=result.get("code", ""),
                    explanation=result.get("explanation", ""),
                    status="success",
                )

                # Move to processed
                os.rename(filepath, os.path.join(PROCESSED_DIR, filename))
                print(f"[WATCHER] Processed result for task {task_id}")

            except Exception as e:
                print(f"[WATCHER] Error processing {filename}: {e}")

        time.sleep(5)


if __name__ == "__main__":
    init_database()
    poll_results()
