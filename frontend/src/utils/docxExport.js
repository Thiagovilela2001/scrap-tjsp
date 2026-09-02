import { 
  Document, 
  Packer, 
  Paragraph, 
  TextRun, 
  AlignmentType, 
  HeadingLevel, 
  Header, 
  Footer, 
  PageNumber, 
  NumberFormat,
  convertInchesToTwip,
  convertMillimetersToTwip,
  BorderStyle
} from 'docx';
import { saveAs } from 'file-saver';

/**
 * Generates and downloads a forensically-formatted .docx legal petition brief
 * following Brazilian procedural formatting (ABNT / CPC standards):
 * - Margins: Top 3cm, Left 3cm, Bottom 2cm, Right 2cm
 * - Body: Arial 12pt, 1.5 line spacing, Justified, First-line indent 1.25cm
 * - Precedent blockquotes: Indent 4cm, 10pt, single line spacing, italic
 */
export async function exportDraftToDocx({
  title = 'MINUTA DE JURISPRUDÊNCIA — TJSP',
  topic = '',
  draftText = '',
  selectedDecisions = [],
}) {
  const paragraphs = [];

  // Title / Document Header
  paragraphs.push(
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 300 },
      children: [
        new TextRun({
          text: title.toUpperCase(),
          bold: true,
          font: 'Arial',
          size: 28, // 14pt
          color: '0F172A',
        }),
      ],
    })
  );

  if (topic) {
    paragraphs.push(
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 400 },
        children: [
          new TextRun({
            text: `TEMA: ${topic}`,
            bold: true,
            font: 'Arial',
            size: 22, // 11pt
            color: '0284C7',
          }),
        ],
      })
    );
  }

  // Parse draft lines
  const rawLines = draftText.split('\n');

  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i].trim();
    if (!line) {
      // Empty spacing paragraph
      paragraphs.push(
        new Paragraph({
          spacing: { before: 120, after: 120 },
          children: [new TextRun('')],
        })
      );
      continue;
    }

    // Detect Markdown / Legal Headings (e.g. ## I - DOS FATOS, **DO DIREITO**, etc.)
    const isHeading1 = line.startsWith('# ') || /^[I|V|X]+\s*[-–.]\s*/.test(line);
    const isHeading2 = line.startsWith('## ') || line.startsWith('### ');

    if (isHeading1) {
      const cleanHeading = line.replace(/^#+\s*/, '').replace(/\*\*/g, '');
      paragraphs.push(
        new Paragraph({
          heading: HeadingLevel.HEADING_1,
          alignment: AlignmentType.LEFT,
          spacing: { before: 360, after: 180 },
          children: [
            new TextRun({
              text: cleanHeading.toUpperCase(),
              bold: true,
              font: 'Arial',
              size: 24, // 12pt
              color: '0F172A',
            }),
          ],
        })
      );
    } else if (isHeading2) {
      const cleanHeading = line.replace(/^#+\s*/, '').replace(/\*\*/g, '');
      paragraphs.push(
        new Paragraph({
          heading: HeadingLevel.HEADING_2,
          alignment: AlignmentType.LEFT,
          spacing: { before: 240, after: 120 },
          children: [
            new TextRun({
              text: cleanHeading,
              bold: true,
              font: 'Arial',
              size: 24, // 12pt
              color: '1E293B',
            }),
          ],
        })
      );
    } else if (line.startsWith('>') || line.startsWith('“') || line.startsWith('"') || line.includes('TJSP;')) {
      // Blockquote / Precedent citation (ABNT NBR 10520: recuo 4cm, tamanho 10pt)
      const cleanQuote = line.replace(/^>\s*/, '');
      paragraphs.push(
        new Paragraph({
          alignment: AlignmentType.JUSTIFIED,
          indent: { left: convertMillimetersToTwip(40) }, // 4cm indent
          spacing: { before: 140, after: 140, line: 240 }, // single spacing
          children: [
            new TextRun({
              text: cleanQuote,
              font: 'Arial',
              size: 20, // 10pt
              italics: true,
              color: '334155',
            }),
          ],
        })
      );
    } else {
      // Normal narrative paragraph: 1.25cm first line indent, 1.5 line spacing (360), 12pt
      const runs = parseInlineMarkdown(line);
      paragraphs.push(
        new Paragraph({
          alignment: AlignmentType.JUSTIFIED,
          indent: { firstLine: convertMillimetersToTwip(12.5) }, // 1.25cm
          spacing: { before: 0, after: 140, line: 360 }, // 1.5 line spacing
          children: runs,
        })
      );
    }
  }

  // Precedents Appendix Table / References (if any)
  if (selectedDecisions && selectedDecisions.length > 0) {
    paragraphs.push(
      new Paragraph({
        spacing: { before: 400, after: 160 },
        children: [
          new TextRun({
            text: 'PRECEDENTES JURISPRUDENCIAIS UTILIZADOS (TJSP)',
            bold: true,
            font: 'Arial',
            size: 22,
            color: '0F172A',
          }),
        ],
      })
    );

    selectedDecisions.forEach((decisao, idx) => {
      const numProcesso = decisao.processo || `Acórdão nº ${decisao.cd_acordao}`;
      const relator = decisao.relator ? `Rel. Des. ${decisao.relator}` : '';
      const orgao = decisao.orgao_julgador || 'TJSP';
      const data = decisao.data_julgamento ? `j. em ${decisao.data_julgamento}` : '';
      const citation = `[${idx + 1}] TJSP; ${numProcesso}; ${orgao}; ${relator}; ${data}.`;

      paragraphs.push(
        new Paragraph({
          alignment: AlignmentType.JUSTIFIED,
          spacing: { before: 60, after: 60, line: 240 },
          children: [
            new TextRun({
              text: citation,
              font: 'Arial',
              size: 19, // 9.5pt
              color: '475569',
            }),
          ],
        })
      );
    });
  }

  // Build Document with Forensics Page Margins (3cm top/left, 2cm bottom/right)
  const doc = new Document({
    sections: [
      {
        properties: {
          page: {
            margin: {
              top: convertMillimetersToTwip(30), // 3cm
              left: convertMillimetersToTwip(30), // 3cm
              bottom: convertMillimetersToTwip(20), // 2cm
              right: convertMillimetersToTwip(20), // 2cm
            },
          },
        },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                children: [
                  new TextRun({
                    text: 'Juris TJSP Studio Pro • Pesquisa e Minuta Jurídica',
                    font: 'Arial',
                    size: 16, // 8pt
                    color: '94A3B8',
                  }),
                ],
              }),
            ],
          }),
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                children: [
                  new TextRun({
                    text: 'Página ',
                    font: 'Arial',
                    size: 18,
                    color: '64748B',
                  }),
                  new TextRun({
                    children: [PageNumber.CURRENT],
                    font: 'Arial',
                    size: 18,
                    color: '64748B',
                  }),
                  new TextRun({
                    text: ' de ',
                    font: 'Arial',
                    size: 18,
                    color: '64748B',
                  }),
                  new TextRun({
                    children: [PageNumber.TOTAL_PAGES],
                    font: 'Arial',
                    size: 18,
                    color: '64748B',
                  }),
                ],
              }),
            ],
          }),
        },
        children: paragraphs,
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  const safeFilename = `Peticao_Minuta_TJSP_${new Date().toISOString().slice(0, 10)}.docx`;
  saveAs(blob, safeFilename);
}

/**
 * Simple parser for bold (**text**) in paragraphs
 */
function parseInlineMarkdown(text) {
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return new TextRun({
        text: part.slice(2, -2),
        bold: true,
        font: 'Arial',
        size: 24, // 12pt
        color: '0F172A',
      });
    }
    return new TextRun({
      text: part,
      font: 'Arial',
      size: 24, // 12pt
      color: '1E293B',
    });
  });
}
