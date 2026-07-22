/**
 * ============================================================================
 * PORTAL SIMONSPORTS
 * CARTOLA LIVE PUBLISHER — MÓDULO DEFINITIVO SOMENTE IMAGENS VIA GITHUB
 * Versão: v2026.123 — 21/07/2026
 * ============================================================================
 *
 * FINALIDADE
 * - Corrige o projeto pelo celular, sem exportar o Cartola Live.gs atual.
 * - Bloqueia as publicações extensas em texto do Live Publisher.
 * - Mantém o mesmo organograma, gatilhos, horários e critérios de publicação.
 * - Redireciona TODAS as publicações válidas do Live Publisher para:
 *       evento GitHub: cartola_live_publish
 *       workflow: .github/workflows/gerar.resultados.yml
 * - O GitHub gera o card profissional e publica a imagem no Telegram.
 *
 * COMO APLICAR NO CELULAR
 * 1. No projeto "Cartola LIVE Publisher", toque no botão + ao lado de Arquivos.
 * 2. Crie um novo arquivo de script com o nome:
 *       ZZZ_LIVE_SOMENTE_IMAGENS
 * 3. Cole TODO este arquivo no novo .gs.
 * 4. Salve o projeto.
 * 5. NÃO apague nem altere Cartola Live.gs e Cartola GitHub Sync.gs.
 * 6. NÃO precisa executar nenhuma função.
 *
 * IMPORTANTE
 * Este módulo não declara outra função com o mesmo nome. Ele substitui em tempo
 * de execução as rotas antigas, evitando o problema de funções duplicadas que
 * ocorreu quando a correção anterior foi apenas colada no final do arquivo.
 * ============================================================================
 */

var PSS_LIVE_ORIGINAL_ENVIAR_TELEGRAM_ =
  (typeof enviarTelegram_ === "function") ? enviarTelegram_ : null;

var PSS_LIVE_ORIGINAL_DISPARAR_GITHUB_ =
  (typeof dispararGithubTeste_ === "function") ? dispararGithubTeste_ : null;

