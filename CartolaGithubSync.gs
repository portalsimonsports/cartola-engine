/**
 * CARTOLA GITHUB SYNC ENGINE v6
 * Portal SimonSports
 *
 * FLUXO OFICIAL:
 * - Google Apps Script atualiza os JSONs do GitHub sempre que os dados mudarem.
 * - Times e Top 5 NÃO são mais publicados em texto pelo jobTelegramDispatcher.
 * - O GitHub gera e publica as imagens somente nos eventos programados.
 *
 * Execute uma única vez:
 *   configurarPublicacaoSomenteImagensGithub()
 */

const CARTOLA_GH_SPREADSHEET_ID = "1-A7w4kkE28iHRd61yiSoNOvSekrmmADzHxGCRDVrICI";
const CARTOLA_GH_TIMEZONE = "America/Sao_Paulo";
const CARTOLA_GH_API_BASE = "https://api.github.com";
const CARTOLA_GH_INTERVALO_MIN = 5;

const CARTOLA_GH_EVENTOS = {
  SELECAO_INICIAL: true,
  ATUALIZACAO_20H: true,
  PRE_FECHAMENTO_TIMES: true,
  PRE_FECHAMENTO_TOP5: true,
  CONFIRMADOS: true
};

/* =========================================================
   INSTALAÇÃO / MIGRAÇÃO
========================================================= */

function configurarPublicacaoSomenteImagensGithub() {
  CARTOLA_GH_setConfig_("NOTIF_TIMES", "NAO");
  CARTOLA_GH_setConfig_("NOTIF_TOP5", "NAO");
  CARTOLA_GH_setConfig_("GITHUB_PUBLICAR_TIMES", "SIM");
  CARTOLA_GH_setConfig_("GITHUB_PUBLICAR_TOP5", "SIM");

  CARTOLA_GH_instalarAcionador_();
  CARTOLA_GH_limparFlagsScheduler_();

  var resultado = syncCartolaGithub();
  CARTOLA_GH_log_(
    "Migração concluída: Times e Top 5 em texto desativados; imagens programadas via GitHub ativadas.",
    "INFO"
  );
  return resultado;
}

function instalarAcionadorCartolaGithubProgramado() {
  return CARTOLA_GH_instalarAcionador_();
}

function removerAcionadorCartolaGithubProgramado() {
  var removidos = 0;
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    var nome = trigger.getHandlerFunction();
    if (nome === "jobCartolaGithubProgramado" || nome === "syncCartolaGithub") {
      ScriptApp.deleteTrigger(trigger);
      removidos++;
    }
  });
  return { ok: true, removidos: removidos };
}

function CARTOLA_GH_instalarAcionador_() {
  removerAcionadorCartolaGithubProgramado();

  var trigger = ScriptApp.newTrigger("jobCartolaGithubProgramado")
    .timeBased()
    .everyMinutes(CARTOLA_GH_INTERVALO_MIN)
    .create();

  CARTOLA_GH_log_(
    "Acionador instalado: jobCartolaGithubProgramado a cada " +
      CARTOLA_GH_INTERVALO_MIN + " minutos.",
    "INFO"
  );

  return { ok: true, trigger_id: trigger.getUniqueId() };
}

/* =========================================================
   SCHEDULER
========================================================= */

