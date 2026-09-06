/**
 * Normaliza textos jurídicos e ementas eliminando quebras de linha artificiais
 * geradas por sistemas de tribunais (como e-SAJ/TJSP), preservando tópicos e parágrafos.
 */
export function cleanLegalText(text) {
  if (!text || typeof text !== 'string') return '';

  // 1. Conecta pontuação órfã em nova linha (ex: "prova\n . Sua" -> "prova. Sua")
  let t = text.replace(/\s*\n\s*([.,;:!?])/g, '$1');

  // 2. Conectar linhas quebradas no meio de frases
  const lines = t.split('\n').map((l) => l.trim());
  const result = [];

  for (const line of lines) {
    if (!line) {
      if (result.length > 0 && result[result.length - 1] !== '') {
        result.push('');
      }
      continue;
    }

    if (result.length === 0 || result[result.length - 1] === '') {
      result.push(line);
      continue;
    }

    const prev = result[result.length - 1];
    // Se a linha atual for início de tópico numerado, seção Markdown (#) ou citação (>)
    const isNewTopic = /^(?:[0-9]+[\.\)\-]|[IVXLCDM]+[\.\)\-]|\([a-z0-9]\)|#+|>)\s*/i.test(line);
    // Se a linha anterior encerra frase formal
    const isPrevSentenceEnd = /[.:;]$/.test(prev) && !/\b(?:art|fls|inc|n|v|rel|dr|dra|exmo|des)\.$/i.test(prev);

    if (isNewTopic || (isPrevSentenceEnd && prev.length > 45)) {
      result.push(line);
    } else {
      result[result.length - 1] = `${prev} ${line}`;
    }
  }

  // 3. Normaliza espaçamentos e parágrafos
  return result
    .join('\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n');
}
