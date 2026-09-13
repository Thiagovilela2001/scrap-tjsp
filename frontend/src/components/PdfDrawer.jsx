import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import React, { useEffect, useRef } from 'react';
import { X, ExternalLink, FileText } from 'lucide-react';

export default function PdfDrawer({ isOpen, onClose, pdfData }) {
  const closeButtonRef = useRef(null);
  const lastDocument = useRef(pdfData);
  useEffect(() => { if (pdfData) lastDocument.current = pdfData; }, [pdfData]);
  // Keep the document visible while the sheet finishes its closing transition.
  const documentData = pdfData || lastDocument.current;

  return (
    <Sheet open={isOpen && Boolean(pdfData)} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent className="pdf-drawer" showCloseButton={false} initialFocus={closeButtonRef}>
        <div className="drawer-header">
          <div className="drawer-title-group">
            <div className="drawer-icon-badge">
              <FileText size={18} />
            </div>
            <div>
              <SheetTitle className="drawer-process-title">{documentData?.title || 'Acórdão Oficial'}</SheetTitle>
              <SheetDescription className="drawer-chamber-subtitle">{documentData?.subtitle || 'Documento Oficial do Tribunal'}</SheetDescription>
            </div>
          </div>

          <div className="drawer-header-actions">
            <a
              href={documentData?.url}
              target="_blank"
              rel="noreferrer"
              className="drawer-action-link"
              title="Abrir documento em nova aba"
            >
              <span>Abrir em Nova Aba</span>
              <ExternalLink size={13} />
            </a>

            <Button variant="ghost" size="icon"
              type="button"
              className="drawer-close-btn"
              onClick={onClose}
              aria-label="Fechar visualizador"
              ref={closeButtonRef}
              tooltip={false}
            >
              <X size={18} />
            </Button>
          </div>
        </div>

        <div className="drawer-body">
          <iframe
            src={documentData?.url}
            title="Visualizador de Inteiro Teor"
            className="pdf-iframe"
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