function jobCartolaGithubProgramado() {
  var estado = CARTOLA_GH_obterEstadoMercado_();
  if (!estado.rodada) {
    CARTOLA_GH_log_("Rodada atual não identificada.", "INFO");
    return { ok: false, motivo: "rodada_nao_identificada" };
  }

  var agora = new Date();
  var props = PropertiesService.getScriptProperties();
  var prefixo = "CARTOLA_GH_SCHED_R" + estado.rodada + "_";

  var getFlag = function(chave) {
    return props.getProperty(prefixo + chave) || "";
  };
  var setFlag = function(chave, valor) {
    props.setProperty(prefixo + chave, String(valor));
  };

  if (!estado.mercado_aberto) {
    return syncCartolaGithub();
  }

  var aberturaTs = Number(getFlag("ABERTURA_TS") || 0);
  if (!aberturaTs) {
    aberturaTs = CARTOLA_GH_obterAberturaLegada_(estado.rodada) || agora.getTime();
    setFlag("ABERTURA_TS", aberturaTs);
  }

  var fechamento = CARTOLA_GH_obterFechamento_(estado);
  var diffMin = fechamento
    ? (fechamento.getTime() - agora.getTime()) / 60000
    : null;

  var tempos = {
    desde_abertura: (agora.getTime() - aberturaTs) / 60000,
    ate_fechamento: diffMin
  };

  var publicarTimes = CARTOLA_GH_configSim_("GITHUB_PUBLICAR_TIMES", true);
  var publicarTop5 = CARTOLA_GH_configSim_("GITHUB_PUBLICAR_TOP5", true);
  var timesValidos = publicarTimes && CARTOLA_GH_temTimesValidos_(estado.rodada);
  var top5Valido = publicarTop5 && CARTOLA_GH_temTop5Valido_(estado.rodada);

  if (
    fechamento &&
    diffMin <= 25 &&
    diffMin > 0 &&
    getFlag("CONFIRMADOS") !== "1" &&
    (timesValidos || top5Valido)
  ) {
    var confirmado = syncCartolaGithub({
      publicar: true,
      evento_programado: "CONFIRMADOS",
      publicar_times: timesValidos,
      publicar_top5: top5Valido,
      forcar: true
    });
    if (CARTOLA_GH_publicou_(confirmado)) {
      setFlag("CONFIRMADOS", "1");
    }
    return { ok: true, evento: "CONFIRMADOS", tempos: tempos, resultado: confirmado };
  }

  if (
    fechamento &&
    diffMin <= 150 &&
    diffMin > 30 &&
    getFlag("PRE_FECHAMENTO_TIMES") !== "1" &&
    timesValidos
  ) {
    var preTimes = syncCartolaGithub({
      publicar: true,
      evento_programado: "PRE_FECHAMENTO_TIMES",
      publicar_times: true,
      publicar_top5: false,
      forcar: true
    });
    if (CARTOLA_GH_publicouTimes_(preTimes)) {
      setFlag("PRE_FECHAMENTO_TIMES", "1");
    }
    return {
      ok: true,
      evento: "PRE_FECHAMENTO_TIMES",
      tempos: tempos,
      resultado: preTimes
    };
  }

  if (
    fechamento &&
    diffMin <= 120 &&
    diffMin > 30 &&
    getFlag("PRE_FECHAMENTO_TOP5") !== "1" &&
    top5Valido
  ) {
    var preTop5 = syncCartolaGithub({
      publicar: true,
      evento_programado: "PRE_FECHAMENTO_TOP5",
      publicar_times: false,
      publicar_top5: true,
      forcar: true
    });
    if (CARTOLA_GH_publicouTop5_(preTop5)) {
      setFlag("PRE_FECHAMENTO_TOP5", "1");
    }
    return {
      ok: true,
      evento: "PRE_FECHAMENTO_TOP5",
      tempos: tempos,
      resultado: preTop5
    };
  }

  if (
    tempos.desde_abertura >= 30 &&
    getFlag("SELECAO_INICIAL") !== "1" &&
    (timesValidos || top5Valido)
  ) {
    var inicial = syncCartolaGithub({
      publicar: true,
      evento_programado: "SELECAO_INICIAL",
      publicar_times: timesValidos,
      publicar_top5: top5Valido,
      forcar: true
    });
    if (CARTOLA_GH_publicou_(inicial)) {
      setFlag("SELECAO_INICIAL", "1");
    }
    return { ok: true, evento: "SELECAO_INICIAL", tempos: tempos, resultado: inicial };
  }

  if (
    getFlag("SELECAO_INICIAL") === "1" &&
    CARTOLA_GH_pode20h_(agora, fechamento, getFlag) &&
    (timesValidos || top5Valido)
  ) {
    var vinteHoras = syncCartolaGithub({
      publicar: true,
      evento_programado: "ATUALIZACAO_20H",
      publicar_times: timesValidos,
      publicar_top5: top5Valido,
      forcar: true
    });
    if (CARTOLA_GH_publicou_(vinteHoras)) {
      setFlag(
        "ULTIMA_20H_DATA",
        Utilities.formatDate(agora, CARTOLA_GH_TIMEZONE, "yyyy-MM-dd")
      );
    }
    return { ok: true, evento: "ATUALIZACAO_20H", tempos: tempos, resultado: vinteHoras };
  }

  return {
    ok: true,
    evento: "",
    tempos: tempos,
    resultado: syncCartolaGithub()
  };
}

function CARTOLA_GH_pode20h_(agora, fechamento, getFlag) {
  if (!fechamento) return false;

  var hoje = Utilities.formatDate(agora, CARTOLA_GH_TIMEZONE, "yyyy-MM-dd");
  var diaFechamento = Utilities.formatDate(
    fechamento,
    CARTOLA_GH_TIMEZONE,
    "yyyy-MM-dd"
  );

  if (hoje === diaFechamento) return false;
  if (getFlag("ULTIMA_20H_DATA") === hoje) return false;

  var hora = Number(
    Utilities.formatDate(agora, CARTOLA_GH_TIMEZONE, "H")
  );
  return hora >= 20;
}

/* =========================================================
   SINCRONIZAÇÃO
========================================================= */