function PSS_LIVE_normalizarTextoImagem_(valor) {
  var texto = String(valor == null ? "" : valor).trim();
  try {
    texto = texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } catch (ignore) {}
  return texto.toUpperCase().replace(/[*_`~]/g, "").replace(/\s+/g, " ").trim();
}

function PSS_LIVE_normalizarChaveImagem_(valor) {
  return PSS_LIVE_normalizarTextoImagem_(valor)
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function PSS_LIVE_hashImagem_(obj) {
  return Utilities.base64Encode(
    Utilities.computeDigest(
      Utilities.DigestAlgorithm.MD5,
      JSON.stringify(obj || {})
    )
  );
}

function PSS_LIVE_logImagem_(mensagem, nivel) {
  try {
    if (typeof logSistema === "function") {
      logSistema(mensagem, nivel || "INFO");
      return;
    }
  } catch (ignore) {}
  console.log("[" + (nivel || "INFO") + "] " + mensagem);
}

function PSS_LIVE_ehPublicacaoVisual_(texto) {
  var normalizado = PSS_LIVE_normalizarTextoImagem_(texto);
  if (!normalizado) return false;

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
    if (normalizado.indexOf(PSS_LIVE_normalizarTextoImagem_(marcadores[i])) !== -1) {
      return true;
    }
  }

  return /(?:SELECAO|TIME)\s+(?:ECONOMICO|INTERMEDIARIO|PONTUACAO)\s*[—-]\s*R\d+/i
    .test(normalizado);
}

function PSS_LIVE_configGithubImagem_(cfg) {
  cfg = cfg || {};

  var ativo = String(
    cfg.GITHUB_LIVE_ATIVO ||
    cfg.GITHUB_TESTE_ATIVO ||
    "NAO"
  ).trim().toUpperCase() === "SIM";

  var repo = String(
    cfg.GITHUB_LIVE_REPO ||
    cfg.GITHUB_TESTE_REPO ||
    cfg.GITHUB_REPO ||
    "portalsimonsports/cartola-engine"
  ).trim();

  var token = String(
    cfg.GITHUB_LIVE_TOKEN ||
    cfg.GITHUB_TESTE_TOKEN ||
    cfg.GITHUB_TOKEN ||
    ""
  ).trim();

  var apiBase = String(
    cfg.GITHUB_LIVE_API_BASE ||
    cfg.GITHUB_TESTE_API_BASE ||
    cfg.GITHUB_API_BASE ||
    "https://api.github.com"
  ).trim();

  var intervaloMin = Number(
    cfg.GITHUB_LIVE_INTERVALO_MIN ||
    cfg.GITHUB_TESTE_INTERVALO_MIN ||
    10
  );
  if (!intervaloMin || intervaloMin < 1) intervaloMin = 10;

  return {
    ativo: ativo,
    repo: repo,
    token: token,
    apiBase: apiBase,
    evento: "cartola_live_publish",
    workflow: "gerar.resultados.yml",
    intervaloMin: intervaloMin
  };
}

function PSS_LIVE_payloadTemConteudo_(tipoPublicacao, payload) {
  payload = payload || {};

  try {
    if (typeof psLivePayloadTemConteudoPublicavelGithub_ === "function") {
      return !!psLivePayloadTemConteudoPublicavelGithub_(tipoPublicacao, payload);
    }
  } catch (e) {
    PSS_LIVE_logImagem_(
      "Validação original do payload falhou; usando validação segura: " + e.message,
      "INFO"
    );
  }

  var tipo = PSS_LIVE_normalizarChaveImagem_(tipoPublicacao || "");

  if (tipo.indexOf("PLACAR") >= 0 || tipo.indexOf("RESULTADO") >= 0) {
    return !!(
      (Array.isArray(payload.partidas) && payload.partidas.length) ||
      (Array.isArray(payload.jogos) && payload.jogos.length) ||
      (Array.isArray(payload.resultados) && payload.resultados.length) ||
      String(payload.mensagem_oficial || "").trim()
    );
  }

  if (tipo.indexOf("RANKING") >= 0 || tipo.indexOf("MITOS") >= 0) {
    return !!(
      (Array.isArray(payload.top_5) && payload.top_5.length) ||
      (Array.isArray(payload.piores_5) && payload.piores_5.length) ||
      String(payload.mensagem_oficial || "").trim()
    );
  }

  if (tipo.indexOf("TOP5") >= 0) {
    return !!(
      (Array.isArray(payload.posicoes) && payload.posicoes.length) ||
      (Array.isArray(payload.lista) && payload.lista.length) ||
      String(payload.mensagem_oficial || "").trim()
    );
  }

  if (tipo.indexOf("TIME") >= 0 || tipo.indexOf("RESUMO") >= 0) {
    return !!(
      (Array.isArray(payload.tipos) && payload.tipos.length) ||
      (Array.isArray(payload.atletas) && payload.atletas.length) ||
      (Array.isArray(payload.jogadores) && payload.jogadores.length) ||
      String(payload.mensagem_oficial || "").trim()
    );
  }

  return !!(Object.keys(payload).length || String(payload.mensagem_oficial || "").trim());
}

function PSS_LIVE_dispararGithubImagem_(cfg, tipoPublicacao, payload) {
  try {
    cfg = cfg || {};
    payload = payload || {};

    var gh = PSS_LIVE_configGithubImagem_(cfg);

    if (!gh.ativo) {
      PSS_LIVE_logImagem_(
        "GitHub Live não enviado: GITHUB_TESTE_ATIVO/GITHUB_LIVE_ATIVO diferente de SIM.",
        "ERRO"
      );
      return false;
    }

    if (!gh.repo || !gh.token) {
      PSS_LIVE_logImagem_(
        "GitHub Live não enviado: repositório ou token ausente na CONFIG.",
        "ERRO"
      );
      return false;
    }

    if (!PSS_LIVE_payloadTemConteudo_(tipoPublicacao, payload)) {
      PSS_LIVE_logImagem_(
        "GitHub Live bloqueado: payload sem conteúdo publicável [" + tipoPublicacao + "].",
        "INFO"
      );
      return false;
    }

    var contexto = String(payload.contexto || "padrao").trim();
    var rodada = Number(payload.rodada || cfg.rodada_atual || cfg.RODADA_ATUAL || 0);
    var tipoSeguro = PSS_LIVE_normalizarChaveImagem_(tipoPublicacao || "GERAL");
    var contextoSeguro = PSS_LIVE_normalizarChaveImagem_(contexto || "PADRAO");

    var payloadInterno = Object.assign({}, payload, {
      origem: "cartola_live_publisher",
      tipo_publicacao: String(tipoPublicacao || ""),
      contexto: contexto,
      rodada: rodada
    });

    var payloadFinal = {
      origem: "cartola_live_publisher",
      ambiente: "producao",
      workflow_destino: gh.workflow,
      evento_github: gh.evento,
      tipo_publicacao: String(tipoPublicacao || ""),
      contexto: contexto,
      rodada: rodada,
      gerado_em: new Date().toISOString(),
      payload: payloadInterno
    };

    var hash = PSS_LIVE_hashImagem_(payloadFinal);
    payloadFinal.payload_hash = hash;

    var props = PropertiesService.getScriptProperties();
    var chaveBase = [
      "PSS_LIVE_GITHUB_IMAGEM",
      "R" + rodada,
      tipoSeguro || "GERAL",
      contextoSeguro || "PADRAO"
    ].join("_");

    var chaveTs = chaveBase + "_TS";
    var chaveHash = chaveBase + "_HASH";
    var agoraMs = Date.now();
    var ultimoTs = Number(props.getProperty(chaveTs) || 0);
    var ultimoHash = String(props.getProperty(chaveHash) || "");
    var diffMin = ultimoTs ? ((agoraMs - ultimoTs) / 60000) : 999999;

    if (ultimoHash === hash && diffMin < gh.intervaloMin) {
      PSS_LIVE_logImagem_(
        "GitHub Live bloqueado por duplicidade [" +
        tipoSeguro + "/" + contextoSeguro + "] R" + rodada +
        " | intervalo=" + diffMin.toFixed(2) + " min.",
        "INFO"
      );
      return false;
    }

    props.setProperty(chaveTs, String(agoraMs));
    props.setProperty(chaveHash, hash);

    var url = gh.apiBase.replace(/\/$/, "") +
      "/repos/" + gh.repo + "/dispatches";

    var resp = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      headers: {
        Authorization: "Bearer " + gh.token,
        Accept: "application/vnd.github+json"
      },
      payload: JSON.stringify({
        event_type: gh.evento,
        client_payload: payloadFinal
      }),
      muteHttpExceptions: true
    });

    var code = resp.getResponseCode();
    var resposta = resp.getContentText();
    var ok = code >= 200 && code < 300;

    PSS_LIVE_logImagem_(
      "GitHub Live imagem [" + tipoSeguro + "/" + contextoSeguro +
      "] HTTP " + code +
      " | evento=" + gh.evento +
      " | workflow=" + gh.workflow +
      " | resposta=" + resposta,
      ok ? "INFO" : "ERRO"
    );

    if (!ok) {
      props.deleteProperty(chaveTs);
      props.deleteProperty(chaveHash);
    }

    return ok;

  } catch (e) {
    PSS_LIVE_logImagem_(
      "ERRO no dispatch GitHub Live: " + (e && e.stack ? e.stack : e.message),
      "ERRO"
    );
    return false;
  }
}

function PSS_LIVE_enviarTelegramSomenteImagem_(cfg, texto) {
  texto = String(texto == null ? "" : texto).trim();
  if (!texto) return false;

  try {
    if (
      typeof psLiveBloquearMensagemTelegram_ === "function" &&
      psLiveBloquearMensagemTelegram_(texto)
    ) {
      return false;
    }
  } catch (ignore) {}

  if (PSS_LIVE_ehPublicacaoVisual_(texto)) {
    PSS_LIVE_logImagem_(
      "Texto direto bloqueado; card será publicado pelo GitHub: " +
      texto.substring(0, 160),
      "INFO"
    );
    return false;
  }

  if (typeof PSS_LIVE_ORIGINAL_ENVIAR_TELEGRAM_ === "function") {
    return PSS_LIVE_ORIGINAL_ENVIAR_TELEGRAM_(cfg, texto);
  }

  PSS_LIVE_logImagem_(
    "Mensagem curta não enviada: rota original enviarTelegram_ indisponível.",
    "ERRO"
  );
  return false;
}

enviarTelegram_ = PSS_LIVE_enviarTelegramSomenteImagem_;
dispararGithubTeste_ = PSS_LIVE_dispararGithubImagem_;

function PSS_LIVE_verificarModuloSomenteImagens() {
  var testes = [
    "🔥 MITOS E ZICAS DA RODADA\nParciais Gerais de Atletas",
    "🏟️ RESULTADOS E RESUMOS\nStatus dos Jogos da Rodada",
    "⚽ ATUALIZAÇÃO DE PLACAR",
    "TIME PONTUAÇÃO — R19",
    "Mensagem operacional curta"
  ];

  testes.forEach(function(texto) {
    console.log(JSON.stringify({
      texto: texto,
      bloqueadoComoTexto: PSS_LIVE_ehPublicacaoVisual_(texto)
    }));
  });

  console.log(
    "Override Telegram ativo=" +
    (enviarTelegram_ === PSS_LIVE_enviarTelegramSomenteImagem_)
  );
  console.log(
    "Override GitHub ativo=" +
    (dispararGithubTeste_ === PSS_LIVE_dispararGithubImagem_)
  );

  return true;
}
