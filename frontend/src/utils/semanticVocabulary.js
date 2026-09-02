/**
 * Vocabulário Semântico e Mapeamento de Ramos / Situações Jurídicas do TJSP
 * Usado para desambiguar pesquisas vagas e orientar o usuário via formulário de múltipla escolha.
 */

export const SEMANTIC_BRANCHES = [
  {
    id: 'consumidor_bancario',
    label: 'Direito Bancário & Fraudes',
    keywords: ['banco', 'pix', 'golpe', 'fraude', 'empréstimo', 'cartão', 'rcc', 'rmc', 'conta', 'instituição financeira', 'súmula 479'],
    questions: [
      {
        id: 'fato',
        title: 'Qual a situação fática específica?',
        multi: true,
        options: [
          'Golpe do PIX / Transferência fraudulenta sob coação',
          'Contratação não reconhecida de Empréstimo Consignado (RMC/RCC)',
          'Fraude de boleto falso / Engenharia social',
          'Cobrança de tarifas bancárias não contratadas',
          'Inclusão indevida no CCF / Serasa por cheque clonado',
        ],
      },
      {
        id: 'tese',
        title: 'Qual a tese jurídica aplicável?',
        multi: true,
        options: [
          'Fortuito interno e Responsabilidade Objetiva (Súmula 479 do STJ)',
          'Falha no dever de segurança e monitoramento de perfil de risco',
          'Inversão do ônus da prova (Art. 6º, VIII do CDC)',
          'Nulidade de cláusula com repetição do indébito em dobro (Art. 42 CDC)',
        ],
      },
      {
        id: 'pedidos',
        title: 'Quais os pedidos pretendidos?',
        multi: true,
        options: [
          'Indenização por Danos Morais (in re ipsa)',
          'Restituição integral dos valores desviados (Dano Material)',
          'Devolução em dobro dos valores descontados indevidamente',
          'Cancelamento definitivo do contrato com declaração de inexigibilidade',
          'Tutela de urgência para cessar descontos imediatos em folha',
        ],
      },
    ],
  },
  {
    id: 'direito_aereo',
    label: 'Direito Aeronáutico & Transporte Aéreo',
    keywords: ['voo', 'aviao', 'avião', 'aeroporto', 'bagagem', 'cancelamento', 'atraso', 'overbooking', 'companhia aérea', 'extravio'],
    questions: [
      {
        id: 'fato',
        title: 'Qual o incidente do voo?',
        multi: true,
        options: [
          'Atraso excessivo de voo (superior a 4 horas)',
          'Cancelamento unilateral do voo com perda de conexão/diária',
          'Extravio temporário de bagagem com despesas de primeira necessidade',
          'Extravio definitivo de bagagem',
          'Preterição de embarque / Overbooking',
        ],
      },
      {
        id: 'tipo_voo',
        title: 'Qual o tipo de voo?',
        multi: false,
        options: [
          'Voo Nacional (Regulado prioritariamente pelo CDC)',
          'Voo Internacional (Conflito entre CDC e Convenções de Varsóvia/Montreal)',
        ],
      },
      {
        id: 'pedidos',
        title: 'Quais pedidos formular?',
        multi: true,
        options: [
          'Dano moral por ausência de assistência material (alimentação/hotel)',
          'Dano moral presumido pela perda de compromisso/frustração da viagem',
          'Ressarcimento de despesas materiais comprovadas (compras emergenciais/passagem)',
          'Reembolso integral do bilhete não utilizado',
        ],
      },
    ],
  },
  {
    id: 'imobiliario_condominio',
    label: 'Direito Imobiliário, Vícios & Locação',
    keywords: ['imóvel', 'imovel', 'apartamento', 'condomínio', 'condominio', 'locação', 'locacao', 'aluguel', 'vício', 'infiltração', 'atraso na entrega', 'construtora', 'despejo'],
    questions: [
      {
        id: 'fato',
        title: 'Qual o problema fático imobiliário?',
        multi: true,
        options: [
          'Vício construtivo / Infiltrações e rachaduras estruturais',
          'Atraso injustificado na entrega das chaves além do prazo de tolerância',
          'Cobrança indevida de taxa de evolução de obra ou comissão de corretagem',
          'Inadimplemento de aluguel e encargos locatícios',
          'Perturbação do sossego / Barulho excessivo e infração às normas condominiais',
        ],
      },
      {
        id: 'tese',
        title: 'Qual a tese jurídica a sustentar?',
        multi: true,
        options: [
          'Responsabilidade objetiva do construtor (Art. 618 do Código Civil)',
          'Prazo decadencial do art. 26 CDC vs Prescrição de 10 anos (Art. 205 CC)',
          'Lucros cessantes presumidos pelo atraso na entrega do imóvel (Tema 996 STJ)',
          'Despejo liminar por falta de pagamento sem garantia (Art. 59 Lei 8.245)',
        ],
      },
    ],
  },
  {
    id: 'saude_planos',
    label: 'Direito à Saúde & Planos Médicos',
    keywords: ['plano de saúde', 'plano de saude', 'cirurgia', 'medicamento', 'tratamento', 'home care', 'hospital', 'negativa', 'rol da ans', 'unimed', 'bradesco saude', 'amil', 'notredame', 'autismo', 'tea'],
    questions: [
      {
        id: 'fato',
        title: 'Qual a conduta do plano de saúde / SUS?',
        multi: true,
        options: [
          'Negativa de cobertura de medicamento de alto custo não previsto no Rol da ANS',
          'Recusa de fornecimento de terapia multidisciplinar (Método ABA / TEA)',
          'Negativa de cirurgia de urgência ou material cirúrgico específico (prótese/órtese)',
          'Negativa de internação domiciliar (Home Care)',
          'Reajuste abusivo por faixa etária ou sinistralidade',
        ],
      },
      {
        id: 'tese',
        title: 'Tese / Súmulas TJSP aplicáveis:',
        multi: true,
        options: [
          'Súmula 102 TJSP (Havendo indicação médica, é abusiva a negativa de cobertura)',
          'Súmula 96 TJSP (Rol exemplificativo da ANS e taxatividade mitigada)',
          'Prescrição médica soberana sobre a escolha do tratamento',
          'Abusividade de cláusula restritiva de direitos fundamentais',
        ],
      },
      {
        id: 'pedidos',
        title: 'Pedidos pretendidos:',
        multi: true,
        options: [
          'Tutela de urgência inaudita altera parte com cominação de multa diária (astreintes)',
          'Dano moral pela negativa injustificada de cobertura em momento de aflição',
          'Ressarcimento integral de despesas médicas pagas pelo beneficiário',
        ],
      },
    ],
  },
  {
    id: 'responsabilidade_civil_geral',
    label: 'Responsabilidade Civil, Acidentes & Negativações',
    keywords: ['dano moral', 'negativação', 'negativacao', 'spc', 'serasa', 'acidente', 'trânsito', 'batida', 'queda', 'ofensa', 'calúnia', 'protesto indevido', 'cheque'],
    questions: [
      {
        id: 'fato',
        title: 'Qual o evento danoso?',
        multi: true,
        options: [
          'Negativação indevida por dívida inexistente ou já quitada',
          'Acidente de trânsito causado por imprudência / desrespeito à sinalização',
          'Manutenção indevida do nome nos cadastros restritivos após pagamento',
          'Protesto indevido de duplicata mercantil sem lastro',
          'Acidente de consumo em estabelecimento comercial (queda/lesão)',
        ],
      },
      {
        id: 'tese',
        title: 'Fundamentação jurídica:',
        multi: true,
        options: [
          'Dano moral in re ipsa (dispensa prova do abalo psicológico)',
          'Inaplicabilidade da Súmula 385 do STJ (ausência de anotações prévias legítimas)',
          'Culpa presumida e dever de indenizar danos materiais e morais',
          'Quantum indenizatório pelo caráter pedagógico e punitivo do desestímulo',
        ],
      },
    ],
  },
];