function syncCartolaGithub(opcoes) {
  opcoes = opcoes || {};

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    return { ok: false, motivo: "lock_ocupado" };
  }

  try {
    var evento = CARTOLA_GH_normalizar_(opcoes.evento_programado || "");
    var publicar = !!opcoes.publicar && !!CARTOLA_GH_EVENTOS[evento];

    var contexto = {
      publicar: publicar,
      evento_programado: publicar ? evento : "",
      publicar_times: publicar && opcoes.publicar_times !== false,
      publicar_top5: publicar && opcoes.publicar_top5 !== false,
      forcar: !!opcoes.forcar
    };

    var times = CARTOLA_GH_processarTimes_(contexto);
    var top5 = CARTOLA_GH_processarTop5_(contexto);

    var resumo = {
      ok: true,
      executado_em: new Date().toISOString(),
      evento_programado: contexto.evento_programado,
      times: times,
      top5: top5
    };

    CARTOLA_GH_log_(
      "syncCartolaGithub concluído: " + JSON.stringify(resumo),
      "INFO"
    );
    return resumo;
  } catch (erro) {
    CARTOLA_GH_log_("ERRO syncCartolaGithub: " + erro.message, "ERRO");
    throw erro;
  } finally {
    lock.releaseLock();
  }
}

function forcarSyncCartolaGithub() {
  return syncCartolaGithub({ forcar: true });
}

function publicarTesteImagensGithub() {
  return syncCartolaGithub({
    publicar: true,
    evento_programado: "SELECAO_INICIAL",
    publicar_times: true,
    publicar_top5: true,
    forcar: true
  });
}

/* =========================================================
   TIMES
========================================================= */

function CARTOLA_GH_processarTimes_(ctx) {
  var ss = SpreadsheetApp.openById(CARTOLA_GH_SPREADSHEET_ID);
  var sh = ss.getSheetByName("TIMES_ATUAL");
  if (!sh || sh.getLastRow() < 2) return [];

  var tabela = CARTOLA_GH_lerTabela_(sh);
  var iRodada = tabela.indices.RODADA;
  var iTipo = tabela.indices.TIPO_TIME;
  if (iTipo === undefined) iTipo = tabela.indices.TIPO;

  if (iRodada === undefined || iTipo === undefined) {
    throw new Error("TIMES_ATUAL sem RODADA e TIPO_TIME/TIPO.");
  }

  var rodada = CARTOLA_GH_maiorNumero_(
    tabela.rows.map(function(row) { return row[iRodada]; })
  );
  if (!rodada) return [];

  var tipos = CARTOLA_GH_unicos_(
    tabela.rows
      .filter(function(row) { return Number(row[iRodada]) === Number(rodada); })
      .map(function(row) { return CARTOLA_GH_texto_(row[iTipo]).trim().toUpperCase(); })
      .filter(function(tipo) { return !!tipo; })
  );

  var props = PropertiesService.getScriptProperties();
  var resultados = [];
  var arquivos = {};

  tipos.forEach(function(tipo) {
    var atletas = tabela.rows
      .filter(function(row) {
        return (
          Number(row[iRodada]) === Number(rodada) &&
          CARTOLA_GH_texto_(row[iTipo]).trim().toUpperCase() === tipo
        );
      })
      .map(function(row) {
        return CARTOLA_GH_objetoLinha_(
          tabela.headers,
          row,
          ["DATA", "ATUALIZADO_EM"]
        );
      });

    if (!atletas.length) return;

    var meta = CARTOLA_GH_lerMetaTime_(ss, rodada, tipo, atletas);
    var slug = CARTOLA_GH_slug_(tipo);
    var caminho = "data/times_atual_" + slug + ".json";
    var chaveHash = "CARTOLA_GH_HASH_TIME_" + tipo;
    var hash = CARTOLA_GH_hash_({
      rodada: rodada,
      tipo: tipo,
      atletas: atletas,
      meta: meta
    });
    var alterado = props.getProperty(chaveHash) !== hash;

    var base = {
      origem: "syncCartolaGithub",
      pipeline: "jobtelegram",
      tipo_publicacao: "times",
      rodada: Number(rodada),
      tipo: tipo,
      modelo: tipo,
      nome_modelo: CARTOLA_GH_nomeModelo_(tipo),
      atualizado_em: new Date().toISOString(),
      formacao: meta.esquema || "",
      capitao: meta.capitao || "",
      custo_total: Number(meta.custo_total || 0),
      dados: atletas
    };

    var upload = null;
    if (alterado || ctx.forcar) {
      upload = CARTOLA_GH_subirArquivo_(
        JSON.stringify(base, null, 2),
        caminho,
        "Cartola: " + tipo + " rodada " + rodada
      );
      props.setProperty(chaveHash, hash);
    }

    var dispatch = null;
    if (ctx.publicar && ctx.publicar_times) {
      dispatch = CARTOLA_GH_dispatch_(
        "times",
        ctx.evento_programado,
        {
          tipo_publicacao: "times",
          rodada: Number(rodada),
          tipo: tipo,
          modelo: tipo,
          nome_modelo: CARTOLA_GH_nomeModelo_(tipo),
          titulo: CARTOLA_GH_nomeModelo_(tipo) + " • RODADA " + rodada,
          blocos_topo: [
            CARTOLA_GH_rotuloEvento_(ctx.evento_programado)
          ],
          atletas: atletas,
          meta: meta,
          formacao: meta.esquema || "",
          capitao: meta.capitao || "",
          custo_total: Number(meta.custo_total || 0),
          arquivo_json: caminho
        }
      );
    }

    arquivos[slug] = caminho;
    resultados.push({
      tipo: tipo,
      rodada: Number(rodada),
      alterado: alterado,
      arquivo: caminho,
      upload: upload ? upload.ok : false,
      dispatch: dispatch ? dispatch.ok : false
    });
  });

  if (Object.keys(arquivos).length) {
    CARTOLA_GH_subirArquivo_(
      JSON.stringify({
        origem: "syncCartolaGithub",
        rodada: Number(rodada),
        atualizado_em: new Date().toISOString(),
        arquivos: arquivos,
        modelos: tipos
      }, null, 2),
      "data/times_atual.json",
      "Cartola: consolidado de times rodada " + rodada
    );
  }

  return resultados;
}

