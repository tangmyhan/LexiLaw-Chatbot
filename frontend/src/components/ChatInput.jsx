import useAutosize from '@/hooks/useAutosize';
import sendIcon from '@/assets/images/send.svg';

function ChatInput({ newMessage, isLoading, setNewMessage, submitNewMessage }) {
  const textareaRef = useAutosize(newMessage);

  function handleKeyDown(e) {
    if(e.keyCode === 13 && !e.shiftKey && !isLoading) {
      e.preventDefault();
      submitNewMessage();
    }
  }
  
  return(
    <div className='relative w-full max-w-4xl mx-auto'>
      <div className='bg-indigo-50/50 p-2 rounded-3xl shadow-inner border border-indigo-100/50 relative overflow-hidden group transition-all duration-300 hover:bg-indigo-50/80 focus-within:bg-indigo-50'>
        <div className='relative flex items-end bg-white rounded-2xl overflow-hidden shadow-sm border border-slate-200 transition-all duration-300 focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100'>
          <textarea
            className='flex-1 w-full max-h-[160px] min-h-[56px] py-4 px-5 pr-14 bg-transparent resize-none placeholder:text-slate-400 placeholder:select-none text-slate-700 leading-relaxed focus:outline-none custom-scrollbar'
            ref={textareaRef}
            rows='1'
            disabled={isLoading}
            placeholder={isLoading ? "Đang tạo sơ đồ và phản hồi..." : "Nhập câu hỏi pháp lý của bạn..."}
            value={newMessage}
            onChange={e => setNewMessage(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            className={`absolute bottom-[8px] right-[8px] p-2.5 rounded-xl transition-all duration-300 flex items-center justify-center ${
              newMessage.trim() && !isLoading 
                ? 'bg-gradient-to-tr from-indigo-500 to-blue-500 shadow-md hover:shadow-lg hover:-translate-y-0.5' 
                : 'bg-slate-100 cursor-not-allowed opacity-60'
            }`}
            onClick={submitNewMessage}
            disabled={!newMessage.trim() || isLoading}
          >
            <img src={sendIcon} alt='send' className={`w-5 h-5 transition-transform duration-300 ${newMessage.trim() && !isLoading ? 'filter brightness-0 invert opacity-100' : 'opacity-40'}`} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatInput;