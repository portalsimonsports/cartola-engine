/**
 * ============================================================================
 * PORTAL SIMONSPORTS
 * CARTOLA LIVE PUBLISHER — SOMENTE IMAGENS VIA GITHUB
 * VERSÃO v2026.125 — BLOQUEIO DEFINITIVO DAS SELEÇÕES EM TEXTO
 * ============================================================================
 *
 * SUBSTITUI integralmente o conteúdo do arquivo auxiliar:
 *
 *   ZZZ_LIVE_SOMENTE_IMAGENS.gs
 *
 * CORREÇÕES:
 * 1. Bloqueia definitivamente mensagens como:
 *      SELEÇÃO ECONOMICO — R19
 *      Total: 0.00 pts
 * 2. Bloqueia o formato antigo de SELEÇÃO dos três modelos mesmo quando o total
 *    deixar de ser zero. Os modelos devem ser publicados exclusivamente em card.
 * 3. Mantém bloqueadas em texto todas as demais publicações visuais.
 * 4. Preserva avisos operacionais curtos que não são relatórios.
 * 5. Remove acionadores antigos e instala somente o executor v2026.125.
 * 6. Mantém o organograma original de horários, deltas, placares e fechamento.
 * 7. Mantém o dispatch GitHub sem tentar obter um segundo ScriptLock.
 * 8. Payload antigo zerado e sem dados estruturados também é bloqueado no GitHub.
 *
 * APÓS SUBSTITUIR O ARQUIVO, EXECUTE UMA ÚNICA VEZ:
 *
 *   PSS_LIVE_IMAGENS_V125_INSTALAR
 *
 * Depois disso, não execute funções manualmente.
 * ============================================================================
 */

var PSS_LIVE_IMAGENS_V125_CONFIG = {
  VERSAO: "v2026.125",
  HANDLER: "PSS_LIVE_IMAGENS_V125_EXECUTAR",
  INTERVALO_MINUTOS: 5,
  EVENTO_GITHUB: "cartola_live_publish",
  WORKFLOW_GITHUB: "gerar.resultados.yml",
  REPOSITORIO_PADRAO: "portalsimonsports/cartola-engine",
  API_BASE_PADRAO: "https://api.github.com"
};


/* ============================================================================
 * INSTALAÇÃO
 * ============================================================================
 */