/**
 * Detecta se uma pergunta é vaga ou corresponde a um ramo semântico
 */
export function matchSemanticBranch(queryText) {
  if (!queryText || typeof queryText !== 'string') return null;
  const q = queryText.toLowerCase().trim();

  for (const branch of SEMANTIC_BRANCHES) {
    const matched = branch.keywords.some((kw) => q.includes(kw));
    if (matched) {
      return branch;
    }
  }
  return null;
}

/**
 * Constrói a consulta refinada a partir das respostas do formulário
 */
export function buildRefinedQuery(originalQuery, selectedAnswers, customDetail) {
  const parts = [];

  const answersList = [];
  Object.values(selectedAnswers).forEach((vals) => {
    if (Array.isArray(vals)) {
      vals.forEach((v) => {
        if (v && !answersList.includes(v)) answersList.push(v);
      });
    } else if (typeof vals === 'string' && vals.trim()) {
      if (!answersList.includes(vals.trim())) answersList.push(vals.trim());
    }
  });

  if (originalQuery && originalQuery.trim()) {
    parts.push(originalQuery.trim());
  }

  if (answersList.length > 0) {
    parts.push(answersList.join(', '));
  }

  if (customDetail && customDetail.trim()) {
    parts.push(customDetail.trim());
  }

  return parts.join('. ');
}
