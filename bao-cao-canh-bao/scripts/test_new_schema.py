import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_agent.chatbot import DNHChatbot

def run_tests():
    # Force stdout encoding to UTF-8
    sys.stdout.reconfigure(encoding='utf-8')
    
    chatbot = DNHChatbot()
    
    test_cases = [
        "Cho tôi biết doanh thu mien bac",
        "Khách hàng nào đang vượt hạn mức công nợ",
        "Xem chi tiết các hợp đồng thầu ETC"
    ]
    
    for i, q in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {q} ---")
        try:
            res = chatbot.ask(q)
            print("Generated SQL:")
            print(res['sql'])
            print(f"Row count: {len(res['data'])}")
            if len(res['data']) > 0:
                print("Sample Row:", res['data'][0])
            else:
                print("No rows returned.")
            print("Answer:")
            print(res['answer'][:500] + "...")
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    run_tests()
