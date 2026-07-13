/**
 * CARTOLA GITHUB SYNC ENGINE v3
 * Portal SimonSports
 *
 * Objetivo:
 * 1) Ler TIMES_ATUAL e TOP5_ATUAL da rodada mais recente
 * 2) Gerar JSONs normalizados no GitHub apenas quando houver alteração real
 * 3) Disparar repository_dispatch para o GitHub gerar imagem/publicação
 * 4) Receber callback por webhook e publicar no Telegram com foto e/ou texto
 *
 * Compatível com os fluxos de jobtelegram e live publisher.
 *
 * GitHub: grava as bases atuais diretamente em data/ e dispara
 * cartola_publish_times / cartola_publish_top5 automaticamente.
 */

const SPREADSHEET_ID = "1-A7w4kkE28iHRd61yiSoNOvSekrmmADzHxGCRDVrICI";
const COFRE_ID = "1Lcb6kLFGdMSRNsG_yCCGjToHx2nLk0UaPdvA9Gf8Dx8";
const COFRE_SHEET = "Telegram_Cartola";
const TIMEZONE_PADRAO = "America/Sao_Paulo";
const GITHUB_API_BASE_PADRAO = "https://api.github.com";

/* =========================
   FUNÇÃO PRINCIPAL
   (usar gatilho time-driven)
========================= */

function syncCartolaGithub() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) {
    logSistemaLocal("syncCartolaGithub: não foi possível obter lock.", "INFO");
    return {
      ok: false,
      motivo: "lock_ocupado"
    };
  }

  try {
    var resumo = {
      ok: true,
      executado_em: new Date().toISOString(),
      times: processarTimesAtual(),
      top5: processarTop5()
    };

    logSistemaLocal("syncCartolaGithub concluído: " + JSON.stringify(resumo), "INFO");
    return resumo;
  } catch (e) {
    logSistemaLocal("ERRO syncCartolaGithub: " + e.message, "ERRO");
    throw e;
  } finally {
    lock.releaseLock();
  }
}

/* =========================
   PROCESSA TIMES_ATUAL
========================= */