function PSS_LIVE_IMAGENS_V125_INSTALAR() {
  var ss = PSS_LIVE_IMAGENS_V125_obterPlanilha_();

  PSS_LIVE_IMAGENS_V125_upsertConfig_(ss, "GITHUB_TESTE_ATIVO", "SIM", false);
  PSS_LIVE_IMAGENS_V125_upsertConfig_(
    ss,
    "GITHUB_TESTE_REPO",
    PSS_LIVE_IMAGENS_V125_CONFIG.REPOSITORIO_PADRAO,
    false
  );
  PSS_LIVE_IMAGENS_V125_upsertConfig_(
    ss,
    "GITHUB_TESTE_API_BASE",
    PSS_LIVE_IMAGENS_V125_CONFIG.API_BASE_PADRAO,
    false
  );
  PSS_LIVE_IMAGENS_V125_upsertConfig_(
    ss,
    "GITHUB_LIVE_EVENTO",
    PSS_LIVE_IMAGENS_V125_CONFIG.EVENTO_GITHUB,
    true
  );
  PSS_LIVE_IMAGENS_V125_upsertConfig_(
    ss,
    "GITHUB_TESTE_INTERVALO_MIN",
    "10",
    false
  );

  // Desativa as rotas textuais antigas conhecidas.
  PSS_LIVE_IMAGENS_V125_upsertConfig_(ss, "NOTIF_TIMES", "NAO", true);
  PSS_LIVE_IMAGENS_V125_upsertConfig_(ss, "NOTIF_TOP5", "NAO", true);

  var removidos = PSS_LIVE_IMAGENS_V125_removerAcionadoresAntigos_();

  var novoTrigger = ScriptApp
    .newTrigger(PSS_LIVE_IMAGENS_V125_CONFIG.HANDLER)
    .timeBased()
    .everyMinutes(PSS_LIVE_IMAGENS_V125_CONFIG.INTERVALO_MINUTOS)
    .create();

  PropertiesService.getScriptProperties().setProperties({
    PSS_LIVE_IMAGENS_V125_INSTALADO: "SIM",
    PSS_LIVE_IMAGENS_V125_VERSAO: PSS_LIVE_IMAGENS_V125_CONFIG.VERSAO,
    PSS_LIVE_IMAGENS_V125_TRIGGER_ID: String(novoTrigger.getUniqueId() || ""),
    PSS_LIVE_IMAGENS_V125_INSTALADO_EM: new Date().toISOString()
  });

  var resultado = {
    ok: true,
    versao: PSS_LIVE_IMAGENS_V125_CONFIG.VERSAO,
    acionador: PSS_LIVE_IMAGENS_V125_CONFIG.HANDLER,
    intervalo_minutos: PSS_LIVE_IMAGENS_V125_CONFIG.INTERVALO_MINUTOS,
    acionadores_antigos_removidos: removidos,
    texto_selecao_antiga: "BLOQUEADO",
    texto_relatorios_visuais: "BLOQUEADO",
    evento_github: PSS_LIVE_IMAGENS_V125_CONFIG.EVENTO_GITHUB,
    workflow_github: PSS_LIVE_IMAGENS_V125_CONFIG.WORKFLOW_GITHUB
  };

  console.log(JSON.stringify(resultado));
  return resultado;
}


function PSS_LIVE_IMAGENS_V125_removerAcionadoresAntigos_() {
  var nomes = {
    publicarResumoLive: true,
    PSS_LIVE_PUBLICAR_SOMENTE_IMAGENS: true,
    PSS_LIVE_SOMENTE_IMAGENS: true,
    PSS_LIVE_IMAGENS_V123_EXECUTAR: true,
    PSS_LIVE_IMAGENS_V124_EXECUTAR: true,
    PSS_LIVE_IMAGENS_V125_EXECUTAR: true
  };

  var removidos = [];

  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    var nome = String(trigger.getHandlerFunction() || "");
    if (!nomes[nome]) return;

    ScriptApp.deleteTrigger(trigger);
    removidos.push(nome);
    console.log("Acionador removido: " + nome);
  });

  return removidos;
}


/* ============================================================================
 * BLOQUEIO CENTRAL DE TEXTO
 * ============================================================================
 */

function PSS_LIVE_IMAGENS_V125_normalizar_(valor) {
  var texto = String(valor == null ? "" : valor).trim();

  try {
    texto = texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } catch (ignore) {}

  return texto
    .toUpperCase()
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}


function PSS_LIVE_IMAGENS_V125_chave_(valor) {
  return PSS_LIVE_IMAGENS_V125_normalizar_(valor)
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}


function PSS_LIVE_IMAGENS_V125_hash_(obj) {
  return Utilities.base64Encode(
    Utilities.computeDigest(
      Utilities.DigestAlgorithm.MD5,
      JSON.stringify(obj || {})
    )
  );
}


function PSS_LIVE_IMAGENS_V125_ehSelecaoAntiga_(texto) {
  var t = PSS_LIVE_IMAGENS_V125_normalizar_(texto);
  if (!t) return false;

  return /(?:SELECAO|TIME)\s+(?:ECONOMICO|INTERMEDIARIO|PONTUACAO)\s*(?:—|-|–)\s*R\s*\d+/i
    .test(t);
}