/* =========================================================
   TOP 5
========================================================= */

function CARTOLA_GH_processarTop5_(ctx) {
  var ss = SpreadsheetApp.openById(CARTOLA_GH_SPREADSHEET_ID);
  var sh = ss.getSheetByName("TOP5_ATUAL");
  if (!sh || sh.getLastRow() < 2) {
    return { alterado: false, motivo: "sem_dados" };
  }

  var tabela = CARTOLA_GH_lerTabela_(sh);
  var iRodada = tabela.indices.RODADA;
  if (iRodada === undefined) {
    throw new Error("TOP5_ATUAL sem coluna RODADA.");
  }

  var rodada = CARTOLA_GH_maiorNumero_(
    tabela.rows.map(function(row) { return row[iRodada]; })
  );
  if (!rodada) return { alterado: false, motivo: "sem_rodada" };

  var lista = tabela.rows
    .filter(function(row) { return Number(row[iRodada]) === Number(rodada); })
    .map(function(row) {
      return CARTOLA_GH_objetoLinha_(
        tabela.headers,
        row,
        ["DATA", "ATUALIZADO_EM"]
      );
    });

  if (!lista.length) return { alterado: false, motivo: "sem_lista" };

  var props = PropertiesService.getScriptProperties();
  var hash = CARTOLA_GH_hash_({ rodada: rodada, lista: lista });
  var alterado = props.getProperty("CARTOLA_GH_HASH_TOP5") !== hash;
  var caminho = "data/top5_atual.json";

  var upload = null;
  if (alterado || ctx.forcar) {
    upload = CARTOLA_GH_subirArquivo_(
      JSON.stringify({
        origem: "syncCartolaGithub",
        pipeline: "jobtelegram",
        tipo_publicacao: "top5",
        rodada: Number(rodada),
        atualizado_em: new Date().toISOString(),
        dados: lista
      }, null, 2),
      caminho,
      "Cartola: Top 5 rodada " + rodada
    );
    props.setProperty("CARTOLA_GH_HASH_TOP5", hash);
  }

  var dispatch = null;
  if (ctx.publicar && ctx.publicar_top5) {
    dispatch = CARTOLA_GH_dispatch_(
      "top5",
      ctx.evento_programado,
      {
        tipo_publicacao: "top5",
        rodada: Number(rodada),
        titulo: "TOP 5 DA RODADA",
        blocos_topo: [
          CARTOLA_GH_rotuloEvento_(ctx.evento_programado)
        ],
        lista: lista,
        arquivo_json: caminho
      }
    );
  }

  return {
    alterado: alterado,
    rodada: Number(rodada),
    arquivo: caminho,
    upload: upload ? upload.ok : false,
    dispatch: dispatch ? dispatch.ok : false
  };
}

/* =========================================================
   GITHUB
========================================================= */

