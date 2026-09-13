// @vitest-environment jsdom
import React, { useState } from 'react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TooltipProvider } from '../ui/tooltip';
import PdfDrawer from '../PdfDrawer';
import SemanticClarificationModal from '../SemanticClarificationModal';
import DraftingCanvas from '../DraftingCanvas';
import CourtSelector from '../CourtSelector';
import DecisionCard from '../DecisionCard';
import { toast } from 'sonner';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// Floating popup geometry is browser-only. Keep real triggers and focus behavior.
vi.mock('../ui/tooltip', async (importOriginal) => ({
  ...await importOriginal(),
  TooltipContent: () => null,
}));

beforeAll(() => {
  window.PointerEvent = class extends MouseEvent {};
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 100, 32));
  // jsdom has no layout; tabbable needs non-empty rects for visible controls.
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(function () {
    return this.closest('[hidden]') ? [] : [new DOMRect(0, 0, 100, 32)];
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });

function setup(ui) {
  const user = userEvent.setup();
  render(<TooltipProvider delay={0}>{ui}</TooltipProvider>);
  return user;
}

describe('Shadcn integration', () => {
  it.each([
    ['PDF', PdfDrawer, { pdfData: { url: 'about:blank', title: 'Acórdão de teste' } }, 'Acórdão de teste', 'Fechar visualizador'],
    ['semantic form', SemanticClarificationModal, { onApplyAndSearch() {} }, 'Delimitar pesquisa', 'Fechar formulário semântico'],
    ['draft editor', DraftingCanvas, { draft: 'Minuta de teste', setDraft() {}, selectedDecisions: [] }, 'Mesa de Redação', 'Fechar editor de minuta'],
  ])('%s traps focus, closes on Escape and returns focus', async (_, Component, props, name, closeName) => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>Abrir</button><Component {...props} isOpen={open} onClose={() => setOpen(false)} /></>;
    }
    const user = setup(<Harness />);
    const opener = screen.getByRole('button', { name: 'Abrir' });
    await user.click(opener);
    const dialog = await screen.findByRole('dialog', { name });
    await waitFor(() => expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: closeName })));
    const buttons = within(dialog).getAllByRole('button');
    for (let i = 0; i < buttons.length + 4; i += 1) {
      await user.tab();
      await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    }
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it('switches court tabs by keyboard and preserves selection while blocking unavailable courts', async () => {
    function Harness() {
      const [selected, setSelected] = useState(new Set(['tjsp']));
      return <CourtSelector activeCodes={new Set(['tjsp', 'stj'])} selectedCodes={selected} onChange={setSelected} />;
    }
    const user = setup(<Harness />);
    const selected = screen.getByRole('checkbox', { name: /TJSP/ });
    expect(selected.getAttribute('aria-checked')).toBe('true');
    await user.click(selected);
    expect(selected.getAttribute('aria-checked')).toBe('false');
    await user.click(screen.getByText('São Paulo'));
    expect(selected.getAttribute('aria-checked')).toBe('true');
    const unavailable = screen.getByRole('checkbox', { name: /TJAC/ });
    await user.click(unavailable);
    expect(unavailable.getAttribute('aria-checked')).toBe('false');
    screen.getByRole('tab', { name: /Estaduais/ }).focus();
    await user.keyboard('{Home}');
    await waitFor(() => expect(screen.getByRole('tab', { name: /Superiores/ }).getAttribute('aria-selected')).toBe('true'));
    expect(screen.getByRole('checkbox', { name: /STJ/ })).toBeTruthy();
    await user.click(screen.getByRole('tab', { name: /Estaduais/ }));
    expect(screen.getByRole('checkbox', { name: /TJSP/ }).getAttribute('aria-checked')).toBe('true');
  });

  it('does not select unavailable courts through presets', async () => {
    function Harness() {
      const [selected, setSelected] = useState(new Set(['tjsp']));
      return <CourtSelector activeCodes={new Set(['tjsp'])} selectedCodes={selected} onChange={setSelected} />;
    }
    const user = setup(<Harness />);
    await user.click(screen.getByRole('button', { name: /Superiores \(STF\/STJ\/TST\)/ }));
    expect(screen.getByText('0 tribunais selecionados')).toBeTruthy();
  });

  it('keeps icon actions working and reports clipboard success and failure', async () => {
    const user = setup(<DecisionCard decisao={{ processo: '123', cd_acordao: '1' }} />);
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Clipboard unavailable'));
    const copy = screen.getByRole('button', { name: 'Copiar número do processo' });
    await user.click(copy);
    expect(toast.error).toHaveBeenCalledWith('Não foi possível copiar. Tente novamente.');
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue();
    await user.click(copy);
    expect(toast.success).toHaveBeenCalledWith('Texto copiado.');
  });

  it('opens a precedent from the keyboard', async () => {
    const onInspect = vi.fn();
    const user = setup(<DecisionCard decisao={{ processo: '123', cd_acordao: '1' }} onInspect={onInspect} />);
    const precedent = screen.getByRole('article', { name: 'Analisar precedente 123' });
    precedent.focus();
    await user.keyboard('{Enter}');
    expect(onInspect).toHaveBeenCalledWith(expect.objectContaining({ processo: '123' }));
  });
});
