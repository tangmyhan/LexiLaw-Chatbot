import { useState } from 'react';
import { useImmer } from 'use-immer';
import api from '@/api';
import { parseSSEStream } from '@/utils';
import ChatMessages from '@/components/ChatMessages';
import ChatInput from '@/components/ChatInput';
import GraphVisualization from '@/components/GraphVisualization';

function Chatbot() {
  const [chatId, setChatId] = useState(null);
  const [messages, setMessages] = useImmer([]);
  const [newMessage, setNewMessage] = useState('');
  const [graphData, setGraphData] = useState(null);
  const [showGraph, setShowGraph] = useState(false);

  const isLoading = messages.length > 0 && messages[messages.length - 1].loading;

  async function submitNewMessage() {
    const trimmedMessage = newMessage.trim();
    if (!trimmedMessage || isLoading) return;

    setMessages(draft => [...draft,
    { role: 'user', content: trimmedMessage },
    { role: 'assistant', content: '', sources: [], loading: true }
    ]);
    setNewMessage('');

    let chatIdOrNew = chatId;
    try {
      if (!chatId) {
        const { id } = await api.createChat();
        setChatId(id);
        chatIdOrNew = id;
      }

      const stream = await api.sendChatMessage(chatIdOrNew, trimmedMessage);
      for await (const textChunk of parseSSEStream(stream)) {
        setMessages(draft => {
          draft[draft.length - 1].content += textChunk;
        });
      }
      setMessages(draft => {
        draft[draft.length - 1].loading = false;
      });

      // Lấy dữ liệu graph visualization trực tiếp từ kết quả (nếu endpoint độc lập)
      try {
        const graph = await api.getGraphVisualization(chatIdOrNew, trimmedMessage);
        if (graph && graph.nodes && graph.nodes.length > 0) {
          setGraphData(graph);
          if (!showGraph) setShowGraph(true);
        }
      } catch (err) {
        console.error('Error fetching graph:', err);
      }
    } catch (err) {
      console.log(err);
      setMessages(draft => {
        draft[draft.length - 1].loading = false;
        draft[draft.length - 1].error = true;
      });
    }
  }

  return (
    <div className='w-full h-[calc(100vh-73px)] flex flex-col lg:flex-row gap-6 p-4 lg:p-6'>
      {/* Cửa sổ Chat */}
      <div className={`flex flex-col h-full bg-white rounded-[2rem] shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 transition-all duration-500 ease-in-out ${graphData && showGraph ? 'lg:w-[450px] xl:w-[500px] shrink-0' : 'w-full max-w-4xl mx-auto'}`}>
        <div className="flex-1 overflow-y-auto px-6 pt-6 pb-2 custom-scrollbar">
          {messages.length === 0 && (
            <div className='mt-10 text-center font-urbanist text-slate-600 space-y-3 px-4'>
              <div className="w-20 h-20 bg-gradient-to-br from-indigo-50 to-blue-50/50 rounded-3xl flex items-center justify-center mx-auto mb-6 shadow-inner border border-indigo-100">
                <span className="text-4xl drop-shadow-sm">⚖️</span>
              </div>
              <p className="text-2xl font-bold text-slate-800 tracking-tight">Xin chào!</p>
              <p className="leading-relaxed text-slate-500 font-medium pb-2">Tôi là LexiLaw, trợ lý ảo chuyên tư vấn thuật ngữ và cấu trúc kiết xuất của Luật Lao động Việt Nam.</p>
              <div className="bg-slate-50/80 p-5 rounded-2xl mt-6 border border-slate-100">
                <p className="text-sm text-slate-500 italic">"Hãy đặt một câu hỏi bất kỳ, tôi sẽ phân tích và trích xuất sơ đồ mạng lưới tri thức trực quan cho bạn."</p>
              </div>
            </div>
          )}
          <ChatMessages messages={messages} isLoading={isLoading} />
        </div>
        
        {graphData && (
          <div className="px-6 py-2 bg-gradient-to-t from-white via-white to-transparent flex justify-center z-10">
            <button
              onClick={() => setShowGraph(!showGraph)}
              className="px-5 py-2 bg-slate-50 border border-slate-200 text-slate-700 font-bold rounded-xl hover:bg-slate-100 hover:border-slate-300 shadow-sm transition-all flex items-center gap-2 text-xs uppercase tracking-wider"
            >
              <span className={showGraph ? 'text-slate-600' : 'text-indigo-600'}>{showGraph ? 'Ẩn Sơ Đồ Cấu Trúc' : 'Mở Sơ đồ Tri thức'}</span>
            </button>
          </div>
        )}

        <div className="px-6 pb-6 pt-3 bg-white rounded-b-[2rem]">
          <ChatInput newMessage={newMessage} isLoading={isLoading} setNewMessage={setNewMessage} submitNewMessage={submitNewMessage} />
        </div>
      </div>

      {/* Cửa sổ Sơ đồ tri thức */}
      {showGraph && graphData && (
        <div className="flex-1 h-full min-h-[500px] animate-in fade-in slide-in-from-right-8 duration-500 ease-out">
          <GraphVisualization graphData={graphData} />
        </div>
      )}
    </div>
  );
}

export default Chatbot;