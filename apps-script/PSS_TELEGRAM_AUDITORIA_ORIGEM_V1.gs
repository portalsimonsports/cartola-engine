/**
 * PORTAL SIMONSPORTS — AUDITORIA DE ORIGEM TELEGRAM V1
 *
 * Objetivo: registrar QUEM tentou enviar cada mensagem/foto ao Telegram.
 * Este módulo NÃO altera a decisão de publicar; apenas audita.
 *
 * Uso recomendado no Apps Script:
 *   PSS_TG_AUDIT_registrar_("LIVE_PUBLISHER_V129", "enviarTelegram_", "sendMessage", texto, rodada, extra);
 *   PSS_TG_AUDIT_registrar_("JOB_TELEGRAM_V7", "enviarTelegramTexto_", "sendMessage", texto, rodada, extra);
 *
 * A auditoria grava:
 * - console.log / Executions
 * - aba LOG_TELEGRAM_ORIGEM da planilha principal, quando acessível
 */

var PSS_TG_AUDIT_CONFIG = {
  VERSAO: "v2026.1",
  ABA: "LOG_TELEGRAM_ORIGEM",
  LIMITE_TEXTO: 500,
  TIMEZONE: "America/Sao_Paulo"
};

function PSS_TG_AUDIT_registrar_(projeto, funcao, metodo, conteudo, rodada, extra) {
  try {
    var agora = new Date();
    var registro = {
      timestamp_iso: agora.toISOString(),
      data_hora: Utilities.formatDate(agora, PSS_TG_AUDIT_CONFIG.TIMEZONE, "dd/MM/yyyy HH:mm:ss"),
      projeto: String(projeto || "DESCONHECIDO"),
      funcao: String(funcao || "DESCONHECIDA"),
      metodo: String(metodo || "DESCONHECIDO"),
      rodada: Number(rodada || 0),
      conteudo: PSS_TG_AUDIT_resumir_(conteudo),
      extra: PSS_TG_AUDIT_serializar_(extra)
    };

    console.log("[PSS_TG_AUDIT] " + JSON.stringify(registro));
    PSS_TG_AUDIT_gravarPlanilha_(registro);
    return registro;
  } catch (e) {
    console.log("[PSS_TG_AUDIT][ERRO] " + String(e && e.message ? e.message : e));
    return null;
  }
}

function PSS_TG_AUDIT_resumir_(valor) {
  var s = "";
  try {
    s = typeof valor === "string" ? valor : JSON.stringify(valor || "");
  } catch (e) {
    s = String(valor || "");
  }
  s = s.replace(/\s+/g, " ").trim();
  if (s.length > PSS_TG_AUDIT_CONFIG.LIMITE_TEXTO) {
    s = s.substring(0, PSS_TG_AUDIT_CONFIG.LIMITE_TEXTO) + "…";
  }
  return s;
}

function PSS_TG_AUDIT_serializar_(extra) {
  if (extra === undefined || extra === null || extra === "") return "";
  try {
    var s = typeof extra === "string" ? extra : JSON.stringify(extra);
    return s.length > 1000 ? s.substring(0, 1000) + "…" : s;
  } catch (e) {
    return String(extra);
  }
}

function PSS_TG_AUDIT_obterSS_() {
  try {
    if (typeof getSS_ === "function") return getSS_();
  } catch (e1) {}
  try {
    if (typeof ss_ === "function") return ss_();
  } catch (e2) {}
  try {
    var ativo = SpreadsheetApp.getActiveSpreadsheet();
    if (ativo) return ativo;
  } catch (e3) {}
  try {
    if (typeof CARTOLA_GH_SPREADSHEET_ID !== "undefined" && CARTOLA_GH_SPREADSHEET_ID) {
      return SpreadsheetApp.openById(CARTOLA_GH_SPREADSHEET_ID);
    }
  } catch (e4) {}
  return null;
}

function PSS_TG_AUDIT_gravarPlanilha_(registro) {
  var ss = PSS_TG_AUDIT_obterSS_();
  if (!ss) return false;

  var sh = ss.getSheetByName(PSS_TG_AUDIT_CONFIG.ABA);
  if (!sh) {
    sh = ss.insertSheet(PSS_TG_AUDIT_CONFIG.ABA);
    sh.getRange(1, 1, 1, 8).setValues([[
      "DATA_HORA",
      "TIMESTAMP_ISO",
      "PROJETO",
      "FUNCAO",
      "METODO",
      "RODADA",
      "CONTEUDO",
      "EXTRA"
    ]]);
    sh.setFrozenRows(1);
  }

  sh.appendRow([
    registro.data_hora,
    registro.timestamp_iso,
    registro.projeto,
    registro.funcao,
    registro.metodo,
    registro.rodada,
    registro.conteudo,
    registro.extra
  ]);
  return true;
}

/**
 * Wrapper opcional para auditar uma chamada sendMessage antes do UrlFetchApp.fetch.
 * Não envia nada sozinho.
 */
function PSS_TG_AUDIT_sendMessage_(projeto, funcao, texto, rodada, extra) {
  return PSS_TG_AUDIT_registrar_(projeto, funcao, "sendMessage", texto, rodada, extra);
}

/**
 * Wrapper opcional para auditar uma chamada sendPhoto antes do UrlFetchApp.fetch.
 * Não envia nada sozinho.
 */
function PSS_TG_AUDIT_sendPhoto_(projeto, funcao, legendaOuArquivo, rodada, extra) {
  return PSS_TG_AUDIT_registrar_(projeto, funcao, "sendPhoto", legendaOuArquivo, rodada, extra);
}
