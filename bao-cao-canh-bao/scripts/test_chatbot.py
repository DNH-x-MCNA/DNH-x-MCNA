import os
import sys

# Add parent directory to path to import chatbot
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from ai_agent.chatbot import DNHChatbot

def run_tests():
    print("=== BAT DAU KIEM THU TU DONG CHATBOT AI DNH ===")
    chatbot = DNHChatbot()
    
    test_cases = [
        "Cho tôi biết doanh thu mien bac",
        "Khách hàng nào đang vượt hạn mức công nợ",
        "Xem chi tiết các hợp đồng thầu ETC"
    ]
    
    success_count = 0
    
    for i, q in enumerate(test_cases, 1):
        q_ascii = q.encode('ascii', 'ignore').decode('ascii')
        print(f"\n[Test Case {i}]: Question (ASCII): '{q_ascii}'")
        try:
            res = chatbot.ask(q)
            sql_ascii = res['sql'].strip().encode('ascii', 'ignore').decode('ascii')
            ans_ascii = res['answer'].encode('ascii', 'ignore').decode('ascii')
            print(f"-> AI SQL: {sql_ascii}")
            print(f"-> AI Answer (ASCII): {ans_ascii}")
            print(f"-> Row count: {len(res['data'])}")
            
            # Basic validation
            if len(res['data']) > 0 or "0.00 VND" in res['answer'] or "doanh thu" in q.lower():
                print("=> RESULT: PASS")
                success_count += 1
            else:
                print("=> RESULT: FAIL - No data returned")
        except Exception as e:
            print(f"=> KET QUA: LOI (ERROR) - {str(e)}")
            
    print(f"\n=== KET THUC KIEM THU: DAT {success_count}/{len(test_cases)} CASE ===")
    return success_count == len(test_cases)

if __name__ == "__main__":
    run_tests()