function PSS_LIVE_IMAGENS_V125_ehSelecaoZerada_(texto) {
  var t = String(texto == null ? "" : texto);
  if (!PSS_LIVE_IMAGENS_V125_ehSelecaoAntiga_(t)) return false;

  var totalSimplesZero = /Total\s*:\s*0(?:[,.]0+)?\s*pts/i.test(t);
  var totalSemZero = /Total\s+Sem\s+Capit[aã]o\s*:\s*0(?:[,.]0+)?\s*pts/i.test(t);
  var totalComZero = /Total\s+Com\s+Capit[aã]o(?:\s*\([^)]*\))?\s*:\s*0(?:[,.]0+)?\s*pts/i.test(t);

  return totalSimplesZero || (totalSemZero && totalComZero);
}


function PSS_LIVE_IMAGENS_V125_ehRelatorioVisual_(texto) {
  var t = PSS_LIVE_IMAGENS_V125_normalizar_(texto);
  if (!t) return false;

  if (PSS_LIVE_IMAGENS_V125_ehSelecaoAntiga_(t)) return true;

  var marcadores = [
    "PORTAL SIMONSPORTS - RESUMO GERAL",
    "PORTAL SIMONSPORTS – RESUMO GERAL",
    "RESUMO GERAL",
    "PARCIAIS DO TOP 5 SUGERIDO",
    "TOP 5 SUGERIDO",
    "MITOS E ZICAS DA RODADA",
    "PARCIAIS GERAIS DE ATLETAS",
    "RESULTADOS E RESUMOS",
    "STATUS DOS JOGOS DA RODADA",
    "ATUALIZACAO DE PLACAR",
    "PLACAR DELTA",
    "RESUMO FINAL DA RODADA",
    "TIME ECONOMICO",
    "TIME INTERMEDIARIO",
    "TIME PONTUACAO",
    "SELECAO ECONOMICO",
    "SELECAO INTERMEDIARIO",
    "SELECAO PONTUACAO"
  ];

  for (var i = 0; i < marcadores.length; i++) {
    if (t.indexOf(PSS_LIVE_IMAGENS_V125_normalizar_(marcadores[i])) !== -1) {
      return true;
    }
  }

  return false;
}


function PSS_LIVE_IMAGENS_V125_bloquearTexto_(texto) {
  texto = String(texto == null ? "" : texto).trim();
  if (!texto) return true;

  if (PSS_LIVE_IMAGENS_V125_ehSelecaoAntiga_(texto)) {
    console.log(
      "🚫 BLOQUEIO DEFINITIVO: publicação antiga de SELEÇÃO não enviada em texto: " +
      texto.substring(0, 220)
    );
    return true;
  }

  if (PSS_LIVE_IMAGENS_V125_ehRelatorioVisual_(texto)) {
    console.log(
      "🖼️ Texto visual bloqueado; a publicação válida seguirá somente como imagem: " +
      texto.substring(0, 220)
    );
    return true;
  }

  return false;
}


/**
 * Esta função é declarada de propósito com o mesmo nome da rota original.
 * No arquivo ZZZ ela se torna a última barreira antes do sendMessage.
 */
function enviarTelegram_(cfg, texto) {
  texto = String(texto == null ? "" : texto).trim();

  if (PSS_LIVE_IMAGENS_V125_bloquearTexto_(texto)) {
    // Retorna true para que o fluxo original continue até o dispatch da imagem.
    return true;
  }

  if (!cfg || !cfg.TG_BOT_TOKEN || !cfg.TG_CHAT_ID) {
    console.log("Mensagem operacional não enviada: Token ou ChatID ausentes.");
    return false;
  }

  var url =
    "https://api.telegram.org/bot" +
    String(cfg.TG_BOT_TOKEN) +
    "/sendMessage";

  var payload = {
    chat_id: String(cfg.TG_CHAT_ID),
    text: texto,
    parse_mode: "Markdown",
    disable_web_page_preview: true
  };

  try {
    var resp = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });

    var code = resp.getResponseCode();
    var corpo = resp.getContentText();

    if (code >= 200 && code < 300) return true;

    // Uma mensagem operacional curta não deve falhar apenas por Markdown.
    if (code === 400 && /parse/i.test(corpo)) {
      delete payload.parse_mode;
      resp = UrlFetchApp.fetch(url, {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });
      code = resp.getResponseCode();
      corpo = resp.getContentText();
      if (code >= 200 && code < 300) return true;
    }

    console.log("Falha Telegram operacional HTTP " + code + ": " + corpo);
    return false;
  } catch (erro) {
    console.log("Erro Telegram operacional: " + erro.message);
    return false;
  }
}


