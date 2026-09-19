import { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { Trash2, X, UploadCloud, FileText, Loader2 } from 'lucide-react';

interface Document {
  id: number;
  filename: string;
  status: string;
}

export default function Sidebar({ onLogout, onClose }: { onLogout: () => void, onClose?: () => void }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchDocuments = async () => {
    try {
      const docs = await api.getDocuments();
      setDocuments(docs);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchDocuments();
    // Poll for status updates
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadProgress(0);
    
    // Simulate progress
    const progressInterval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + 10;
      });
    }, 200);

    try {
      await api.uploadDocument(file);
      setUploadProgress(100);
      await fetchDocuments();
    } catch (err: any) {
      console.error(err);
      alert(err?.message || "Failed to upload document");
    } finally {
      clearInterval(progressInterval);
      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress(0);
      }, 500);
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
          
          {isUploading && (
            <div className="w-full bg-slate-800 rounded-full h-1.5 mt-3 overflow-hidden">
              <div 
                className="bg-blue-500 h-1.5 rounded-full transition-all duration-300 ease-out" 
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>
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
              {documents.map(doc => (
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
                  <div className="flex items-center mt-2">
                    <span className={`h-2 w-2 rounded-full mr-2 ${doc.status === 'indexed' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : doc.status === 'processing' ? 'bg-amber-400 animate-pulse' : 'bg-red-400'}`}></span>
                    <span className="text-[11px] text-slate-400 uppercase tracking-wider font-medium">{doc.status}</span>
                  </div>
                </li>
              ))}
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
