import React, { useEffect, useRef } from 'react';
import { X, ExternalLink, FileText } from 'lucide-react';

export default function PdfDrawer({ isOpen, onClose, pdfData }) {
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    const previousFocus = document.activeElement;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    closeButtonRef.current?.focus();
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus?.();
    };
  }, [isOpen, onClose]);

  if (!isOpen || !pdfData) return null;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className={`pdf-drawer ${isOpen ? 'open' : ''}`} role="dialog" aria-modal="true" aria-labelledby="pdf-title">
        <div className="drawer-header">
          <div className="drawer-title-group">
            <div className="drawer-icon-badge">
              <FileText size={18} />
            </div>
            <div>
              <strong id="pdf-title" className="drawer-process-title">{pdfData.title || 'Acórdão Oficial'}</strong>
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
              ref={closeButtonRef}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="drawer-body">
          <iframe 
            src={pdfData.url} 
            title="Visualizador de Inteiro Teor" 
            className="pdf-iframe"
          />
        </div>
      </aside>
    </>
  );
}