/**
 * Barreira compatível com versões do núcleo que consultam este helper antes de
 * chamar enviarTelegram_().
 */
function psLiveBloquearMensagemTelegram_(texto) {
  return PSS_LIVE_IMAGENS_V125_bloquearTexto_(texto);
}


/* ============================================================================
 * EXECUTOR OFICIAL DO ACIONADOR
 * ============================================================================
 */

function PSS_LIVE_IMAGENS_V125_EXECUTAR() {
  if (typeof publicarResumoLive !== "function") {
    throw new Error(
      "A função publicarResumoLive() não foi encontrada no Cartola Live.gs."
    );
  }

  if (typeof dispararGithubTeste_ !== "function") {
    throw new Error(
      "A função dispararGithubTeste_() não foi encontrada no Cartola Live.gs."
    );
  }

  var enviarTelegramAnterior =
    (typeof enviarTelegram_ === "function") ? enviarTelegram_ : null;
  var bloqueioAnterior =
    (typeof psLiveBloquearMensagemTelegram_ === "function")
      ? psLiveBloquearMensagemTelegram_
      : null;
  var dispararGithubAnterior = dispararGithubTeste_;

  try {
    // Reforço em tempo de execução, além da declaração global acima.
    enviarTelegram_ = function(cfg, texto) {
      return PSS_LIVE_IMAGENS_V125_enviarTelegramSeguro_(cfg, texto);
    };

    psLiveBloquearMensagemTelegram_ = function(texto) {
      return PSS_LIVE_IMAGENS_V125_bloquearTexto_(texto);
    };

    dispararGithubTeste_ = function(cfg, tipoPublicacao, payload) {
      return PSS_LIVE_IMAGENS_V125_dispararGithubSemSegundoLock_(
        cfg,
        tipoPublicacao,
        payload
      );
    };

    return publicarResumoLive();

  } finally {
    if (enviarTelegramAnterior) enviarTelegram_ = enviarTelegramAnterior;
    if (bloqueioAnterior) {
      psLiveBloquearMensagemTelegram_ = bloqueioAnterior;
    }
    dispararGithubTeste_ = dispararGithubAnterior;
  }
}


function PSS_LIVE_IMAGENS_V125_enviarTelegramSeguro_(cfg, texto) {
  texto = String(texto == null ? "" : texto).trim();
  if (PSS_LIVE_IMAGENS_V125_bloquearTexto_(texto)) return true;

  // Avisos curtos continuam permitidos pela mesma implementação segura.
  if (!cfg || !cfg.TG_BOT_TOKEN || !cfg.TG_CHAT_ID) return false;

  var url =
    "https://api.telegram.org/bot" +
    String(cfg.TG_BOT_TOKEN) +
    "/sendMessage";

  try {
    var resposta = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({
        chat_id: String(cfg.TG_CHAT_ID),
        text: texto,
        parse_mode: "Markdown",
        disable_web_page_preview: true
      }),
      muteHttpExceptions: true
    });

    var http = resposta.getResponseCode();
    console.log(
      "Telegram operacional HTTP " + http + ": " + resposta.getContentText()
    );
    return http >= 200 && http < 300;
  } catch (erro) {
    console.log("Erro Telegram operacional: " + erro.message);
    return false;
  }
}


