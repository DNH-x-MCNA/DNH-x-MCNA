import sys
sys.stdout.reconfigure(encoding='utf-8')
import os

p = 'C:/Users/Admin/.gemini/antigravity/brain/6e07a087-162d-4bf4-9422-6c9923c61c4a/.system_generated/tasks/task-3649.log'
if os.path.exists(p):
    with open(p, encoding='utf-8') as f:
        content = f.read()
    
    # Search for SQL query or output
    lines = content.split('\n')
    found_sql = False
    for i, line in enumerate(lines):
        if "doanh thu tháng 6 theo kênh và miền" in line:
            print(f"Found question at line {i+1}: {line}")
            # Print the next 20 lines to see if there is any printout of SQL
            print("\n=== Next 30 lines after question ===")
            for j in range(i+1, min(i+31, len(lines))):
                print(lines[j])
            found_sql = True
            
    if not found_sql:
        print("Question text not found in logs.")
else:
    print("Log file not found.")