function CARTOLA_GH_dispatch_(tipo, evento, payload) {
  var cfg = CARTOLA_GH_configGithub_();
  if (!cfg.ativo) {
    return { ok: false, motivo: "github_inativo" };
  }
  if (!cfg.repo || !cfg.token) {
    throw new Error("GitHub sem repositório ou token.");
  }

  var eventType = tipo === "top5"
    ? cfg.evento_top5
    : cfg.evento_times;

  var body = {
    event_type: eventType,
    client_payload: {
      origem: "jobCartolaGithubProgramado",
      pipeline: "jobtelegram",
      tipo_publicacao: tipo,
      rodada: payload.rodada || null,
      gerado_em: new Date().toISOString(),
      evento_programado: evento,
      payload: payload
    }
  };

  var resp = UrlFetchApp.fetch(
    cfg.api_base.replace(/\/$/, "") +
      "/repos/" + cfg.repo + "/dispatches",
    {
      method: "post",
      contentType: "application/json",
      headers: {
        Authorization: "Bearer " + cfg.token,
        Accept: "application/vnd.github+json"
      },
      payload: JSON.stringify(body),
      muteHttpExceptions: true
    }
  );

  var code = resp.getResponseCode();
  var ok = code >= 200 && code < 300;
  CARTOLA_GH_log_(
    "Dispatch " + tipo + " / " + evento +
      " HTTP " + code + ": " + resp.getContentText(),
    ok ? "INFO" : "ERRO"
  );

  return {
    ok: ok,
    codigo: code,
    resposta: resp.getContentText()
  };
}

function CARTOLA_GH_subirArquivo_(conteudo, caminho, mensagem) {
  var cfg = CARTOLA_GH_configGithub_();
  if (!cfg.repo || !cfg.token || !cfg.branch) {
    throw new Error("Configuração GitHub incompleta.");
  }

  var path = caminho
    .split("/")
    .map(function(parte) { return encodeURIComponent(parte); })
    .join("/");

  var url =
    cfg.api_base.replace(/\/$/, "") +
    "/repos/" + cfg.repo + "/contents/" + path;

  var sha = "";
  var consulta = UrlFetchApp.fetch(
    url + "?ref=" + encodeURIComponent(cfg.branch),
    {
      method: "get",
      headers: {
        Authorization: "Bearer " + cfg.token,
        Accept: "application/vnd.github+json"
      },
      muteHttpExceptions: true
    }
  );

  if (consulta.getResponseCode() === 200) {
    sha = (CARTOLA_GH_parseJson_(consulta.getContentText()).sha || "");
  } else if (consulta.getResponseCode() !== 404) {
    throw new Error(
      "Falha ao consultar " + caminho +
      ": HTTP " + consulta.getResponseCode()
    );
  }

  var body = {
    message: mensagem,
    content: Utilities.base64Encode(
      Utilities.newBlob(conteudo).getBytes()
    ),
    branch: cfg.branch
  };
  if (sha) body.sha = sha;

  var gravacao = UrlFetchApp.fetch(url, {
    method: "put",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + cfg.token,
      Accept: "application/vnd.github+json"
    },
    payload: JSON.stringify(body),
    muteHttpExceptions: true
  });

  var code = gravacao.getResponseCode();
  var ok = code >= 200 && code < 300;
  if (!ok) {
    throw new Error(
      "Falha ao gravar " + caminho +
      ": HTTP " + code + " - " + gravacao.getContentText()
    );
  }

  CARTOLA_GH_log_(
    "Arquivo enviado ao GitHub: " + caminho + " | HTTP " + code,
    "INFO"
  );
  return { ok: true, codigo: code };
}

function CARTOLA_GH_configGithub_() {
  var repo = CARTOLA_GH_texto_(
    CARTOLA_GH_getConfig_("GITHUB_REPO") ||
    CARTOLA_GH_getConfig_("GITHUB_DISPATCH_REPO") ||
    CARTOLA_GH_getConfig_("GITHUB_TESTE_REPO")
  ).trim();

  var token = CARTOLA_GH_texto_(
    CARTOLA_GH_getConfig_("GITHUB_TOKEN") ||
    CARTOLA_GH_getConfig_("GITHUB_DISPATCH_TOKEN") ||
    CARTOLA_GH_getConfig_("GITHUB_TESTE_TOKEN")
  ).trim();

  var ativoBruto = CARTOLA_GH_texto_(
    CARTOLA_GH_getConfig_("GITHUB_DISPATCH_ATIVO") ||
    CARTOLA_GH_getConfig_("GITHUB_TESTE_ATIVO") ||
    "SIM"
  ).trim().toUpperCase();

  return {
    ativo: ativoBruto === "SIM",
    repo: repo,
    token: token,
    branch: CARTOLA_GH_texto_(
      CARTOLA_GH_getConfig_("GITHUB_BRANCH") || "main"
    ).trim(),
    api_base: CARTOLA_GH_texto_(
      CARTOLA_GH_getConfig_("GITHUB_API_BASE") ||
      CARTOLA_GH_getConfig_("GITHUB_TESTE_API_BASE") ||
      CARTOLA_GH_API_BASE
    ).trim(),
    evento_times: CARTOLA_GH_texto_(
      CARTOLA_GH_getConfig_("GITHUB_EVENTO_TIMES") ||
      "cartola_publish_times"
    ).trim(),
    evento_top5: CARTOLA_GH_texto_(
      CARTOLA_GH_getConfig_("GITHUB_EVENTO_TOP5") ||
      "cartola_publish_top5"
    ).trim()
  };
}

