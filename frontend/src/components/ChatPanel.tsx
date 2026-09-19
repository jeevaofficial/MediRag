import { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import { Copy, Check, Send, Bot, User, Clock, FileText, ChevronRight } from 'lucide-react';

interface Source {
  page: number | string;
  content: string;
}

interface Message {
  role: string;
  content: string;
  sources?: Source[];
  timestamp?: string;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('Retrieving medical context...');
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const loadingIntervalRef = useRef<number | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const history = await api.getChatHistory();
        if (history.length === 0) {
          // Empty state handled in render
        } else {
          setMessages(history.map((m: any) => ({ ...m, timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) })));
        }
      } catch (e) {
        console.error("Failed to load chat history", e);
      }
    };
    fetchHistory();
  }, []);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
      }
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, loadingText]);

  useEffect(() => {
    if (isLoading) {
      setLoadingText('Retrieving medical context...');
      loadingIntervalRef.current = window.setInterval(() => {
        setLoadingText(prev => 
          prev === 'Retrieving medical context...' ? 'Generating answer...' : 'Retrieving medical context...'
        );
      }, 3000);
    } else {
      if (loadingIntervalRef.current) {
        clearInterval(loadingIntervalRef.current);
      }
    }
    return () => {
      if (loadingIntervalRef.current) clearInterval(loadingIntervalRef.current);
    };
  }, [isLoading]);

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const deduplicateSources = (sources: Source[]) => {
    const unique = new Map<string, Source>();
    sources.forEach(src => {
      if (!unique.has(src.content)) {
        unique.set(src.content, src);
      }
    });
    return Array.from(unique.values());
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage, timestamp }]);
    setIsLoading(true);
    
    try {
      const response = await api.queryChat(userMessage);
      
      // Ensure we don't duplicate responses (Strict mode protection)
      setMessages(prev => {
        // If the last message is already this exact assistant response, don't add it again
        const lastMsg = prev[prev.length - 1];
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === response.answer) {
          return prev;
        }
        return [...prev, {
          role: 'assistant',
          content: response.answer,
          sources: response.sources ? deduplicateSources(response.sources) : [],
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }];
      });
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `**Error:** ${err.message || 'Failed to get answer'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const highlightSnippet = (content: string) => {
    // A simple highlight simulation: if we want to bold some keywords or just style the block
    return content.trim(); 
  };

  return (
    <div className="flex flex-col h-full bg-white relative">
      <div 
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto px-4 sm:px-6 md:px-8 pt-6 pb-40 scroll-smooth"
      >
        <div className="max-w-4xl mx-auto space-y-8">
          
          {messages.length === 0 && !isLoading && (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center h-full text-center mt-20"
            >
              <div className="bg-blue-50 p-6 rounded-full mb-6 text-blue-500">
                <Bot size={48} />
              </div>
              <h2 className="text-2xl font-bold text-gray-800 mb-3">Welcome to MediRAG AI</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-8 leading-relaxed">
                I am your specialized medical reference assistant. Upload medical documents in the sidebar and ask me questions to extract relevant information.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl text-left">
                <div className="bg-white border border-gray-100 p-4 rounded-xl shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => setInput("What are the patient's symptoms?")}>
                  <p className="font-medium text-gray-700 text-sm">"What are the patient's symptoms?"</p>
                </div>
                <div className="bg-white border border-gray-100 p-4 rounded-xl shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => setInput("Summarize the treatment plan.")}>
                  <p className="font-medium text-gray-700 text-sm">"Summarize the treatment plan."</p>
                </div>
              </div>
            </motion.div>
          )}

          <AnimatePresence initial={false}>
            {messages.map((msg, idx) => (
              <motion.div 
                key={idx} 
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div className={`flex max-w-[85%] md:max-w-[75%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'} items-end gap-3`}>
                  
                  {/* Avatar */}
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-emerald-500 text-white'}`}>
                    {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                  </div>

                  {/* Bubble */}
                  <div className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                    <div className={`relative px-5 py-4 rounded-2xl shadow-sm ${msg.role === 'user' ? 'bg-blue-600 text-white rounded-br-sm' : 'bg-gray-50 text-gray-800 border border-gray-200 rounded-bl-sm'}`}>
                      
                      {msg.role === 'assistant' && (
                        <button 
                          onClick={() => handleCopy(msg.content, idx)}
                          className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 transition-colors"
                          title="Copy answer"
                        >
                          {copiedIndex === idx ? <Check size={16} className="text-emerald-500" /> : <Copy size={16} />}
                        </button>
                      )}

                      <div className={`prose prose-sm max-w-none ${msg.role === 'user' ? 'prose-invert' : ''}`}>
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                      
                      {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                        <div className="mt-5 pt-4 border-t border-gray-200">
                          <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1">
                            <FileText size={14} /> Sources
                          </p>
                          <div className="space-y-3">
                            {msg.sources.map((src, i) => (
                              <div key={i} className="bg-white p-3 rounded-xl border border-gray-100 shadow-sm text-sm group hover:border-blue-200 transition-colors">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-semibold text-blue-600 flex items-center gap-1">
                                    <ChevronRight size={14} /> Page {src.page !== undefined ? src.page : 'N/A'}
                                  </span>
                                </div>
                                <span className="text-gray-600 italic bg-yellow-50/50 block p-1.5 rounded text-xs leading-relaxed border border-yellow-100/50">
                                  "...{highlightSnippet(src.content)}..."
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                    
                    {/* Timestamp */}
                    {msg.timestamp && (
                      <div className="flex items-center gap-1 mt-1 text-[11px] text-gray-400 px-1">
                        <Clock size={10} />
                        {msg.timestamp}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {isLoading && (
            <motion.div 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex justify-start w-full"
            >
              <div className="flex max-w-[85%] md:max-w-[75%] flex-row items-end gap-3">
                <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-emerald-500 text-white">
                  <Bot size={16} />
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-2xl rounded-bl-sm px-5 py-4 text-gray-500 flex flex-col gap-2">
                  <div className="flex items-center space-x-2 h-4">
                    <motion.div className="w-1.5 h-1.5 bg-blue-500 rounded-full" animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0 }} />
                    <motion.div className="w-1.5 h-1.5 bg-blue-500 rounded-full" animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0.2 }} />
                    <motion.div className="w-1.5 h-1.5 bg-blue-500 rounded-full" animate={{ y: [0, -5, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0.4 }} />
                  </div>
                  <span className="text-xs font-medium text-gray-400 animate-pulse">{loadingText}</span>
                </div>
              </div>
            </motion.div>
          )}
          <div ref={messagesEndRef} className="h-4" />
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 p-4 md:p-6 bg-gradient-to-t from-white via-white to-transparent pointer-events-none">
        <div className="max-w-4xl mx-auto pointer-events-auto bg-white/80 backdrop-blur-md rounded-3xl p-1 shadow-lg border border-gray-100">
          <form onSubmit={handleSubmit} className="relative flex items-center bg-white rounded-full shadow-sm border border-gray-200/60 focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-500/10 transition-all">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Ask a question about your documents..."
              className="w-full bg-transparent py-4 pl-6 pr-16 focus:outline-none text-gray-800 placeholder-gray-400"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="absolute right-2 p-2.5 rounded-full bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 transition-all shadow-sm"
            >
              <Send size={20} className={input.trim() && !isLoading ? 'translate-x-0.5' : ''} />
            </button>
          </form>
          <div className="text-center mt-2.5 mb-1">
            <p className="text-[10px] text-gray-400 font-medium">MediRAG AI can make mistakes. Verify critical information.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
