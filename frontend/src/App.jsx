import Chatbot from '@/components/Chatbot';

function App() {
  return (
    <div className='flex flex-col h-screen w-full bg-slate-50 overflow-hidden font-sans text-slate-800'>
      <header className='shrink-0 z-20 bg-white/80 backdrop-blur-xl border-b border-slate-200/60 px-6 py-4 shadow-xs sticky top-0'>
        <div className='max-w-[1600px] w-full mx-auto flex items-center justify-between'>
          <div className='flex items-center gap-3'>
            <div className='w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center text-white font-bold shadow-md'>
              L
            </div>
            <h1 className='font-urbanist text-[1.4rem] tracking-tight font-bold bg-gradient-to-r from-slate-800 to-slate-600 bg-clip-text text-transparent'>
              LexiLaw AI
            </h1>
          </div>
          <div className="text-xs font-semibold text-indigo-600 bg-indigo-50 border border-indigo-100 px-3 py-1.5 rounded-full shadow-inner flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
            Knowledge Graph Render
          </div>
        </div>
      </header>
      <main className='flex-1 overflow-hidden w-full max-w-[1600px] mx-auto'>
        <Chatbot />
      </main>
    </div>
  );
}

export default App;