/* =========================================================
   DADOS / VALIDAÇÃO
========================================================= */

function CARTOLA_GH_temTimesValidos_(rodada) {
  var sh = SpreadsheetApp.openById(
    CARTOLA_GH_SPREADSHEET_ID
  ).getSheetByName("TIMES_ATUAL");
  if (!sh || sh.getLastRow() < 2) return false;

  var tabela = CARTOLA_GH_lerTabela_(sh);
  var iRodada = tabela.indices.RODADA;
  var iTipo = tabela.indices.TIPO_TIME;
  if (iTipo === undefined) iTipo = tabela.indices.TIPO;
  var iStatus = tabela.indices.STATUS;

  if (iRodada === undefined || iTipo === undefined) return false;

  var contagem = {};
  tabela.rows.forEach(function(row) {
    if (Number(row[iRodada]) !== Number(rodada)) return;
    var tipo = CARTOLA_GH_texto_(row[iTipo]).trim().toUpperCase();
    if (!tipo) return;

    var status = iStatus === undefined
      ? "TITULAR"
      : CARTOLA_GH_texto_(row[iStatus]).trim().toUpperCase();

    if (status === "TITULAR" || status.indexOf("RESERV") === 0) {
      contagem[tipo] = Number(contagem[tipo] || 0) + 1;
    }
  });

  return ["ECONOMICO", "INTERMEDIARIO", "PONTUACAO"].every(
    function(tipo) {
      return Number(contagem[tipo] || 0) >= 12;
    }
  );
}

function CARTOLA_GH_temTop5Valido_(rodada) {
  var sh = SpreadsheetApp.openById(
    CARTOLA_GH_SPREADSHEET_ID
  ).getSheetByName("TOP5_ATUAL");
  if (!sh || sh.getLastRow() < 2) return false;

  var tabela = CARTOLA_GH_lerTabela_(sh);
  var iRodada = tabela.indices.RODADA;
  var iPos = tabela.indices.POS;
  if (iPos === undefined) iPos = tabela.indices.POSICAO;
  if (iRodada === undefined || iPos === undefined) return false;

  var contagem = { GOL: 0, LAT: 0, ZAG: 0, MEI: 0, ATA: 0, TEC: 0 };
  tabela.rows.forEach(function(row) {
    if (Number(row[iRodada]) !== Number(rodada)) return;
    var pos = CARTOLA_GH_normalizar_(row[iPos]);
    if (contagem.hasOwnProperty(pos)) contagem[pos]++;
  });

  return Object.keys(contagem).every(function(pos) {
    return contagem[pos] >= 5;
  });
}

function CARTOLA_GH_lerMetaTime_(ss, rodada, tipo, atletas) {
  var meta = {
    custo_total: 0,
    pontos_total: 0,
    variacao_total: 0,
    capitao: "",
    esquema: ""
  };

  var sh = ss.getSheetByName("HIST_TIMES");
  if (sh && sh.getLastRow() >= 2) {
    var tabela = CARTOLA_GH_lerTabela_(sh);
    var I = tabela.indices;

    for (var i = tabela.rows.length - 1; i >= 0; i--) {
      var row = tabela.rows[i];
      var tipoLinha = CARTOLA_GH_texto_(
        I.TIPO_TIME !== undefined ? row[I.TIPO_TIME] :
        (I.TIPO !== undefined ? row[I.TIPO] : "")
      ).trim().toUpperCase();

      if (
        I.RODADA !== undefined &&
        Number(row[I.RODADA]) === Number(rodada) &&
        tipoLinha === tipo
      ) {
        meta.custo_total = Number(
          I.CUSTO_TOTAL !== undefined ? row[I.CUSTO_TOTAL] : 0
        );
        meta.pontos_total = Number(
          I.PONTOS_TOTAL !== undefined ? row[I.PONTOS_TOTAL] : 0
        );
        meta.variacao_total = Number(
          I.VARIACAO_TOTAL !== undefined ? row[I.VARIACAO_TOTAL] : 0
        );
        meta.capitao = CARTOLA_GH_texto_(
          I.CAPITAO_SUGERIDO !== undefined ? row[I.CAPITAO_SUGERIDO] :
          (I.CAPITAO !== undefined ? row[I.CAPITAO] : "")
        );
        meta.esquema = CARTOLA_GH_texto_(
          I.ESQUEMA !== undefined ? row[I.ESQUEMA] :
          (I.FORMACAO !== undefined ? row[I.FORMACAO] : "")
        );
        break;
      }
    }
  }

  if (!meta.custo_total) {
    atletas.forEach(function(atleta) {
      var status = CARTOLA_GH_texto_(
        atleta.STATUS || atleta.status
      ).toUpperCase();
      if (status === "TITULAR") {
        meta.custo_total += Number(
          atleta.PRECO || atleta.preco || 0
        );
      }
    });
  }

  return meta;
}

