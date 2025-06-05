# daily_rollover.py
import os
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GLOBAL_PROMPT_FILE = os.getenv('GLOBAL_PROMPT_FILE', '/app/config/global_system_prompt.txt')
OVERRIDE_FILE = os.getenv('LLM_HISTORY_FILE', '/app/config/global_prompt_old.txt')

def rollover_prompt():
    today = datetime.today().strftime('%Y-%m-%d')
    dst = OVERRIDE_FILE.replace('global_prompt_old.txt', f'global_prompt_old_{today}.txt')
    if os.path.exists(OVERRIDE_FILE):
        shutil.move(OVERRIDE_FILE, dst)
    shutil.copy(GLOBAL_PROMPT_FILE, OVERRIDE_FILE)
    print(f"[{datetime.now()}] rollover complete → {dst}")

if __name__ == "__main__":
    rollover_prompt()
