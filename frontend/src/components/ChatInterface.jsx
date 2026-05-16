import { useState, useEffect, useRef } from 'react';
import { Send, Edit3, BookOpen, ExternalLink, Loader2, Paperclip, FileText, X } from 'lucide-react';
import { sendMessage, getMessages, uploadPDF } from '../services/api';
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

const ParentEaseMascot = ({ className = "h-20 w-20" }) => (
  <svg
    viewBox="0 0 72 72"
    aria-hidden="true"
    className={`${className} drop-shadow-sm`}
    fill="none"
  >
    <line x1="36" y1="13" x2="36" y2="20" stroke="#347FA8" strokeWidth="3.2" strokeLinecap="round" />
    <circle cx="36" cy="10" r="4" fill="#BDEFE2" stroke="#347FA8" strokeWidth="2.4" />
    <rect x="14" y="35" width="7" height="12" rx="3.5" fill="#6BAED6" />
    <rect x="51" y="35" width="7" height="12" rx="3.5" fill="#6BAED6" />
    <rect x="18" y="24" width="36" height="30" rx="10" fill="#72C9C3" />
    <path
      d="M25 25.5h22c2.7 0 5 2.2 5 5v2.2C48.3 30.2 42.7 29 36 29s-12.3 1.2-16 3.7v-2.2c0-2.8 2.2-5 5-5Z"
      fill="#AEE8DD"
    />
    <rect x="24" y="31" width="24" height="17" rx="5.5" fill="#F8FCFF" />
    <circle cx="30.2" cy="38.1" r="2.5" fill="#172033" />
    <circle cx="41.8" cy="38.1" r="2.5" fill="#172033" />
    <path d="M32.8 43h6.4" stroke="#172033" strokeWidth="2.3" strokeLinecap="round" />
    <rect x="24" y="54" width="24" height="8" rx="4" fill="#BDEFE2" />
    <path d="M30.5 58h11" stroke="#4F9FC8" strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

const ChatInterface = ({ sessionId, babyData, onEditBabyData }) => {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [isLoadingHistory, setIsLoadingHistory] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);

    const messagesEndRef = useRef(null);
    const fileInputRef = useRef(null);

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

    const handleFileSelect = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('Hanya file PDF yang diterima.');
            return;
        }
        if (file.size > 20 * 1024 * 1024) {
            alert('Ukuran file maksimal 20 MB.');
            return;
        }
        setSelectedFile(file);
        // Reset the input so the same file can be re-selected
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleRemoveFile = () => {
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleSend = async (text) => {
        const hasText = text && text.trim();
        const hasFile = !!selectedFile;
        if (!hasText && !hasFile) return;
        
        const displayText = hasFile
            ? (hasText ? `${text}\n📎 ${selectedFile.name}` : `📎 Upload PDF: ${selectedFile.name}`)
            : text;
        const userMsg = { role: 'user', content: displayText, id: Date.now() };
        const aiMsgId = Date.now() + 1;
        const assistantPlaceholder = { 
            role: 'assistant', 
            content: '', 
            id: aiMsgId, 
            sources: [],
            isStreaming: true 
        };

        const fileToUpload = selectedFile;
        setMessages(prev => [...prev, userMsg, assistantPlaceholder]);
        setInput('');
        setSelectedFile(null);
        setIsSending(true);

        try {
            let result;
            const onChunk = (chunk) => {
                setMessages(prev => 
                    prev.map(msg => msg.id === aiMsgId ? { ...msg, content: msg.content + chunk } : msg)
                );
            };

            if (fileToUpload) {
                result = await uploadPDF(sessionId, fileToUpload, hasText ? text : null, onChunk);
            } else {
                result = await sendMessage(sessionId, text, onChunk);
            }

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
                setMessages(prev =>
                    prev.map(msg =>
                        msg.id === aiMsgId
                        ? {
                            ...msg,
                            content: 'Respons kosong dari server. Coba kirim ulang pertanyaan atau cek terminal backend.',
                            sources: [],
                            isStreaming: false
                        }
                        : msg
                    )
                );
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
        <div className="liquid-panel-strong flex h-full min-h-0 flex-col overflow-hidden rounded-xl">
            <header className="z-10 flex min-h-16 items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
                <div className="min-w-0">
                <div className="flex items-center gap-2">
                    <h1 className="truncate text-base font-bold text-text-main sm:text-lg">ParentEase AI</h1>
                    <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-600">Online</span>
                </div>
                <p className="hidden text-xs text-text-muted sm:block">ASI, MPASI, vaksinasi, tumbuh kembang, dan dokumen KIA.</p>
                </div>
                <button onClick={onEditBabyData} className="flex shrink-0 items-center gap-2 rounded-lg border border-primary-border bg-primary-light px-3 py-2 text-sm text-primary transition hover:bg-primary/15">
                <Edit3 className="w-4 h-4" /> <span className="hidden sm:inline">Edit Data Anak</span>
                </button>
            </header>

            <div className="glass-scrollbar min-h-0 flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-6">
                {isLoadingHistory ? (
                    <div className="h-full flex flex-col items-center justify-center text-text-muted">
                        <Loader2 className="w-8 h-8 animate-spin mb-3" />
                        <p>Memuat riwayat chat...</p>
                    </div>
                ) : (
                    <div>
                        {messages.length === 0 ? (
                            <div className="mx-auto flex min-h-[62vh] max-w-4xl flex-col items-center justify-center pb-16 text-center">
                                <div className="relative mb-6 flex h-28 w-24 items-center justify-center">
                                <div className="mascot-float">
                                    <ParentEaseMascot />
                                </div>
                                <div className="mascot-float-shadow absolute bottom-2 h-2 w-12 rounded-full bg-primary/35 blur-sm" />
                                </div>
                                <h2 className="mb-2 text-xl font-bold text-text-main sm:text-2xl">Halo, ada yang bisa dibantu?</h2>
                                <p className="mb-8 max-w-md text-sm text-text-muted sm:text-base">Tanyakan seputar ASI, MPASI, vaksinasi, tumbuh kembang, atau upload PDF Buku KIA.</p>
                                <div className="grid w-full max-w-3xl grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                                {quickActions.map((action, idx) => (
                                    <button key={idx} onClick={() => handleSend(action)} className="rounded-lg border border-border bg-bg-tertiary px-4 py-3 text-sm font-medium text-text-main shadow-sm transition hover:border-primary-border hover:text-primary">
                                    {action}
                                    </button>
                                ))}
                                </div>
                            </div>
                        ) : (
                            <div className="mx-auto max-w-4xl space-y-5">
                                {messages.map((msg) => (
                                <div key={msg.id} className={`flex gap-3 sm:gap-4 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                                    {msg.role === 'assistant' && (
                                    <div className="mt-1 flex h-9 w-9 flex-shrink-0 items-center justify-center">
                                        <ParentEaseMascot className="h-9 w-9" />
                                    </div>
                                    )}
                                    <div className="min-w-[100px] max-w-[92%] sm:max-w-[84%]">
                                    <div className={`relative rounded-xl p-4 text-sm leading-relaxed shadow-sm ${
                                        msg.role === 'user' ? 'bg-primary text-white' : 'border border-border bg-bg-tertiary text-text-main'
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
                                            <div key={sIdx} className="group flex items-center gap-3 rounded-lg border border-border bg-bg-main px-3 py-2 shadow-sm transition hover:border-primary/30">
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

            <div className="border-t border-border bg-bg-main/60 p-3 sm:p-4">
                <div className="mx-auto max-w-4xl">
                {selectedFile && (
                    <div className="mb-2 flex items-center gap-2 px-1">
                        <div className="flex max-w-full items-center gap-2 rounded-lg border border-primary/20 bg-primary/10 px-3 py-1.5 text-sm">
                            <FileText className="w-4 h-4 text-primary flex-shrink-0" />
                            <span className="max-w-[48vw] truncate text-text-main sm:max-w-[320px]">{selectedFile.name}</span>
                            <span className="hidden text-xs text-text-muted sm:inline">({(selectedFile.size / 1024).toFixed(0)} KB)</span>
                            <button
                                type="button"
                                onClick={handleRemoveFile}
                                className="ml-1 p-0.5 rounded-full hover:bg-red-100 text-text-muted hover:text-red-500 transition"
                            >
                                <X className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    </div>
                )}
                <form onSubmit={(e) => { e.preventDefault(); handleSend(input); }}>
                    <div className="flex items-center rounded-xl border border-border bg-bg-tertiary px-3 py-2 shadow-sm transition focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 sm:px-4">
                    <input
                        type="file"
                        ref={fileInputRef}
                        accept=".pdf"
                        onChange={handleFileSelect}
                        className="hidden"
                    />
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={isSending}
                        title="Upload PDF (KMS, Posyandu, dll)"
                        className="mr-2 p-2 rounded-lg text-text-muted hover:text-primary hover:bg-primary/10 disabled:opacity-50 disabled:cursor-not-allowed transition"
                    >
                        <Paperclip className="w-5 h-5" />
                    </button>
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={selectedFile ? "Tambahkan pesan (opsional)..." : "Tanya seputar ASI, MPASI, tumbuh kembang..."}
                        className="min-w-0 flex-1 border-none bg-transparent py-2 text-text-main placeholder-text-light focus:outline-none"
                        disabled={isSending}
                    />
                    <button 
                        type="submit" 
                        disabled={(!input.trim() && !selectedFile) || isSending}
                        className="ml-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-white shadow-sm transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
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
