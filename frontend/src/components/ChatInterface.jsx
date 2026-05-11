import { useState, useEffect, useRef } from 'react';
import { Send, Bot, Edit3, BookOpen, ExternalLink, Loader2 } from 'lucide-react';
import { sendMessage, getMessages } from '../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

const StreamingCursor = () => (
  <span className="inline-block w-1.5 h-4 ml-1 bg-primary animate-pulse align-middle"></span>
);

const TypingIndicator = () => (
  <div className="flex gap-1.5 h-4 items-center justify-center">
    <span className="w-2 h-2 bg-primary rounded-full animate-bounce"></span>
    <span className="w-2 h-2 bg-primary rounded-full animate-bounce delay-75"></span>
    <span className="w-2 h-2 bg-primary rounded-full animate-bounce delay-150"></span>
  </div>
);

const ChatInterface = ({ sessionId, babyData, onEditBabyData }) => {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [isLoadingHistory, setIsLoadingHistory] = useState(false); 

    const messagesEndRef = useRef(null);

    useEffect(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

    // Parse sources dari content text
    const parseSourcesFromContent = (content) => {
        if (!content) return { content, sources: [] };
        
        const sourcesMatch = content.match(/\[SOURCES\]\s*(\[[\s\S]*?\])/);
        if (sourcesMatch) {
            try {
                const sources = JSON.parse(sourcesMatch[1]);
                const cleanContent = content.replace(/\[SOURCES\]\s*\[[\s\S]*?\]/, '').trim();
                return { content: cleanContent, sources };
            } catch (e) {
                console.error("Failed to parse sources from history:", e);
            }
        }
        return { content, sources: [] };
    };

    // LOAD HISTORY saat sessionId berubah atau mount
    const loadHistory = async () => {
        setIsLoadingHistory(true);
        try {
            const history = await getMessages(sessionId);
            // Format ulang & parse sources untuk setiap message
            const formatted = history.map((m, idx) => {
                const parsed = m.role === 'assistant' ? parseSourcesFromContent(m.content) : { content: m.content, sources: [] };
                return {
                    ...m,
                    id: m.id || `hist-${idx}`,
                    content: parsed.content,
                    sources: parsed.sources,
                    isStreaming: false
                };
            });
            setMessages(formatted);
        } catch (err) {
            console.error("Failed to load history:", err);
            setMessages([]);
        } finally {
            setIsLoadingHistory(false);
        }
    };

    useEffect(() => {
        if (!sessionId) {
            setMessages([]);
            return;
        }

        loadHistory();
    }, [sessionId]);

    const handleSend = async (text) => {
        if (!text.trim()) return;
        
        const userMsg = { role: 'user', content: text, id: Date.now() };
        const aiMsgId = Date.now() + 1;
        const assistantPlaceholder = { 
            role: 'assistant', 
            content: '', 
            id: aiMsgId, 
            sources: [],
            isStreaming: true 
        };

        setMessages(prev => [...prev, userMsg, assistantPlaceholder]);
        setInput('');
        setIsSending(true);

        try {
            const result = await sendMessage(sessionId, text, (chunk) => {
                setMessages(prev => 
                    prev.map(msg => msg.id === aiMsgId ? { ...msg, content: msg.content + chunk } : msg)
                );
            });

            // ✅ PARSE SOURCES dari response
            let content = result.response;
            let sources = result.sources || [];
            
            // Cek jika ada [SOURCES] di dalam text response
            const sourcesMatch = content.match(/\[SOURCES\]\s*(\[[\s\S]*?\])/);
            if (sourcesMatch) {
                try {
                    sources = JSON.parse(sourcesMatch[1]);
                    // Hapus [SOURCES]... dari content
                    content = content.replace(/\[SOURCES\]\s*\[[\s\S]*?\]/, '').trim();
                } catch (e) {
                    console.error("Failed to parse sources:", e);
                }
            }

            if (!content || content.length === 0) {
                setMessages(prev => prev.filter(msg => msg.id !== aiMsgId));
                return;
            }

            setMessages(prev => 
                prev.map(msg => 
                    msg.id === aiMsgId 
                    ? { ...msg, content, sources, isStreaming: false } 
                    : msg
                )
            );
            
        } catch (err) {
            console.error("Streaming error:", err);
            setMessages(prev => 
                prev.map(msg => 
                    msg.id === aiMsgId 
                    ? { ...msg, content: `❌ ${err.message}`, isStreaming: false } 
                    : msg
                )
            );
        } finally {
            setIsSending(false);
        }
    };

    const quickActions = ["Kapan mulai MPASI?", "Jadwal vaksinasi bayi", "Posisi menyusui yang benar", "Berat normal bayi 6 bulan"];

    // ✅ FIX: Preprocess markdown untuk cleanup karakter yang tidak perlu + nested bullets
    const preprocessMarkdown = (text) => {
        if (!text) return '';
        
        let processed = text;
        
        // =====================================================
        // ✅ BAGIAN 1: Regex Cleanup Markdown (Existing - Jangan Diubah)
        // =====================================================
        
        // ✅ Hapus #### yang muncul DI MANA SAJA
        processed = processed.replace(/####/g, '');
        
        // ✅ Handle kasus: "### **1." → "**1." (hapus ###, biarkan **)
        processed = processed.replace(/###\s*\*\*/g, '**');
        
        // ✅ Handle kasus: "****" → "**" (4 asterisks jadi 2)
        processed = processed.replace(/\*\*\*\*/g, '**');
        
        // ✅ Handle 5+ asterisks → "**"
        processed = processed.replace(/\*{5,}/g, '**');
        
        // ✅ Handle "###" tanpa asterisk → "**"
        processed = processed.replace(/###\s*/g, '**');
        
        // ✅ Handle "##" → "**"
        processed = processed.replace(/##\s*/g, '**');
        
        // ✅ Handle "#" di awal baris → "**"
        processed = processed.replace(/^#\s*/gm, '**');
        
        // ✅ Pastikan ada line break sebelum "---"
        processed = processed.replace(/\s*---+\s*/g, '\n\n---\n\n');
        
        // ✅ Pastikan bullet points "-" yang INLINE pindah ke baris baru
        processed = processed.replace(/([.!)]\s*)-\s+/g, '$1\n- ');
        
        // ✅ Pastikan "-" yang berdiri sendiri sebagai bullet punya line break sebelumnya
        processed = processed.replace(/([a-zA-Z0-9)]\s)-\s/g, '$1\n\n- ');
        
        // ✅ Handle pattern "- **text**:" agar jadi list yang rapi
        processed = processed.replace(/-\s+\*\*([^*]+)\*\*:/g, '\n- **$1**:');
        
        // ✅ Tambah line break sebelum numbered list yang bold
        processed = processed.replace(/\*\*(\d+\.\s)/g, '\n\n**$1');
        
        // ✅ Pastikan list items dimulai di baris baru (existing logic)
        processed = processed.replace(/([^\n])\n(\s*[-*]\s+)/g, '$1\n\n$2');
        processed = processed.replace(/([^\n])\n(\s*\d+\.\s+)/g, '$1\n\n$2');
        
        // ✅ Bersihkan backticks
        processed = processed.replace(/`{3,}/g, '');
        
        // ✅ Bersihkan multiple newlines
        processed = processed.replace(/\n{3,}/g, '\n\n');
        
        // ✅ Tambah line break setelah bold section headers
        processed = processed.replace(/\*\*([^*]+)\*\*\n(?!\n)/g, '**$1**\n\n');
        
        // =====================================================
        // ✅ BAGIAN 2: Auto-Indent Nested Bullets (Logic Baru)
        // =====================================================
        
        const lines = processed.split('\n');
        const result = [];
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();
            const isBullet = trimmed.startsWith('-');
            
            if (isBullet) {
                const prevLine = result.length > 0 ? result[result.length - 1].trim() : '';
                const prevIsBullet = prevLine.startsWith('-');
                const prevEndsWithColon = prevLine.endsWith(':');
                
                // ✅ Jika bullet sebelumnya adalah bullet DAN berakhir dengan ":" → ini sub-bullet
                if (prevIsBullet && prevEndsWithColon) {
                    // Hitung indent level dari parent + 2 spasi
                    const parentIndent = prevLine.match(/^(\s*)-/)?.[1]?.length || 0;
                    const newIndent = ' '.repeat(parentIndent + 2);
                    result.push(newIndent + trimmed);
                    continue;
                }
                
                // ✅ Jika bullet sebelumnya sudah di-indent → pertahankan sebagai sibling sub-bullet
                if (prevIsBullet && prevLine.startsWith('  ')) {
                    const prevIndent = prevLine.match(/^(\s*)-/)?.[1]?.length || 0;
                    result.push(' '.repeat(prevIndent) + trimmed);
                    continue;
                }
            }
            
            // ✅ Bukan nested bullet → tambahkan seperti biasa
            result.push(line);
        }
        
        processed = result.join('\n');
        
        return processed;
    };

    return (
        <div className="flex flex-col h-full bg-bg-main">
            <header className="h-16 border-b border-border p-6 flex items-center justify-between bg-bg-main/80 backdrop-blur-sm z-10">
                <div className="flex items-center gap-2">
                <h1 className="font-bold text-lg text-text-main">ParentEase AI</h1>
                <span className="text-xs bg-green-100 text-green-600 px-2 py-0.5 rounded-full font-medium">Online</span>
                </div>
                <button onClick={onEditBabyData} className="flex items-center gap-2 px-3 py-1.5 text-sm text-primary border border-primary-border rounded-lg hover:bg-primary-light transition">
                <Edit3 className="w-4 h-4" /> Edit Data Anak Saya
                </button>
            </header>

            <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent">
                {isLoadingHistory ? (
                    <div className="h-full flex flex-col items-center justify-center text-text-muted">
                        <Loader2 className="w-8 h-8 animate-spin mb-3" />
                        <p>Memuat riwayat chat...</p>
                    </div>
                ) : (
                    <div>
                        {messages.length === 0 ? (
                            <div className="h-full flex flex-col items-center justify-center text-center pb-20">
                                <div className="w-16 h-16 bg-primary-light rounded-full flex items-center justify-center mb-6 shadow-sm">
                                <Bot className="w-8 h-8 text-primary" />
                                </div>
                                <h2 className="text-2xl font-bold text-text-main mb-2">Halo! Ada yang bisa dibantu?</h2>
                                <p className="text-text-muted max-w-md mb-8">Tanyakan seputar ASI, MPASI, vaksinasi, atau tumbuh kembang si kecil.</p>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 w-full max-w-3xl">
                                {quickActions.map((action, idx) => (
                                    <button key={idx} onClick={() => handleSend(action)} className="bg-bg-main border border-border text-text-main px-4 py-3 rounded-xl hover:border-primary-border hover:text-primary hover:shadow-sm transition text-sm font-medium">
                                    {action}
                                    </button>
                                ))}
                                </div>
                            </div>
                        ) : (
                            <div className="max-w-3xl mx-auto space-y-6">
                                {messages.map((msg) => (
                                <div key={msg.id} className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                                    {msg.role === 'assistant' && (
                                    <div className="w-8 h-8 bg-primary-light rounded-full flex-shrink-0 flex items-center justify-center mt-1 shadow-sm">
                                        <Bot className="w-4 h-4 text-primary" />
                                    </div>
                                    )}
                                    <div className="max-w-[85%] min-w-[100px]">
                                    <div className={`p-4 rounded-2xl text-sm leading-relaxed shadow-sm relative ${
                                        msg.role === 'user' ? 'bg-primary text-white rounded-br-none' : 'bg-bg-tertiary text-text-main rounded-bl-none border border-border'
                                    }`}>
                                        {msg.role === 'assistant' ? (
                                        <>
                                            {!msg.content && msg.isStreaming ? (
                                            <TypingIndicator />
                                            ) : (
                                            <>
                                                {msg.isStreaming ? (
                                                <>
                                                    <span className="whitespace-pre-wrap">{msg.content}</span>
                                                    <StreamingCursor />
                                                </>
                                                ) : (
                                                <div className="markdown-content prose prose-sm max-w-none">
                                                    <ReactMarkdown 
                                                        remarkPlugins={[remarkGfm, remarkBreaks]}
                                                        components={{
                                                            p: ({node, ...props}) => <p className="mb-3 last:mb-0 leading-relaxed" {...props} />,
                                                            ul: ({node, ...props}) => <ul className="list-disc pl-5 mb-3 space-y-1 marker:text-primary" {...props} />,
                                                            ol: ({node, ...props}) => <ol className="list-decimal pl-5 mb-3 space-y-1 marker:text-primary marker:font-semibold" {...props} />,
                                                            li: ({node, ...props}) => <li className="ml-1 leading-relaxed pl-1" {...props} />,
                                                            strong: ({node, ...props}) => <strong className="font-semibold text-text-main" {...props} />,
                                                            em: ({node, ...props}) => <em className="italic text-text-main" {...props} />,
                                                            h1: ({node, ...props}) => <h1 className="text-lg font-bold mt-4 mb-2 text-text-main" {...props} />,
                                                            h2: ({node, ...props}) => <h2 className="text-base font-bold mt-3 mb-2 text-text-main" {...props} />,
                                                            h3: ({node, ...props}) => <h3 className="text-base font-semibold mt-3 mb-2 text-text-main" {...props} />,
                                                            hr: ({node, ...props}) => <hr className="my-3 border-border opacity-30" {...props} />,
                                                            blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-primary pl-3 italic my-2 text-text-muted" {...props} />,
                                                            code: ({node, inline, ...props}) => 
                                                                inline ? 
                                                                <code className="bg-bg-main px-1.5 py-0.5 rounded text-xs font-mono text-primary" {...props} /> :
                                                                <code className="block bg-bg-main p-2 rounded my-2 text-xs font-mono text-primary overflow-x-auto" {...props} />,
                                                        }}
                                                    >
                                                        {preprocessMarkdown(msg.content)}
                                                    </ReactMarkdown>
                                                </div>
                                                )}
                                            </>
                                            )}
                                        </>
                                        ) : msg.content}
                                    </div>

                                    {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                                        <div className="mt-3 ml-1">
                                        <div className="flex items-center gap-1.5 text-xs text-text-muted mb-2 px-1">
                                            <BookOpen className="w-3.5 h-3.5" />
                                            <span className="font-semibold">Referensi:</span>
                                        </div>
                                        <div className="space-y-2">
                                            {msg.sources.map((source, sIdx) => (
                                            <div key={sIdx} className="flex items-center gap-3 px-3 py-2 bg-bg-main rounded-lg border border-border hover:border-primary/30 transition shadow-sm group">
                                                <div className="w-8 h-8 bg-primary/10 rounded-md flex items-center justify-center flex-shrink-0">
                                                <BookOpen className="w-4 h-4 text-primary" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                <p className="text-xs font-semibold text-text-main truncate group-hover:text-primary transition">
                                                    {source.title || "Medical Guideline"}
                                                </p>
                                                {source.page && <p className="text-[10px] text-text-muted">Halaman {source.page}</p>}
                                                </div>
                                                {source.url && (
                                                <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-text-light hover:text-primary transition p-1 rounded-full hover:bg-primary-light">
                                                    <ExternalLink className="w-4 h-4" />
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
                                <div ref={messagesEndRef} />
                            </div>
                        )}
                    </div>
                )}
            </div>

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
                        disabled={isSending}
                    />
                    <button 
                        type="submit" 
                        disabled={!input.trim() || isSending}
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