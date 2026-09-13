import React from 'react';
import { ChevronDown, Landmark } from 'lucide-react';
import CourtSelector from './CourtSelector';

export default function MobileSearchScope({ activeCodes, selectedCodes, onChange, disabled }) {
  return (
    <details className="mobile-module mobile-scope">
      <summary>
        <Landmark size={18} aria-hidden="true" />
        <span><strong>Onde pesquisar</strong><small>{selectedCodes.size} {selectedCodes.size === 1 ? 'tribunal selecionado' : 'tribunais selecionados'}</small></span>
        <ChevronDown className="module-chevron" size={18} aria-hidden="true" />
      </summary>
      <CourtSelector activeCodes={activeCodes} selectedCodes={selectedCodes} onChange={onChange} disabled={disabled} />
    </details>
  );
}
