/**
 * ============================================================================
 * PORTAL SIMONSPORTS
 * CARTOLA LIVE PUBLISHER — CORREÇÃO: SOMENTE IMAGENS VIA GITHUB
 * ============================================================================
 *
 * PROBLEMA CORRIGIDO:
 * O Live Publisher montava a publicação em texto, enviava diretamente ao
 * Telegram por sendMessage e, depois, também disparava o GitHub.
 *
 * COMPORTAMENTO NOVO:
 * - Relatórios estruturados do Live Publisher NÃO são mais enviados em texto.
 * - O dispatch para cartola_live_publish continua sendo executado normalmente.
 * - O GitHub gera e publica as imagens.
 * - Mensagens técnicas curtas que não pertencem aos relatórios continuam
 *   permitidas, caso ainda exista alguma chamada legítima.
 *
 * APLICAÇÃO:
 * 1. Adicione a função psLivePublicacaoVisualGithub_ ao projeto.
 * 2. Substitua integralmente a função enviarTelegram_(cfg, texto) pela versão
 *    contida neste arquivo.
 *
 * NÃO ALTERE:
 * - psLiveBloquearMensagemTelegram_
 * - psLivePayloadTemConteudoPublicavelGithub_
 * - dispararGithubTeste_
 *
 * Dessa forma, o texto direto é bloqueado sem bloquear o dispatch das imagens.
 * ============================================================================
 */


/**
 * Identifica relatórios que devem ser publicados exclusivamente como imagem.
 */
function psLivePublicacaoVisualGithub_(texto) {
  var normalizado = String(texto || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/\s+/g, " ")
    .trim();

  if (!normalizado) return false;

  var marcadoresVisuais = [
    "PORTAL SIMONSPORTS - RESUMO GERAL",
    "PORTAL SIMONSPORTS – RESUMO GERAL",
    "PARCIAIS DO TOP 5 SUGERIDO",
    "TOP 5 SUGERIDO",
    "MITOS E ZICAS",
    "PARCIAIS GERAIS DE ATLETAS",
    "RESULTADOS E RESUMOS",
    "STATUS DOS JOGOS DA RODADA",
    "ATUALIZACAO DE PLACAR"
  ];

  for (var i = 0; i < marcadoresVisuais.length; i++) {
    var marcador = String(marcadoresVisuais[i])
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toUpperCase();

    if (normalizado.indexOf(marcador) !== -1) {
      return true;
    }
  }

  // Times oficiais do Live Publisher.
  if (
    /(?:SELECAO|TIME)\s+(?:ECONOMICO|INTERMEDIARIO|PONTUACAO)\s*[—-]\s*R\d+/i
      .test(normalizado)
  ) {
    return true;
  }

  return false;
}


/**
 * Substitui integralmente a função antiga.
 *
 * IMPORTANTE:
 * Esta função apenas impede o sendMessage direto.
 * As funções de publicação continuam executando dispararGithubTeste_()
 * logo depois, portanto as imagens continuam sendo geradas pelo GitHub.
 */
function enviarTelegram_(cfg, texto) {
  texto = String(texto || "").trim();

  if (typeof psLiveBloquearMensagemTelegram_ === "function") {
    if (psLiveBloquearMensagemTelegram_(texto)) {
      return false;
    }
  }

  if (psLivePublicacaoVisualGithub_(texto)) {
    console.log(
      "🖼️ Texto direto bloqueado. " +
      "A publicação será enviada ao GitHub para geração da imagem: " +
      texto.substring(0, 140)
    );
    return false;
  }

  if (!cfg || !cfg.TG_BOT_TOKEN || !cfg.TG_CHAT_ID) {
    console.log("Erro: Token ou ChatID ausentes na aba CONFIG.");
    return false;
  }

  const url =
    "https://api.telegram.org/bot" +
    cfg.TG_BOT_TOKEN +
    "/sendMessage";

  const payload = {
    chat_id: String(cfg.TG_CHAT_ID),
    text: texto,
    parse_mode: "Markdown",
    disable_web_page_preview: true
  };

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  try {
    const resp = UrlFetchApp.fetch(url, options);
    const code = resp.getResponseCode();
    const body = resp.getContentText();

    console.log("Telegram texto HTTP " + code + " :: " + body);

    if (code < 200 || code >= 300) {
      console.log(
        "Falha no envio de texto ao Telegram. HTTP " +
        code +
        " :: " +
        body
      );
      return false;
    }

    return true;

  } catch (e) {
    console.log("Erro ao enviar texto ao Telegram: " + e.message);
    return false;
  }
}


/**
 * Teste local opcional.
 * Apenas registra no log; não envia nada ao Telegram.
 */
function psLiveTestarBloqueioSomenteImagens_() {
  var testes = [
    "🔥 MITOS E ZICAS DA RODADA\nParciais Gerais de Atletas",
    "🏟️ RESULTADOS E RESUMOS\nStatus dos Jogos da Rodada",
    "⚽ ATUALIZAÇÃO DE PLACAR",
    "TIME PONTUACAO — R19",
    "Mensagem operacional curta"
  ];

  testes.forEach(function(texto) {
    console.log(
      JSON.stringify({
        texto: texto,
        somenteImagem: psLivePublicacaoVisualGithub_(texto)
      })
    );
  });
}