/* ============================================================================
 * DISPATCH GITHUB SEM SEGUNDO LOCK
 * ============================================================================
 */

function PSS_LIVE_IMAGENS_V125_payloadLegadoZerado_(tipoPublicacao, payload) {
  payload = payload || {};

  var mensagem = String(payload.mensagem_oficial || "");
  var tipo = PSS_LIVE_IMAGENS_V125_chave_(tipoPublicacao || "");
  var tipoTime = String(
    payload.tipo_time || payload.tipo || payload.modelo || ""
  ).trim();

  var temEstrutura = !!(
    (Array.isArray(payload.atletas) && payload.atletas.length) ||
    (Array.isArray(payload.jogadores) && payload.jogadores.length) ||
    (Array.isArray(payload.dados) && payload.dados.length) ||
    (Array.isArray(payload.tipos) && payload.tipos.length)
  );

  if (temEstrutura) return false;

  if (PSS_LIVE_IMAGENS_V125_ehSelecaoZerada_(mensagem)) return true;

  var ehTime =
    tipo.indexOf("TIME") >= 0 ||
    tipo.indexOf("SELECAO") >= 0 ||
    !!tipoTime;

  if (!ehTime) return false;

  var semCap = Number(payload.pontos_sem_capitao || 0);
  var comCap = Number(payload.pontos_com_capitao || 0);
  var participacao = Number(payload.participacao || payload.participaram || 0);

  return (
    Math.abs(semCap) < 0.0001 &&
    Math.abs(comCap) < 0.0001 &&
    participacao <= 0
  );
}


function PSS_LIVE_IMAGENS_V125_payloadPublicavel_(tipoPublicacao, payload) {
  payload = payload || {};

  if (
    PSS_LIVE_IMAGENS_V125_payloadLegadoZerado_(tipoPublicacao, payload)
  ) {
    console.log(
      "🚫 GitHub bloqueado: payload antigo de seleção zerada e sem estrutura."
    );
    return false;
  }

  if (Array.isArray(payload.tipos) && payload.tipos.length === 0) return false;
  if (Array.isArray(payload.partidas) && payload.partidas.length === 0) return false;
  if (Array.isArray(payload.posicoes) && payload.posicoes.length === 0) return false;

  if (
    Array.isArray(payload.top_5) && payload.top_5.length === 0 &&
    Array.isArray(payload.piores_5) && payload.piores_5.length === 0
  ) {
    return false;
  }

  return !!(
    String(payload.mensagem_oficial || "").trim() ||
    (Array.isArray(payload.tipos) && payload.tipos.length) ||
    (Array.isArray(payload.partidas) && payload.partidas.length) ||
    (Array.isArray(payload.posicoes) && payload.posicoes.length) ||
    (Array.isArray(payload.top_5) && payload.top_5.length) ||
    (Array.isArray(payload.piores_5) && payload.piores_5.length) ||
    (Array.isArray(payload.atletas) && payload.atletas.length) ||
    (Array.isArray(payload.jogadores) && payload.jogadores.length) ||
    Object.keys(payload).length
  );
}


