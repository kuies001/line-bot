# daily_rollover.py
import os
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PROMPT_FILE = os.getenv('LLM_PROMPT_FILE')
OVERRIDE_FILE = os.getenv('LLM_HISTORY_FILE', '/app/config/llm_config_old.json')

def rollover_prompt():
    today = datetime.today().strftime('%Y-%m-%d')
    dst = OVERRIDE_FILE.replace('llm_config_old.json', f'llm_config_old_{today}.json')
    if os.path.exists(OVERRIDE_FILE):
        shutil.move(OVERRIDE_FILE, dst)
    shutil.copy(PROMPT_FILE, OVERRIDE_FILE)
    print(f"[{datetime.now()}] rollover complete → {dst}")

if __name__ == "__main__":
    rollover_prompt()