function processarTimesAtual() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sh = ss.getSheetByName("TIMES_ATUAL");
  if (!sh || sh.getLastRow() < 2) {
    logSistemaLocal("processarTimesAtual: aba TIMES_ATUAL inexistente ou vazia.", "INFO");
    return [];
  }

  var tabela = lerTabelaAba(sh);
  var idxRodada = tabela.indices["RODADA"];
  var idxTipo = tabela.indices["TIPO_TIME"];

  if (idxRodada === undefined || idxTipo === undefined) {
    throw new Error("TIMES_ATUAL sem colunas obrigatórias RODADA/TIPO_TIME.");
  }

  var rowsValidas = tabela.rows.filter(function(row) {
    return isNumeroValido(row[idxRodada]) && textoSeguro(row[idxTipo]).trim() !== "";
  });

  if (!rowsValidas.length) {
    logSistemaLocal("processarTimesAtual: nenhuma linha válida encontrada.", "INFO");
    return [];
  }

  var rodadaAtual = obterMaiorNumero(rowsValidas.map(function(row) {
    return row[idxRodada];
  }));

  if (!isNumeroValido(rodadaAtual)) {
    throw new Error("Não foi possível determinar a rodada atual em TIMES_ATUAL.");
  }

  var tipos = obterValoresUnicos(rowsValidas
    .filter(function(row) { return Number(row[idxRodada]) === Number(rodadaAtual); })
    .map(function(row) { return textoSeguro(row[idxTipo]).trim(); }))
    .filter(function(tipo) { return !!tipo; });

  var props = PropertiesService.getScriptProperties();
  var resultado = [];

  tipos.forEach(function(tipo) {
    var filtrado = rowsValidas
      .filter(function(row) {
        return Number(row[idxRodada]) === Number(rodadaAtual) && textoSeguro(row[idxTipo]).trim() === tipo;
      })
      .map(function(row) {
        return montarObjetoLinha(tabela.headersOriginais, row, ["DATA", "ATUALIZADO_EM"]);
      });

    if (!filtrado.length) return;

    var chaveTipo = slugSeguro(tipo).toUpperCase();
    var hashBase = {
      rodada: Number(rodadaAtual),
      tipo: tipo,
      dados: filtrado
    };
    var hashAtual = gerarHash(hashBase);
    var chaveHash = "HASH_TIMES_" + chaveTipo;
    var hashAnterior = props.getProperty(chaveHash);

    if (hashAnterior === hashAtual) {
      resultado.push({
        tipo: tipo,
        rodada: Number(rodadaAtual),
        alterado: false,
        arquivo: "data/times_atual_" + slugSeguro(tipo) + ".json",
        dispatch: false
      });
      return;
    }

    var jsonObj = {
      origem: "syncCartolaGithub",
      pipeline: "jobtelegram",
      tipo_publicacao: "times",
      rodada: Number(rodadaAtual),
      tipo: tipo,
      atualizado_em: new Date().toISOString(),
      dados: filtrado
    };

    var caminho = "data/times_atual_" + slugSeguro(tipo) + ".json";
    var upload = subirArquivoGithub(JSON.stringify(jsonObj, null, 2), caminho, "Atualização automática TIMES_ATUAL - " + tipo + " - rodada " + rodadaAtual);

    if (!upload.ok) {
      throw new Error("Falha ao subir arquivo do tipo " + tipo + " para o GitHub: " + upload.mensagem);
    }

    var dispatch = dispararGithubPublicacao("times", {
      pipeline: "jobtelegram",
      rodada: Number(rodadaAtual),
      tipo: tipo,
      arquivo_json: caminho,
      mensagem_oficial: "",
      dados: filtrado,
      resumo: {
        total_registros: filtrado.length,
        sha: upload.sha || ""
      }
    });

    props.setProperty(chaveHash, hashAtual);

    resultado.push({
      tipo: tipo,
      rodada: Number(rodadaAtual),
      alterado: true,
      arquivo: caminho,
      dispatch: !!dispatch.ok
    });
  });

  var houveAlteracao = resultado.some(function(item) {
    return !!item.alterado;
  });

  if (houveAlteracao) {
    var arquivosConsolidados = {};
    resultado.forEach(function(item) {
      arquivosConsolidados[slugSeguro(item.tipo)] = item.arquivo;
    });

    var consolidado = {
      origem: "syncCartolaGithub",
      rodada: Number(rodadaAtual),
      arquivos: arquivosConsolidados,
      modelos: tipos
    };

    subirArquivoGithub(
      JSON.stringify(consolidado, null, 2),
      "data/times_atual.json",
      "Atualização automática TIMES_ATUAL consolidado - rodada " + rodadaAtual
    );
  }

  return resultado;
}

/* =========================
   PROCESSA TOP5_ATUAL
========================= */

