import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_agent.chatbot import DNHChatbot

chatbot = DNHChatbot()

test_cases = [
    "Cho tôi biết doanh thu theo từng tháng",
    "Báo cáo doanh thu trong 7 ngày gần nhất",
    "Tình hình kpi doanh thu đến ngày 20 của tháng 6"
]

for i, q in enumerate(test_cases, 1):
    print(f"\n{'='*80}")
    print(f"Test Case {i}: {q}")
    print('='*80)
    try:
        res = chatbot.ask(q)
        print(f"Generated SQL:\n{res['sql']}")
        print(f"\nRow count: {len(res['data'])}")
        if res['data']:
            print(f"Sample rows:")
            for j, row in enumerate(res['data'][:10]):
                print(f"  #{j+1}: {row}")
        print(f"\nAnswer (first 800 chars):\n{res['answer'][:800]}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
