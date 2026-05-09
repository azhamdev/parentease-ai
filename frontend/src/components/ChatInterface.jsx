import { useState, useEffect, useRef } from 'react';
import { Send, Bot, Edit3 } from 'lucide-react';
import { sendMessage } from '../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BookOpen, ExternalLink } from 'lucide-react';

const ChatInterface = ({ sessionId, babyData, onEditBabyData }) => {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    useEffect(scrollToBottom, [messages]);

    const handleSend = async (text) => {
        if (!text.trim()) return;
        
        const userMsg = { role: 'user', content: text };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            const data = await sendMessage(sessionId, text);

            const aiMsg = { 
            role: 'assistant', 
            content: data.response,
            sources: data.sources  // Simpan sources
            };
            setMessages(prev => [...prev, aiMsg]);
            
        } catch (err) {
            setMessages(prev => [...prev, { 
            role: 'assistant', 
            content: '❌ Maaf, terjadi kesalahan.',
            sources: []
            }]);
        } finally {
            setLoading(false);
        }
    };

    const quickActions = [
        "Kapan mulai MPASI?",
        "Jadwal vaksinasi bayi",
        "Posisi menyusui yang benar",
        "Berat normal bayi 6 bulan"
    ];

    return (
        <div className="flex flex-col h-full bg-bg-main">
        {/* Header */}
        <header className="h-16 border-b border-border px-6 flex items-center justify-between bg-bg-main/80 backdrop-blur-sm">
            <div className="flex items-center gap-2">
            <h1 className="font-bold text-lg text-text-main">ParentEase AI</h1>
            <span className="text-xs bg-green-100 text-green-600 px-2 py-0.5 rounded-full font-medium">
                Online
            </span>
            </div>
            <button 
            onClick={onEditBabyData}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-primary border border-primary-border rounded-lg hover:bg-primary-light transition"
            >
            <Edit3 className="w-4 h-4" />
            Edit Data Anak Saya
            </button>
        </header>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-6">
            {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center pb-20">
                <div className="w-16 h-16 bg-primary-light rounded-full flex items-center justify-center mb-6 shadow-sm">
                <Bot className="w-8 h-8 text-primary" />
                </div>
                <h2 className="text-2xl font-bold text-text-main mb-2">Halo! Ada yang bisa dibantu?</h2>
                <p className="text-text-muted max-w-md mb-8">
                Tanyakan seputar ASI, MPASI, vaksinasi, atau tumbuh kembang si kecil.
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full max-w-3xl">
                {quickActions.map((action, idx) => (
                    <button 
                    key={idx} 
                    onClick={() => handleSend(action)}
                    className="bg-bg-main border border-border text-text-main px-4 py-3 rounded-xl hover:border-primary-border hover:text-primary hover:shadow-sm transition text-sm font-medium"
                    >
                    {action}
                    </button>
                ))}
                </div>
            </div>
            ) : (
            <div className="max-w-3xl mx-auto space-y-6">
                {messages.map((msg, idx) => (
                    <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                        {msg.role === 'assistant' && (
                        <div className="w-8 h-8 bg-primary-light rounded-full flex-shrink-0 flex items-center justify-center mt-1">
                            <Bot className="w-4 h-4 text-primary" />
                        </div>
                        )}
                        <div className="max-w-[80%]">
                        {/* Message Bubble */}
                        <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm ${
                            msg.role === 'user' 
                            ? 'bg-primary text-white rounded-br-none' 
                            : 'bg-bg-tertiary text-text-main rounded-bl-none border border-border'
                        }`}>
                            {msg.role === 'assistant' ? (
                            <ReactMarkdown 
                                remarkPlugins={[remarkGfm]}
                                components={{
                                strong: ({node, ...props}) => (
                                    <strong className="font-semibold text-text-main" {...props} />
                                ),
                                em: ({node, ...props}) => (
                                    <em className="italic" {...props} />
                                ),
                                p: ({node, ...props}) => (
                                    <p className="inline" {...props} />
                                ),
                                }}
                            >
                                {msg.content}
                            </ReactMarkdown>
                            ) : (
                            msg.content
                            )}
                        </div>

                        {/*  Sources Section - Tampilkan jika ada sources */}
                        {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                            <div className="mt-2 ml-1">
                            <div className="flex items-center gap-1.5 text-xs text-text-muted mb-2">
                                <BookOpen className="w-3.5 h-3.5" />
                                <span className="font-medium">Referensi:</span>
                            </div>
                            <div className="space-y-1.5">
                                {msg.sources.map((source, sIdx) => (
                                <div 
                                    key={sIdx}
                                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:border-primary/30 transition shadow-sm"
                                >
                                    <BookOpen className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                                    <div className="flex-1 min-w-0">
                                    <p className="text-xs font-medium text-text-main truncate">
                                        {source.title}
                                    </p>
                                    {source.page && (
                                        <p className="text-[10px] text-text-muted">
                                        Halaman {source.page}
                                        </p>
                                    )}
                                    </div>
                                    {source.url && (
                                    <a 
                                        href={source.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-primary hover:text-primary-hover transition"
                                    >
                                        <ExternalLink className="w-3.5 h-3.5" />
                                    </a>
                                    )}
                                </div>
                                ))}
                            </div>
                            </div>
                        )}
                        </div>
                    </div>
                ))}
                {loading && (
                    <div className="flex gap-3 items-end">
                        {/* Avatar Bot */}
                        <div className="w-8 h-8 bg-primary-light rounded-full flex-shrink-0 flex items-center justify-center mt-1">
                        <Bot className="w-4 h-4 text-primary" />
                        </div>
                        
                        {/* Bubble Animasi */}
                        <div className="bg-bg-tertiary px-4 py-3 rounded-2xl rounded-bl-none border border-border shadow-sm flex items-center gap-3">
                            <div className="flex gap-1.5">
                                <span className="w-2 h-2 bg-primary rounded-full animate-bounce"></span>
                                <span className="w-2 h-2 bg-primary rounded-full animate-bounce delay-75"></span>
                                <span className="w-2 h-2 bg-primary rounded-full animate-bounce delay-150"></span>
                            </div>
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>
            )}
        </div>

        {/* Input */}
        <div className="p-4 bg-bg-main border-t border-border">
            <div className="max-w-3xl mx-auto">
            <form onSubmit={(e) => { e.preventDefault(); handleSend(input); }}>
                <div className="flex items-center bg-bg-tertiary border border-border rounded-2xl px-4 py-2 focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary transition shadow-sm">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Tanya seputar ASI, MPASI, tumbuh kembang..."
                    className="flex-1 bg-transparent border-none focus:outline-none text-text-main placeholder-text-light py-2"
                />
                <button 
                    type="submit" 
                    disabled={!input.trim() || loading}
                    className="ml-2 w-10 h-10 bg-primary text-white rounded-xl hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center transition shadow-sm"
                >
                    <Send className="w-5 h-5" />
                </button>
                </div>
            </form>
            </div>
        </div>
        </div>
    );
};

export default ChatInterface;