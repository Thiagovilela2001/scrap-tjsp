// @vitest-environment jsdom
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import PrecedentInspector from '../PrecedentInspector';

afterEach(cleanup);

describe('PrecedentInspector', () => {
  it('moves between content tabs with arrow keys', async () => {
    const user = userEvent.setup();
    render(
      <PrecedentInspector
        decisao={{ processo: '123', cd_acordao: '1', ementa: 'Ementa', argumento: 'Aplicação' }}
        onOpenPdf={() => {}}
        onToggleSelect={() => {}}
      />,
    );

    const ementaTab = screen.getByRole('tab', { name: 'Ementa Oficial' });
    const aplicacaoTab = screen.getByRole('tab', { name: 'Subsunção & Aplicação' });
    ementaTab.focus();

    await user.keyboard('{ArrowRight}');
    expect(aplicacaoTab.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(aplicacaoTab);

    await user.keyboard('{ArrowLeft}');
    expect(ementaTab.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(ementaTab);
  });
});