function PSS_LIVE_IMAGENS_V125_dispararGithubSemSegundoLock_(
  cfg,
  tipoPublicacao,
  payload
) {
  cfg = cfg || {};
  payload = payload || {};

  try {
    var ativo = String(
      cfg.GITHUB_TESTE_ATIVO ||
      cfg.GITHUB_LIVE_ATIVO ||
      "NAO"
    ).trim().toUpperCase() === "SIM";

    if (!ativo) {
      console.log("GitHub Live inativo na CONFIG.");
      return false;
    }

    var repo = String(
      cfg.GITHUB_TESTE_REPO ||
      cfg.GITHUB_LIVE_REPO ||
      cfg.GITHUB_REPO ||
      PSS_LIVE_IMAGENS_V125_CONFIG.REPOSITORIO_PADRAO
    ).trim();

    var token = String(
      cfg.GITHUB_TESTE_TOKEN ||
      cfg.GITHUB_LIVE_TOKEN ||
      cfg.GITHUB_TOKEN ||
      ""
    ).trim();

    var apiBase = String(
      cfg.GITHUB_TESTE_API_BASE ||
      cfg.GITHUB_LIVE_API_BASE ||
      cfg.GITHUB_API_BASE ||
      PSS_LIVE_IMAGENS_V125_CONFIG.API_BASE_PADRAO
    ).trim();

    var intervaloMin = Number(
      cfg.GITHUB_TESTE_INTERVALO_MIN ||
      cfg.GITHUB_LIVE_INTERVALO_MIN ||
      10
    );
    if (!intervaloMin || intervaloMin < 1) intervaloMin = 10;

    if (!repo || !token) {
      console.log("GitHub Live não enviado: repositório ou token ausente.");
      return false;
    }

    if (
      !PSS_LIVE_IMAGENS_V125_payloadPublicavel_(tipoPublicacao, payload)
    ) {
      return false;
    }

    var contexto = String(payload.contexto || "padrao").trim();
    var rodada = Number(
      payload.rodada ||
      cfg.rodada_atual ||
      cfg.RODADA_ATUAL ||
      0
    );

    var raizHash = {
      tipo_publicacao: String(tipoPublicacao || ""),
      contexto: contexto,
      rodada: rodada,
      payload: payload
    };

    var hash = PSS_LIVE_IMAGENS_V125_hash_(raizHash);
    var tipoSeguro = PSS_LIVE_IMAGENS_V125_chave_(
      tipoPublicacao || "GERAL"
    );
    var contextoSeguro = PSS_LIVE_IMAGENS_V125_chave_(
      contexto || "PADRAO"
    );

    var chaveBase = [
      "PSS_LIVE_IMAGENS_V125",
      "R" + rodada,
      tipoSeguro,
      contextoSeguro
    ].join("_");

    var props = PropertiesService.getScriptProperties();
    var chaveHash = chaveBase + "_HASH";
    var chaveTs = chaveBase + "_TS";
    var hashAnterior = String(props.getProperty(chaveHash) || "");
    var tsAnterior = Number(props.getProperty(chaveTs) || 0);
    var agoraMs = Date.now();
    var diffMin = tsAnterior
      ? (agoraMs - tsAnterior) / 60000
      : 999999;

    if (hashAnterior === hash && diffMin < intervaloMin) {
      console.log(
        "GitHub Live: conteúdo idêntico já aceito; duplicidade bloqueada."
      );
      return true;
    }

    var payloadFinal = {
      origem: "cartola_live_publisher",
      ambiente: "producao",
      workflow_destino: PSS_LIVE_IMAGENS_V125_CONFIG.WORKFLOW_GITHUB,
      evento_github: PSS_LIVE_IMAGENS_V125_CONFIG.EVENTO_GITHUB,
      tipo_publicacao: String(tipoPublicacao || ""),
      contexto: contexto,
      rodada: rodada,
      gerado_em: new Date().toISOString(),
      payload_hash: hash,
      payload: payload
    };

    var url = apiBase.replace(/\/$/, "") +
      "/repos/" + repo + "/dispatches";

    var resposta = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      headers: {
        Authorization: "Bearer " + token,
        Accept: "application/vnd.github+json"
      },
      payload: JSON.stringify({
        event_type: PSS_LIVE_IMAGENS_V125_CONFIG.EVENTO_GITHUB,
        client_payload: payloadFinal
      }),
      muteHttpExceptions: true
    });

    var http = resposta.getResponseCode();
    var corpo = resposta.getContentText();
    var ok = http >= 200 && http < 300;

    console.log(
      "GitHub Live imagem HTTP=" + http +
      " | tipo=" + tipoSeguro +
      " | contexto=" + contextoSeguro +
      " | rodada=" + rodada +
      " | resposta=" + corpo
    );

    if (!ok) return false;

    props.setProperty(chaveHash, hash);
    props.setProperty(chaveTs, String(agoraMs));
    return true;

  } catch (erro) {
    console.log(
      "ERRO no GitHub Live imagem: " +
      (erro && erro.stack ? erro.stack : erro.message)
    );
    return false;
  }
}