function CARTOLA_GH_obterEstadoMercado_() {
  var st = {};
  try {
    if (typeof apiGetComCache_ === "function") {
      st = apiGetComCache_("/mercado/status") || {};
    }
  } catch (erroApi) {}

  var rodada = Number(
    st.rodada_atual ||
    CARTOLA_GH_getConfig_("rodada_atual") ||
    CARTOLA_GH_getConfig_("RODADA_ATUAL") ||
    0
  );

  var status = Number(
    st.status_mercado ||
    CARTOLA_GH_getConfig_("status_rodada") ||
    CARTOLA_GH_getConfig_("STATUS_RODADA") ||
    0
  );

  return {
    rodada: rodada,
    status_mercado: status,
    mercado_aberto: status === 1,
    bruto: st
  };
}

function CARTOLA_GH_obterFechamento_(estado) {
  try {
    if (typeof psObterFechamentoMercadoSeguro_ === "function") {
      var dataHelper = psObterFechamentoMercadoSeguro_(
        SpreadsheetApp.openById(CARTOLA_GH_SPREADSHEET_ID),
        estado.bruto || {}
      );
      if (dataHelper && !isNaN(dataHelper.getTime())) {
        return dataHelper;
      }
    }
  } catch (erroHelper) {}

  var bruto = CARTOLA_GH_texto_(
    CARTOLA_GH_getConfig_("fechamento_mercado") ||
    CARTOLA_GH_getConfig_("FECHAMENTO_MERCADO")
  ).trim();

  var m = bruto.match(
    /^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/
  );
  if (m) {
    return new Date(
      Number(m[3]),
      Number(m[2]) - 1,
      Number(m[1]),
      Number(m[4]),
      Number(m[5]),
      Number(m[6] || 0),
      0
    );
  }

  var data = bruto ? new Date(bruto) : null;
  return data && !isNaN(data.getTime()) ? data : null;
}

function CARTOLA_GH_obterAberturaLegada_(rodada) {
  try {
    if (typeof getFlagsRodada_ === "function") {
      var flags = getFlagsRodada_(rodada) || {};
      return Number(flags.timestamp_abertura || 0);
    }
  } catch (erro) {}
  return 0;
}

/* =========================================================
   CONFIG / HELPERS
========================================================= */

function CARTOLA_GH_getConfig_(chave) {
  var sh = SpreadsheetApp.openById(
    CARTOLA_GH_SPREADSHEET_ID
  ).getSheetByName("CONFIG");

  if (!sh || sh.getLastRow() < 2) return null;

  var valores = sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues();
  var alvo = CARTOLA_GH_texto_(chave).trim().toUpperCase();

  for (var i = 0; i < valores.length; i++) {
    if (
      CARTOLA_GH_texto_(valores[i][0]).trim().toUpperCase() === alvo
    ) {
      return valores[i][1];
    }
  }
  return null;
}

function CARTOLA_GH_setConfig_(chave, valor) {
  var sh = SpreadsheetApp.openById(
    CARTOLA_GH_SPREADSHEET_ID
  ).getSheetByName("CONFIG");

  if (!sh) throw new Error("Aba CONFIG não encontrada.");

  var alvo = CARTOLA_GH_texto_(chave).trim().toUpperCase();
  var lastRow = sh.getLastRow();

  if (lastRow >= 2) {
    var valores = sh.getRange(2, 1, lastRow - 1, 2).getValues();
    for (var i = 0; i < valores.length; i++) {
      if (
        CARTOLA_GH_texto_(valores[i][0]).trim().toUpperCase() === alvo
      ) {
        sh.getRange(i + 2, 2).setValue(valor);
        return;
      }
    }
  }

  sh.appendRow([chave, valor]);
}

function CARTOLA_GH_configSim_(chave, padrao) {
  var valor = CARTOLA_GH_getConfig_(chave);
  if (valor === null || valor === undefined || valor === "") {
    return !!padrao;
  }
  return CARTOLA_GH_texto_(valor).trim().toUpperCase() === "SIM";
}

