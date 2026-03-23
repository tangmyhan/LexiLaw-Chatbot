import Markdown from 'react-markdown';
import useAutoScroll from '@/hooks/useAutoScroll';
import Spinner from '@/components/Spinner';
import userIcon from '@/assets/images/user.svg';
import errorIcon from '@/assets/images/error.svg';

function ChatMessages({ messages, isLoading }) {
  const scrollContentRef = useAutoScroll(isLoading);
  
  return (
    <div ref={scrollContentRef} className='grow space-y-6 flex flex-col'>
      {messages.map(({ role, content, loading, error }, idx) => (
        <div 
          key={idx} 
          className={`group flex items-start gap-4 py-4 px-5 rounded-3xl transition-all duration-300 ${
            role === 'user' 
              ? 'bg-gradient-to-br from-indigo-50 to-blue-50/50 border border-indigo-100/50 shadow-sm self-end ml-12 rounded-tr-sm' 
              : 'bg-white border border-slate-100 shadow-[0_2px_10px_rgb(0,0,0,0.02)] self-start mr-8 rounded-tl-sm'
          }`}
        >
          {role === 'user' && (
            <div className="w-8 h-8 rounded-full bg-white shadow-sm flex items-center justify-center shrink-0 border border-indigo-100">
               <img className='h-[18px] w-[18px]' src={userIcon} alt='user' />
            </div>
          )}
          {role === 'assistant' && (
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-blue-600 shadow-md flex items-center justify-center shrink-0 text-white font-bold text-xs mt-1">
               L
            </div>
          )}
          
          <div className="flex-1 min-w-0 mt-1">
            <div className={`prose prose-sm max-w-none ${role === 'user' ? 'text-indigo-950 font-medium' : 'text-slate-700 prose-headings:text-slate-800 prose-a:text-indigo-600 prose-code:text-indigo-600 prose-pre:bg-slate-50'}`}>
              {(loading && !content) ? <Spinner />
                : (role === 'assistant')
                  ? <Markdown>{content}</Markdown>
                  : <div className='whitespace-pre-line'>{content}</div>
              }
            </div>
            {error && (
              <div className={`flex items-center gap-2 text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg mt-3 border border-red-100`}>
                <img className='h-4 w-4' src={errorIcon} alt='error' />
                <span className="font-medium">Đã có lỗi xảy ra khi tạo câu trả lời.</span>
              </div>
            )}
            
            {loading && content && (
               <div className="h-1.5 w-1.5 bg-indigo-500 rounded-full animate-bounce mt-2" style={{animationDelay: '0ms'}} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ChatMessages;