function processarTop5() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sh = ss.getSheetByName("TOP5_ATUAL");
  if (!sh || sh.getLastRow() < 2) {
    logSistemaLocal("processarTop5: aba TOP5_ATUAL inexistente ou vazia.", "INFO");
    return {
      alterado: false,
      motivo: "sem_dados"
    };
  }

  var tabela = lerTabelaAba(sh);
  var idxRodada = tabela.indices["RODADA"];

  if (idxRodada === undefined) {
    throw new Error("TOP5_ATUAL sem coluna obrigatória RODADA.");
  }

  var rowsValidas = tabela.rows.filter(function(row) {
    return isNumeroValido(row[idxRodada]);
  });

  if (!rowsValidas.length) {
    logSistemaLocal("processarTop5: nenhuma linha válida encontrada.", "INFO");
    return {
      alterado: false,
      motivo: "sem_linhas_validas"
    };
  }

  var rodadaAtual = obterMaiorNumero(rowsValidas.map(function(row) {
    return row[idxRodada];
  }));

  var filtrado = rowsValidas
    .filter(function(row) {
      return Number(row[idxRodada]) === Number(rodadaAtual);
    })
    .map(function(row) {
      return montarObjetoLinha(tabela.headersOriginais, row, ["DATA", "ATUALIZADO_EM"]);
    });

  if (!filtrado.length) {
    return {
      alterado: false,
      motivo: "sem_registros_na_rodada"
    };
  }

  var props = PropertiesService.getScriptProperties();
  var hashBase = {
    rodada: Number(rodadaAtual),
    dados: filtrado
  };
  var hashAtual = gerarHash(hashBase);
  var hashAnterior = props.getProperty("HASH_TOP5");

  if (hashAnterior === hashAtual) {
    return {
      alterado: false,
      rodada: Number(rodadaAtual),
      arquivo: "data/top5_atual.json",
      dispatch: false
    };
  }

  var jsonObj = {
    origem: "syncCartolaGithub",
    pipeline: "jobtelegram",
    tipo_publicacao: "top5",
    rodada: Number(rodadaAtual),
    atualizado_em: new Date().toISOString(),
    dados: filtrado
  };

  var caminho = "data/top5_atual.json";
  var upload = subirArquivoGithub(JSON.stringify(jsonObj, null, 2), caminho, "Atualização automática TOP5_ATUAL - rodada " + rodadaAtual);

  if (!upload.ok) {
    throw new Error("Falha ao subir TOP5_ATUAL para o GitHub: " + upload.mensagem);
  }

  var dispatch = dispararGithubPublicacao("top5", {
    pipeline: "jobtelegram",
    rodada: Number(rodadaAtual),
    arquivo_json: caminho,
    mensagem_oficial: "",
    dados: filtrado,
    resumo: {
      total_registros: filtrado.length,
      sha: upload.sha || ""
    }
  });

  props.setProperty("HASH_TOP5", hashAtual);

  return {
    alterado: true,
    rodada: Number(rodadaAtual),
    arquivo: caminho,
    dispatch: !!dispatch.ok
  };
}

/* =========================
   WEBHOOK PARA GITHUB ACTIONS / PUBLICAÇÃO
========================= */