function CARTOLA_GH_lerTabela_(sh) {
  var dados = sh.getDataRange().getValues();
  var headers = (dados[0] || []).map(function(item) {
    return CARTOLA_GH_texto_(item).trim();
  });
  var indices = {};

  headers.forEach(function(header, index) {
    var normalizado = CARTOLA_GH_normalizar_(header);
    if (normalizado && indices[normalizado] === undefined) {
      indices[normalizado] = index;
    }
  });

  return {
    headers: headers,
    indices: indices,
    rows: dados.slice(1)
  };
}

function CARTOLA_GH_objetoLinha_(headers, row, ignoradas) {
  var ignorar = {};
  (ignoradas || []).forEach(function(chave) {
    ignorar[CARTOLA_GH_normalizar_(chave)] = true;
  });

  var obj = {};
  headers.forEach(function(header, index) {
    if (!header || ignorar[CARTOLA_GH_normalizar_(header)]) return;
    var valor = row[index];

    if (valor instanceof Date) {
      valor = Utilities.formatDate(
        valor,
        CARTOLA_GH_TIMEZONE,
        "yyyy-MM-dd'T'HH:mm:ssXXX"
      );
    }
    obj[header] = valor;
  });
  return obj;
}

function CARTOLA_GH_normalizar_(valor) {
  var texto = CARTOLA_GH_texto_(valor).trim().toUpperCase();
  try {
    texto = texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } catch (erro) {}
  return texto.replace(/\s+/g, "_");
}

function CARTOLA_GH_slug_(valor) {
  return CARTOLA_GH_normalizar_(valor)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function CARTOLA_GH_texto_(valor) {
  return String(valor === null || valor === undefined ? "" : valor);
}

function CARTOLA_GH_parseJson_(texto) {
  try {
    return JSON.parse(CARTOLA_GH_texto_(texto) || "{}");
  } catch (erro) {
    return {};
  }
}

function CARTOLA_GH_maiorNumero_(valores) {
  var numeros = (valores || [])
    .map(function(valor) { return Number(valor); })
    .filter(function(valor) { return !isNaN(valor) && valor > 0; });

  return numeros.length ? Math.max.apply(null, numeros) : 0;
}

function CARTOLA_GH_unicos_(valores) {
  var mapa = {};
  return (valores || []).filter(function(valor) {
    var chave = CARTOLA_GH_texto_(valor);
    if (mapa[chave]) return false;
    mapa[chave] = true;
    return true;
  });
}

function CARTOLA_GH_hash_(obj) {
  return Utilities.base64Encode(
    Utilities.computeDigest(
      Utilities.DigestAlgorithm.MD5,
      JSON.stringify(obj)
    )
  );
}

function CARTOLA_GH_nomeModelo_(tipo) {
  var nomes = {
    ECONOMICO: "TIME ECONÔMICO",
    INTERMEDIARIO: "TIME INTERMEDIÁRIO",
    PONTUACAO: "TIME PARA PONTUAR"
  };
  return nomes[tipo] || ("TIME " + tipo);
}

function CARTOLA_GH_rotuloEvento_(evento) {
  var rotulos = {
    SELECAO_INICIAL: "Seleção inicial da rodada",
    ATUALIZACAO_20H: "Atualização programada das 20h",
    PRE_FECHAMENTO_TIMES: "Pré-fechamento dos times",
    PRE_FECHAMENTO_TOP5: "Pré-fechamento do Top 5",
    CONFIRMADOS: "Seleções confirmadas"
  };
  return rotulos[evento] || evento;
}

function CARTOLA_GH_publicou_(resultado) {
  return (
    CARTOLA_GH_publicouTimes_(resultado) ||
    CARTOLA_GH_publicouTop5_(resultado)
  );
}

function CARTOLA_GH_publicouTimes_(resultado) {
  return !!(
    resultado &&
    Array.isArray(resultado.times) &&
    resultado.times.some(function(item) { return !!item.dispatch; })
  );
}

function CARTOLA_GH_publicouTop5_(resultado) {
  return !!(
    resultado &&
    resultado.top5 &&
    resultado.top5.dispatch
  );
}

function CARTOLA_GH_limparFlagsScheduler_() {
  var props = PropertiesService.getScriptProperties();
  var valores = props.getProperties();

  Object.keys(valores).forEach(function(chave) {
    if (
      chave.indexOf("CARTOLA_GH_SCHED_") === 0 ||
      chave.indexOf("CARTOLA_GH_HASH_") === 0
    ) {
      props.deleteProperty(chave);
    }
  });
}

function CARTOLA_GH_log_(mensagem, nivel) {
  if (typeof logSistema === "function") {
    try {
      logSistema(mensagem, nivel || "INFO");
      return;
    } catch (erro) {}
  }
  Logger.log("[" + (nivel || "INFO") + "] " + mensagem);
}
