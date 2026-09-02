import React, { useEffect } from 'react';
import { X, ExternalLink, Download, FileText, Scale } from 'lucide-react';

export default function PdfDrawer({ isOpen, onClose, pdfData }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !pdfData) return null;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className={`pdf-drawer ${isOpen ? 'open' : ''}`} aria-label="Visualizador de PDF do TJSP">
        <div className="drawer-header">
          <div className="drawer-title-group">
            <div className="drawer-icon-badge">
              <FileText size={18} />
            </div>
            <div>
              <strong className="drawer-process-title">{pdfData.title || 'Acórdão do TJSP'}</strong>
              <span className="drawer-chamber-subtitle">{pdfData.subtitle || 'Documento Oficial do Tribunal'}</span>
            </div>
          </div>

          <div className="drawer-header-actions">
            <a
              href={pdfData.url}
              target="_blank"
              rel="noreferrer"
              className="drawer-action-link"
              title="Abrir documento em nova aba"
            >
              <span>Abrir em Nova Aba</span>
              <ExternalLink size={13} />
            </a>

            <button 
              type="button" 
              className="drawer-close-btn" 
              onClick={onClose} 
              aria-label="Fechar visualizador"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="drawer-body">
          <iframe 
            src={pdfData.url} 
            title="Visualizador de Inteiro Teor TJSP" 
            className="pdf-iframe"
          />
        </div>
      </aside>
    </>
  );
}
