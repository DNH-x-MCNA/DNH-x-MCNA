import sys
sys.stdout.reconfigure(encoding='utf-8')
import os

targets = ["16.12", "16,12", "29.40", "29,40", "12.03", "12,03", "32.66", "32,66"]
print("Searching D:\\DNH for Slide 1 values...")

# Let's walk the directory
for root, dirs, files in os.walk("D:\\DNH"):
    # Skip system/cache dirs
    if any(p in root for p in [".git", "__pycache__", "venv", ".idea", "node_modules"]):
        continue
    for file in files:
        if file.endswith((".py", ".sql", ".txt", ".json", ".md", ".yaml", ".yml")):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for t in targets:
                    if t in content:
                        print(f"  Found '{t}' in: {filepath}")
            except Exception as e:
                pass
conn = None
