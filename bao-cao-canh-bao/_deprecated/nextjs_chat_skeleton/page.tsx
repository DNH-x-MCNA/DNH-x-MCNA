'use client';

import { useState, useRef, useEffect } from 'react';

interface Message {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  sql?: string;
  tableData?: any[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { 
      id: '1', 
      sender: 'ai', 
      text: 'Chào anh/chị. Tôi là AI trợ lý phân tích dữ liệu Dược Nam Hà. Tôi có thể giúp anh/chị tra cứu nhanh doanh số vùng miền, kiểm tra công nợ quá hạn hoặc báo cáo tồn kho dược phẩm từ SQL Server DWH.' 
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll chat to bottom when message list changes
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg: Message = { id: Date.now().toString(), sender: 'user', text: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(false); // set true when connecting to real backend API

    // Simulate response delay for mock demo
    setLoading(true);
    setTimeout(() => {
      const isRevenueQuery = input.toLowerCase().includes('doanh thu') || input.toLowerCase().includes('doanh số');
      const isDebtQuery = input.toLowerCase().includes('công nợ') || input.toLowerCase().includes('quá hạn') || input.toLowerCase().includes('nợ');
      const isInventoryQuery = input.toLowerCase().includes('tồn kho') || input.toLowerCase().includes('kho') || input.toLowerCase().includes('tồn');
      
      let answer = '';
      let sql = '';
      let tableData: any[] = [];

      if (isRevenueQuery) {
        answer = 'Tổng hợp chỉ tiêu doanh số kinh doanh kỳ tháng 10/2025 theo vùng miền được ghi nhận như sau:';
        sql = 'SELECT area_code, SUM(month_sale_target) as target, SUM(month_sale_amount) as actual, (SUM(month_sale_amount)*100.0/SUM(month_sale_target)) as pct FROM dnh_core.kpi_summary GROUP BY area_code;';
        tableData = [
          { 'Vùng miền': 'Miền Bắc', 'Chỉ tiêu Target (VND)': 21230443963, 'Thực đạt (VND)': 18004727678, 'Tỷ lệ hoàn thành': '84.8%' },
          { 'Miền Nam': 'Miền Nam', 'Chỉ tiêu Target (VND)': 5420310240, 'Thực đạt (VND)': 4895238100, 'Tỷ lệ hoàn thành': '90.3%' }
        ];
      } else if (isDebtQuery) {
        answer = 'Dưới đây là danh sách 3 khách hàng có nợ quá hạn cao nhất trên hệ thống receivable_detail (DWH SQL Server):';
        sql = 'SELECT TOP 3 customer_code, customer_name, total_overdue FROM dnh_core.receivable_detail WHERE total_overdue > 0 ORDER BY total_overdue DESC;';
        tableData = [
          { 'Mã KH': '1002341', 'Tên khách hàng': 'Công ty Dược phẩm Dương Tự Giang', 'Kênh': 'OTC', 'Nợ quá hạn (VND)': 139270560 },
          { 'Mã KH': '1004562', 'Tên khách hàng': 'Nhà thuốc Long Châu Chi nhánh 2', 'Kênh': 'OTC', 'Nợ quá hạn (VND)': 87400230 },
          { 'Mã KH': '1007890', 'Tên khách hàng': 'Hộ kinh doanh Nhà thuốc Tư Anh', 'Kênh': 'OTC', 'Nợ quá hạn (VND)': 42100980 }
        ];
      } else if (isInventoryQuery) {
        answer = 'Số liệu tồn kho các sản phẩm chính và số tháng bán dự phóng tương ứng:';
        sql = 'SELECT TOP 3 item_code, item_name, closing_qty, months_to_sell FROM dnh_core.inventory ORDER BY closing_qty DESC;';
        tableData = [
          { 'Mã SP': '31190000680', 'Tên sản phẩm': 'Siro thuốc ho bổ phế Nam Hà chỉ khái lộ', 'Đvt': 'Lọ', 'Số lượng tồn': 942492, 'Dự phóng số tháng bán hết': 3 },
          { 'Mã SP': '31190000690', 'Tên sản phẩm': 'Siro Thuốc ho Bổ phế Nam Hà chỉ khái lộ KĐ', 'Đvt': 'Lọ', 'Số lượng tồn': 327891, 'Dự phóng số tháng bán hết': 3 }
        ];
      } else {
        answer = `Tôi đã nhận được câu hỏi: "${input}". Hiện hệ thống đang chạy ở chế độ Demo Mock.`;
        sql = 'SELECT TOP 5 * FROM dnh_core.kpi_summary;';
        tableData = [];
      }

      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: 'ai',
          text: answer,
          sql: sql,
          tableData: tableData.length > 0 ? tableData : undefined
        }
      ]);
      setLoading(false);
    }, 1200);
  };

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-white font-sans">
      {/* Header bar */}
      <header className="flex justify-between items-center p-4 bg-slate-950 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="bg-blue-600 p-2 rounded-lg text-white">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide">Dược Nam Hà</h1>
            <p className="text-xs text-slate-400">Trợ lý phân tích dữ liệu AI (T-SQL DWH)</p>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-xs text-slate-400">SQL Server Active</span>
        </div>
      </header>

      {/* Chat Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-3xl rounded-lg p-4 shadow-md ${
              msg.sender === 'user' 
                ? 'bg-blue-600 text-white rounded-br-none' 
                : 'bg-slate-800 text-slate-100 rounded-bl-none border border-slate-700'
            }`}>
              <p className="whitespace-pre-wrap leading-relaxed text-sm">{msg.text}</p>
              
              {/* Show T-SQL query translation */}
              {msg.sql && (
                <details className="mt-3 text-xs bg-slate-950 p-2.5 rounded border border-slate-700 select-all">
                  <summary className="font-semibold text-slate-400 cursor-pointer focus:outline-none hover:text-slate-200">
                    <i className="fa-solid fa-code mr-1"></i> Xem câu lệnh T-SQL được AI biên dịch
                  </summary>
                  <pre className="block mt-2 font-mono text-blue-300 overflow-x-auto whitespace-pre-wrap">{msg.sql}</pre>
                </details>
              )}

              {/* Show structured table if data exists */}
              {msg.tableData && msg.tableData.length > 0 && (
                <div className="mt-3 overflow-x-auto rounded border border-slate-750 max-h-60">
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px] sticky top-0">
                      <tr>
                        {Object.keys(msg.tableData[0]).map((k) => (
                          <th key={k} className="px-3 py-2 border-b border-slate-700">{k}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700 bg-slate-850 text-xs">
                      {msg.tableData.map((row, idx) => (
                        <tr key={idx} className="hover:bg-slate-750 transition-colors">
                          {Object.values(row).map((val: any, vIdx) => (
                            <td key={vIdx} className="px-3 py-2 font-mono">{typeof val === 'number' ? val.toLocaleString() : String(val)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ))}
        
        {/* Loading Spinner */}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-800 text-slate-400 rounded-lg p-4 flex items-center space-x-2 border border-slate-700">
              <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span className="text-xs">AI đang phân tích dữ liệu DWH...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input area */}
      <form onSubmit={handleSend} className="p-4 bg-slate-950 border-t border-slate-800 flex space-x-3">
        <input 
          type="text" 
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Nhập câu hỏi tra cứu (ví dụ: Doanh thu quý này, top nợ quá hạn, kiểm tra tồn kho)..."
          className="flex-1 bg-slate-900 border border-slate-700 rounded px-4 py-3 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 text-sm"
        />
        <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded font-semibold text-sm transition">
          Gửi <i className="fa-solid fa-paper-plane ml-1"></i>
        </button>
      </form>
    </div>
  );
}