function doPost(e) {
  try {
    var body = parseJsonSeguro((e && e.postData && e.postData.contents) ? e.postData.contents : "{}");
    var payload = extrairPayloadWebhook(body);

    var BOT_TOKEN = getCredencialCofre("TELEGRAM_BOT_TOKEN");
    var CHAT_ID_PADRAO = getCredencialCofre("TELEGRAM_CHAT_ID");

    if (!BOT_TOKEN) {
      throw new Error("Credencial TELEGRAM_BOT_TOKEN não encontrada no Cofre.");
    }

    var chatId = textoSeguro(payload.chat_id || body.chat_id || CHAT_ID_PADRAO).trim();
    if (!chatId) {
      throw new Error("CHAT_ID não informado no payload e não encontrado no Cofre.");
    }

    var tipoPublicacao = textoSeguro(payload.tipo_publicacao || body.tipo_publicacao || payload.tipo || body.tipo || "geral").trim();
    var pipeline = textoSeguro(payload.pipeline || body.pipeline || "jobtelegram").trim();
    var imagemUrl = textoSeguro(
      payload.imagem_url || payload.image_url || payload.photo || body.imagem_url || body.image_url || body.photo || ""
    ).trim();
    var mensagem = textoSeguro(
      payload.mensagem || payload.mensagem_oficial || payload.caption || payload.legenda || body.mensagem || body.caption || body.legenda || ""
    );
    var parseMode = textoSeguro(payload.parse_mode || body.parse_mode || "Markdown").trim() || "Markdown";

    if (!imagemUrl && !mensagem) {
      throw new Error("Webhook sem imagem e sem mensagem para publicar.");
    }

    var respostaTelegram = [];

    if (imagemUrl) {
      var envioFoto = enviarTelegramFoto(BOT_TOKEN, chatId, imagemUrl, mensagem, parseMode);
      respostaTelegram.push(envioFoto);

      if (envioFoto.captionsExcedidas && mensagem) {
        var partesMensagem = quebrarTextoTelegram(mensagem, 3500);
        partesMensagem.forEach(function(parte) {
          respostaTelegram.push(enviarTelegramTexto(BOT_TOKEN, chatId, parte, parseMode));
        });
      }
    } else if (mensagem) {
      var partesTexto = quebrarTextoTelegram(mensagem, 3500);
      partesTexto.forEach(function(parte) {
        respostaTelegram.push(enviarTelegramTexto(BOT_TOKEN, chatId, parte, parseMode));
      });
    }

    logSistemaLocal(
      "Webhook publicado com sucesso. pipeline=" + pipeline + " tipo_publicacao=" + tipoPublicacao + " imagem=" + (imagemUrl ? "SIM" : "NAO"),
      "INFO"
    );

    return ContentService
      .createTextOutput(JSON.stringify({
        status: "sucesso",
        pipeline: pipeline,
        tipo_publicacao: tipoPublicacao,
        respostas: respostaTelegram
      }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (erro) {
    logSistemaLocal("ERRO doPost: " + erro.message, "ERRO");
    return ContentService
      .createTextOutput(JSON.stringify({
        status: "erro",
        mensagem: erro.message
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/* =========================
   DISPATCH GITHUB
========================= */

function dispararGithubPublicacao(tipoPublicacao, payload) {
  try {
    var cfg = montarConfigGithubDispatch();
    if (!cfg.ativo) {
      logSistemaLocal("Dispatch GitHub desativado na CONFIG.", "INFO");
      return {
        ok: false,
        motivo: "dispatch_inativo"
      };
    }

    if (!cfg.repo || !cfg.token) {
      throw new Error("Repo/token do dispatch GitHub não configurados.");
    }

    var evento = obterEventoPorTipo(cfg, tipoPublicacao);
    if (!evento) {
      throw new Error("Evento GitHub não definido para o tipo: " + tipoPublicacao);
    }

    var url = cfg.apiBase.replace(/\/$/, "") + "/repos/" + cfg.repo + "/dispatches";
    var body = {
      event_type: evento,
      client_payload: {
        origem: "syncCartolaGithub",
        pipeline: payload && payload.pipeline ? payload.pipeline : "jobtelegram",
        tipo_publicacao: tipoPublicacao,
        rodada: payload && payload.rodada ? payload.rodada : null,
        gerado_em: new Date().toISOString(),
        payload: payload || {}
      }
    };

    var resp = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      headers: {
        Authorization: "Bearer " + cfg.token,
        Accept: "application/vnd.github+json"
      },
      payload: JSON.stringify(body),
      muteHttpExceptions: true
    });

    var code = resp.getResponseCode();
    var text = resp.getContentText();
    var ok = code >= 200 && code < 300;

    logSistemaLocal("Dispatch GitHub [" + tipoPublicacao + "] HTTP " + code + ": " + text, ok ? "INFO" : "ERRO");

    return {
      ok: ok,
      codigo: code,
      resposta: text,
      evento: evento
    };
  } catch (e) {
    logSistemaLocal("ERRO dispararGithubPublicacao [" + tipoPublicacao + "]: " + e.message, "ERRO");
    return {
      ok: false,
      mensagem: e.message
    };
  }
}

function montarConfigGithubDispatch() {
  var ativoRaw = textoSeguro(getConfig("GITHUB_DISPATCH_ATIVO") || getConfig("GITHUB_TESTE_ATIVO") || "NAO").toUpperCase();
  return {
    ativo: ativoRaw === "SIM",
    repo: textoSeguro(getConfig("GITHUB_DISPATCH_REPO") || getConfig("GITHUB_REPO") || getConfig("GITHUB_TESTE_REPO")).trim(),
    token: textoSeguro(getConfig("GITHUB_DISPATCH_TOKEN") || getConfig("GITHUB_TOKEN") || getConfig("GITHUB_TESTE_TOKEN")).trim(),
    apiBase: textoSeguro(getConfig("GITHUB_DISPATCH_API_BASE") || getConfig("GITHUB_API_BASE") || getConfig("GITHUB_TESTE_API_BASE") || GITHUB_API_BASE_PADRAO).trim(),
    eventoGeral: textoSeguro(getConfig("GITHUB_DISPATCH_EVENTO") || getConfig("GITHUB_TESTE_EVENTO") || "cartola_publish_test").trim(),
    eventoTimes: textoSeguro(getConfig("GITHUB_EVENTO_TIMES") || getConfig("GITHUB_DISPATCH_EVENTO_TIMES") || getConfig("GITHUB_TESTE_EVENTO") || "cartola_publish_times").trim(),
    eventoTop5: textoSeguro(getConfig("GITHUB_EVENTO_TOP5") || getConfig("GITHUB_DISPATCH_EVENTO_TOP5") || getConfig("GITHUB_TESTE_EVENTO") || "cartola_publish_top5").trim(),
    eventoLive: textoSeguro(getConfig("GITHUB_EVENTO_LIVE") || getConfig("GITHUB_DISPATCH_EVENTO_LIVE") || getConfig("GITHUB_TESTE_EVENTO") || "cartola_live_publish").trim()
  };
}

function obterEventoPorTipo(cfg, tipoPublicacao) {
  var tipo = textoSeguro(tipoPublicacao).toLowerCase().trim();
  if (tipo === "times") return cfg.eventoTimes || cfg.eventoGeral;
  if (tipo === "top5") return cfg.eventoTop5 || cfg.eventoGeral;
  if (tipo === "live" || tipo === "live_publisher") return cfg.eventoLive || cfg.eventoGeral;
  return cfg.eventoGeral;
}

/* =========================
   TELEGRAM
========================= */

function enviarTelegramTexto(botToken, chatId, texto, parseMode) {
  var url = "https://api.telegram.org/bot" + botToken + "/sendMessage";
  var payload = {
    chat_id: chatId,
    text: texto,
    parse_mode: parseMode || "Markdown"
  };

  var resp = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var code = resp.getResponseCode();
  var text = resp.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error("Falha ao enviar texto ao Telegram. HTTP " + code + ": " + text);
  }

  return {
    tipo: "texto",
    codigo: code,
    resposta: parseJsonSeguro(text)
  };
}

function enviarTelegramFoto(botToken, chatId, imagemUrl, legenda, parseMode) {
  var url = "https://api.telegram.org/bot" + botToken + "/sendPhoto";
  var legendaFinal = textoSeguro(legenda);
  var captionsExcedidas = false;

  if (legendaFinal.length > 1024) {
    legendaFinal = legendaFinal.substring(0, 1020) + "...";
    captionsExcedidas = true;
  }

  var payload = {
    chat_id: chatId,
    photo: imagemUrl,
    parse_mode: parseMode || "Markdown"
  };

  if (legendaFinal) {
    payload.caption = legendaFinal;
  }

  var resp = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var code = resp.getResponseCode();
  var text = resp.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error("Falha ao enviar foto ao Telegram. HTTP " + code + ": " + text);
  }

  return {
    tipo: "foto",
    codigo: code,
    captionsExcedidas: captionsExcedidas,
    resposta: parseJsonSeguro(text)
  };
}

function quebrarTextoTelegram(texto, limite) {
  var saida = [];
  var txt = textoSeguro(texto);
  var max = Number(limite || 3500);

  if (!txt) return saida;
  if (txt.length <= max) return [txt];

  var inicio = 0;
  while (inicio < txt.length) {
    var fim = Math.min(inicio + max, txt.length);
    var trecho = txt.substring(inicio, fim);
    var quebra = trecho.lastIndexOf("\n");
    if (quebra > 500 && fim < txt.length) {
      fim = inicio + quebra;
    }
    saida.push(txt.substring(inicio, fim));
    inicio = fim;
  }

  return saida;
}

/* =========================
   GITHUB CONTENTS API
========================= */

function subirArquivoGithub(conteudo, filePath, commitMessage) {
  var cfg = montarConfigGithubArquivos();

  if (!cfg.token || !cfg.repo || !cfg.branch) {
    throw new Error("Configuração GitHub incompleta na aba CONFIG.");
  }

  var pathSeguro = montarPathGithubSeguro(filePath);
  var urlBase = cfg.apiBase.replace(/\/$/, "") + "/repos/" + cfg.repo + "/contents/" + pathSeguro;
  var urlGet = urlBase + "?ref=" + encodeURIComponent(cfg.branch);

  var sha = null;
  var getResp = UrlFetchApp.fetch(urlGet, {
    method: "get",
    headers: {
      Authorization: "Bearer " + cfg.token,
      Accept: "application/vnd.github+json"
    },
    muteHttpExceptions: true
  });

  var getCode = getResp.getResponseCode();
  if (getCode === 200) {
    var getObj = parseJsonSeguro(getResp.getContentText());
    sha = getObj && getObj.sha ? getObj.sha : null;
  } else if (getCode !== 404) {
    throw new Error("Falha ao consultar arquivo no GitHub. HTTP " + getCode + ": " + getResp.getContentText());
  }

  var payload = {
    message: commitMessage || ("Atualização automática: " + filePath),
    content: Utilities.base64Encode(Utilities.newBlob(conteudo).getBytes()),
    branch: cfg.branch
  };
  if (sha) payload.sha = sha;

  var putResp = UrlFetchApp.fetch(urlBase, {
    method: "put",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + cfg.token,
      Accept: "application/vnd.github+json"
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var putCode = putResp.getResponseCode();
  var putText = putResp.getContentText();
  var putObj = parseJsonSeguro(putText);
  var ok = putCode >= 200 && putCode < 300;

  if (!ok) {
    throw new Error("Falha ao gravar arquivo no GitHub. HTTP " + putCode + ": " + putText);
  }

  logSistemaLocal("Arquivo enviado ao GitHub: " + filePath + " | HTTP " + putCode, "INFO");

  return {
    ok: true,
    codigo: putCode,
    sha: putObj && putObj.content ? putObj.content.sha : "",
    mensagem: putText
  };
}

function montarConfigGithubArquivos() {
  return {
    token: textoSeguro(getConfig("GITHUB_TOKEN") || getConfig("GITHUB_DISPATCH_TOKEN") || getConfig("GITHUB_TESTE_TOKEN")).trim(),
    repo: textoSeguro(getConfig("GITHUB_REPO") || getConfig("GITHUB_DISPATCH_REPO") || getConfig("GITHUB_TESTE_REPO")).trim(),
    branch: textoSeguro(getConfig("GITHUB_BRANCH") || "main").trim(),
    apiBase: textoSeguro(getConfig("GITHUB_API_BASE") || getConfig("GITHUB_DISPATCH_API_BASE") || getConfig("GITHUB_TESTE_API_BASE") || GITHUB_API_BASE_PADRAO).trim()
  };
}

function montarPathGithubSeguro(filePath) {
  return textoSeguro(filePath)
    .split("/")
    .filter(function(parte) { return !!parte; })
    .map(function(parte) { return encodeURIComponent(parte); })
    .join("/");
}

/* =========================
   LEITURA DE CONFIG / COFRE
========================= */

function getCredencialCofre(chaveBusca) {
  var ss = SpreadsheetApp.openById(COFRE_ID);
  var sh = ss.getSheetByName(COFRE_SHEET);
  if (!sh || sh.getLastRow() < 2) return null;

  var dados = sh.getDataRange().getValues();
  for (var i = 1; i < dados.length; i++) {
    if (textoSeguro(dados[i][2]).trim() === textoSeguro(chaveBusca).trim()) {
      return dados[i][3];
    }
  }
  return null;
}

function getConfig(chave) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sh = ss.getSheetByName("CONFIG");
  if (!sh || sh.getLastRow() < 2) return null;

  var dados = sh.getDataRange().getValues();
  for (var i = 1; i < dados.length; i++) {
    if (textoSeguro(dados[i][0]).trim() === textoSeguro(chave).trim()) {
      return dados[i][1];
    }
  }
  return null;
}

/* =========================
   HELPERS GERAIS
========================= */

function lerTabelaAba(sheet) {
  var dados = sheet.getDataRange().getValues();
  var headersOriginais = (dados[0] || []).map(function(h) {
    return textoSeguro(h).trim();
  });
  var headersNormalizados = headersOriginais.map(function(h) {
    return normalizarCabecalho(h);
  });
  var indices = {};
  headersNormalizados.forEach(function(h, i) {
    if (h && indices[h] === undefined) indices[h] = i;
  });

  return {
    headersOriginais: headersOriginais,
    headersNormalizados: headersNormalizados,
    indices: indices,
    rows: dados.slice(1)
  };
}

function montarObjetoLinha(headersOriginais, row, colunasIgnoradas) {
  var ignorar = {};
  (colunasIgnoradas || []).forEach(function(col) {
    ignorar[normalizarCabecalho(col)] = true;
  });

  var obj = {};
  headersOriginais.forEach(function(header, idx) {
    var chaveNormalizada = normalizarCabecalho(header);
    if (!header || ignorar[chaveNormalizada]) return;
    obj[header] = normalizarValorLinha(row[idx]);
  });
  return obj;
}

function normalizarValorLinha(valor) {
  if (valor instanceof Date) {
    return Utilities.formatDate(valor, TIMEZONE_PADRAO, "yyyy-MM-dd'T'HH:mm:ssXXX");
  }
  return valor;
}

function normalizarCabecalho(texto) {
  var s = textoSeguro(texto).trim().toUpperCase();
  try {
    s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } catch (e) {}
  return s.replace(/\s+/g, "_");
}

function textoSeguro(valor) {
  return String(valor === null || valor === undefined ? "" : valor);
}

function parseJsonSeguro(texto) {
  try {
    return JSON.parse(textoSeguro(texto) || "{}");
  } catch (e) {
    return {};
  }
}

function isNumeroValido(valor) {
  return valor !== "" && valor !== null && valor !== undefined && !isNaN(Number(valor));
}

function obterMaiorNumero(lista) {
  var numeros = (lista || [])
    .map(function(v) { return Number(v); })
    .filter(function(v) { return !isNaN(v); });
  return numeros.length ? Math.max.apply(null, numeros) : null;
}

function obterValoresUnicos(lista) {
  var mapa = {};
  var saida = [];
  (lista || []).forEach(function(item) {
    var chave = textoSeguro(item);
    if (mapa[chave]) return;
    mapa[chave] = true;
    saida.push(item);
  });
  return saida;
}

function slugSeguro(texto) {
  var s = textoSeguro(texto).trim().toLowerCase();
  try {
    s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  } catch (e) {}
  s = s.replace(/[^a-z0-9]+/g, "_");
  s = s.replace(/^_+|_+$/g, "");
  return s || "geral";
}

function gerarHash(obj) {
  var texto = JSON.stringify(obj);
  return Utilities.base64Encode(
    Utilities.computeDigest(
      Utilities.DigestAlgorithm.MD5,
      texto
    )
  );
}

function extrairPayloadWebhook(body) {
  if (!body || typeof body !== "object") return {};
  if (body.client_payload && body.client_payload.payload) return body.client_payload.payload;
  if (body.payload && typeof body.payload === "object") return body.payload;
  return body;
}

function logSistemaLocal(mensagem, nivel) {
  var linha = "[" + (nivel || "INFO") + "] " + mensagem;
  if (typeof logSistema === "function") {
    try {
      logSistema(mensagem, nivel || "INFO");
      return;
    } catch (e) {}
  }
  Logger.log(linha);
}