/* ============================================================================
 * CONFIGURAÇÃO DA PLANILHA
 * ============================================================================
 */

function PSS_LIVE_IMAGENS_V125_obterPlanilha_() {
  if (typeof ID_PLANILHA_MESTRE === "undefined") {
    throw new Error(
      "A constante ID_PLANILHA_MESTRE não foi encontrada no Cartola Live.gs."
    );
  }
  return SpreadsheetApp.openById(ID_PLANILHA_MESTRE);
}


function PSS_LIVE_IMAGENS_V125_upsertConfig_(
  ss,
  chave,
  valor,
  sobrescrever
) {
  var sh = ss.getSheetByName("CONFIG");
  if (!sh) throw new Error("A aba CONFIG não foi encontrada.");

  var ultimaLinha = sh.getLastRow();
  if (ultimaLinha >= 1) {
    var dados = sh.getRange(1, 1, ultimaLinha, 2).getValues();
    var alvo = String(chave || "").trim().toUpperCase();

    for (var i = 0; i < dados.length; i++) {
      var atual = String(dados[i][0] || "").trim().toUpperCase();
      if (atual !== alvo) continue;

      if (sobrescrever) sh.getRange(i + 1, 2).setValue(valor);
      return;
    }
  }

  sh.appendRow([chave, valor]);
}


/* ============================================================================
 * DIAGNÓSTICO — NÃO ENVIA NADA
 * ============================================================================
 */

function PSS_LIVE_IMAGENS_V125_DIAGNOSTICO() {
  var testes = [
    "🎩 SELEÇÃO ECONOMICO — R19\n\nTotal: 0.00 pts",
    "🎩 SELEÇÃO INTERMEDIARIO — R19\n\nTotal: 18.50 pts",
    "🔥 MITOS E ZICAS DA RODADA",
    "Mensagem operacional curta"
  ];

  var resultadoTestes = testes.map(function(texto) {
    return {
      texto: texto,
      bloqueado: PSS_LIVE_IMAGENS_V125_bloquearTexto_(texto)
    };
  });

  var acionadores = ScriptApp.getProjectTriggers().map(function(trigger) {
    return {
      funcao: String(trigger.getHandlerFunction() || ""),
      origem: String(trigger.getTriggerSource() || ""),
      evento: String(trigger.getEventType() || "")
    };
  });

  var props = PropertiesService.getScriptProperties();
  var resultado = {
    versao: PSS_LIVE_IMAGENS_V125_CONFIG.VERSAO,
    instalado: props.getProperty("PSS_LIVE_IMAGENS_V125_INSTALADO"),
    acionador_esperado: PSS_LIVE_IMAGENS_V125_CONFIG.HANDLER,
    acionadores: acionadores,
    testes: resultadoTestes
  };

  console.log(JSON.stringify(resultado));
  return resultado;
}


function PSS_LIVE_IMAGENS_V125_DESINSTALAR() {
  var removidos = [];

  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    var nome = String(trigger.getHandlerFunction() || "");
    if (nome !== PSS_LIVE_IMAGENS_V125_CONFIG.HANDLER) return;

    ScriptApp.deleteTrigger(trigger);
    removidos.push(nome);
  });

  PropertiesService.getScriptProperties().deleteProperty(
    "PSS_LIVE_IMAGENS_V125_INSTALADO"
  );

  console.log("Módulo V125 desinstalado: " + JSON.stringify(removidos));
  return removidos;
}
