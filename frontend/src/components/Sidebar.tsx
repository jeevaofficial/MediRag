import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../services/api';
import { Trash2, X, UploadCloud, FileText, Loader2 } from 'lucide-react';

interface Document {
  id: number;
  filename: string;
  status: string;
  processing_progress?: number;
  processing_error?: string | null;
}

const normalizeStatus = (status?: string) => {
  const value = (status || '').toLowerCase();
  if (value === 'completed') return 'COMPLETED';
  if (value === 'indexed') return 'INDEXED';
  if (value === 'failed' || value === 'error') return 'FAILED';
  if (value === 'processing') return 'PROCESSING';
  if (value === 'uploaded') return 'UPLOADED';
  return (status || 'UPLOADED').toUpperCase();
};

export default function Sidebar({ onLogout, onClose }: { onLogout: () => void, onClose?: () => void }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isFetchingRef = useRef(false);

  const fetchDocuments = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const docs = await api.getDocuments();
      setDocuments(docs);
      setUploadError('');
    } catch (e) {
      console.error(e);
      setUploadError(e instanceof Error ? e.message : 'Could not refresh document status.');
    } finally {
      isFetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    if (!documents.some(doc => ['uploaded', 'processing'].includes(doc.status.toLowerCase()))) return;
    const interval = window.setInterval(() => void fetchDocuments(), 5000);
    return () => clearInterval(interval);
  }, [documents, fetchDocuments]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf')) {
      setUploadError('Only PDF files are supported. Convert DOCX files to PDF before uploading.');
      e.target.value = '';
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setUploadError('The PDF is larger than the 25 MB upload limit.');
      e.target.value = '';
      return;
    }

    setIsUploading(true);
    setUploadError('');

    try {
      await api.uploadDocument(file);
      await fetchDocuments();
    } catch (err: any) {
      console.error(err);
      setUploadError(err?.message || "Failed to upload document");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteDocument = async (id: number) => {
    if (!confirm("Are you sure you want to delete this document?")) return;
    try {
      await api.deleteDocument(id);
      await fetchDocuments();
    } catch (err: any) {
      alert(err.message || "Failed to delete document");
    }
  };

  const handleRetryDocument = async (id: number) => {
    try {
      await api.retryDocument(id);
      await fetchDocuments();
    } catch (err: any) {
      alert(err.message || "Failed to retry document");
    }
  };

  return (
    <div className="w-64 bg-slate-900 text-white flex flex-col h-full shadow-2xl z-10 w-full md:w-64">
      <div className="p-4 bg-slate-950 flex justify-between items-center border-b border-slate-800">
        <div>
          <h1 className="text-xl font-bold tracking-wider text-blue-400">MediRAG AI</h1>
          <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-widest">Trusted Medical Ref</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="md:hidden text-slate-400 hover:text-white p-1">
            <X size={20} />
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-6">
        <div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="w-full flex items-center justify-center py-2.5 px-4 border border-blue-500/30 text-sm font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 focus:ring-blue-500 disabled:opacity-50 transition-all shadow-lg hover:shadow-blue-500/20 gap-2"
          >
            {isUploading ? <Loader2 size={16} className="animate-spin" /> : <UploadCloud size={16} />}
            {isUploading ? "Uploading..." : "Upload PDF"}
          </button>
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept=".pdf"
            onChange={handleFileUpload}
          />
          
          {uploadError && (
            <p role="alert" className="mt-2 text-xs text-red-300 break-words">{uploadError}</p>
          )}

        </div>

        <div className="flex-1 flex flex-col">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
            <FileText size={14} /> Knowledge Base
          </h2>
          {documents.length === 0 ? (
            <div className="text-sm text-slate-500 flex flex-col items-center justify-center py-8 text-center bg-slate-800/30 rounded-xl border border-slate-800 border-dashed">
              <FileText size={24} className="mb-2 opacity-50" />
              <p>No documents yet.</p>
              <p className="text-xs mt-1 opacity-70">Upload a PDF to get started.</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {documents.map(doc => {
                const normalizedStatus = normalizeStatus(doc.status);
                const isFailed = normalizedStatus === 'FAILED';
                const progress = normalizedStatus === 'COMPLETED' || normalizedStatus === 'INDEXED'
                  ? 100
                  : Math.max(0, Math.min(99, doc.processing_progress ?? 0));
                const isProcessing = normalizedStatus === 'PROCESSING' || normalizedStatus === 'UPLOADED';
                return (
                  <li key={doc.id} className="flex flex-col bg-slate-800/80 hover:bg-slate-800 p-3 rounded-xl border border-slate-700/50 transition-colors group">
                    <div className="flex justify-between items-start">
                      <span className="text-sm truncate font-medium text-slate-200 pr-2" title={doc.filename}>
                        {doc.filename}
                      </span>
                      <button 
                        onClick={() => handleDeleteDocument(doc.id)}
                        className="text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity p-0.5"
                        title="Delete document"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="flex items-center mt-2 justify-between gap-2">
                      <div className="flex items-center min-w-0">
                        <span className={`h-2 w-2 rounded-full mr-2 ${normalizedStatus === 'COMPLETED' || normalizedStatus === 'INDEXED' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : isProcessing ? 'bg-amber-400 animate-pulse' : normalizedStatus === 'FAILED' ? 'bg-red-400' : 'bg-slate-400'}`}></span>
                        <span className="text-[11px] text-slate-400 uppercase tracking-wider font-medium">
                          {normalizedStatus} · {progress}%
                        </span>
                      </div>
                      {isFailed && (
                        <button
                          onClick={() => handleRetryDocument(doc.id)}
                          className="text-[10px] text-amber-300 border border-amber-500/40 rounded px-1.5 py-0.5 hover:bg-amber-500/10"
                        >
                          Retry
                        </button>
                      )}
                    </div>
                    {(isProcessing || normalizedStatus === 'COMPLETED' || normalizedStatus === 'INDEXED') && (
                      <div
                        className="w-full bg-slate-700 rounded-full h-1.5 mt-2 overflow-hidden"
                        role="progressbar"
                        aria-label={`${doc.filename} indexing progress`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={progress}
                      >
                        <div
                          className={`h-full rounded-full transition-all duration-500 ease-out ${normalizedStatus === 'COMPLETED' || normalizedStatus === 'INDEXED' ? 'bg-emerald-400' : 'bg-blue-400'}`}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    )}
                    {isFailed && doc.processing_error && (
                      <p className="mt-2 text-[10px] text-red-300 break-words">{doc.processing_error}</p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      <div className="p-4 bg-slate-900 border-t border-slate-800">
        <button
          onClick={onLogout}
          className="w-full flex justify-center py-2 px-4 border border-slate-700 text-sm font-medium rounded-md text-slate-300 hover:bg-slate-800 focus:outline-none transition-colors"
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
