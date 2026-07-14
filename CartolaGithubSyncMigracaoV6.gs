/**
 * Complemento de migração do Cartola GitHub Sync Engine v6.
 *
 * Execute UMA VEZ no projeto Apps Script:
 *   configurarPublicacaoSomenteImagensGithubV6()
 *
 * A função preserva as flags já cumpridas pelo jobTelegramDispatcher,
 * evitando republicar seleção inicial, pré-fechamento ou atualização das 20h.
 */

function configurarPublicacaoSomenteImagensGithubV6() {
  CARTOLA_GH_setConfig_("NOTIF_TIMES", "NAO");
  CARTOLA_GH_setConfig_("NOTIF_TOP5", "NAO");
  CARTOLA_GH_setConfig_("GITHUB_PUBLICAR_TIMES", "SIM");
  CARTOLA_GH_setConfig_("GITHUB_PUBLICAR_TOP5", "SIM");

  CARTOLA_GH_instalarAcionador_();
  CARTOLA_GH_limparFlagsScheduler_();
  CARTOLA_GH_importarFlagsLegados_();

  var resultado = syncCartolaGithub();
  CARTOLA_GH_log_(
    "Migração V6 concluída: textos antigos desativados e flags programadas preservadas.",
    "INFO"
  );
  return resultado;
}

function CARTOLA_GH_importarFlagsLegados_() {
  var estado = CARTOLA_GH_obterEstadoMercado_();
  if (!estado.rodada) return;

  var props = PropertiesService.getScriptProperties();
  var prefixo = "CARTOLA_GH_SCHED_R" + estado.rodada + "_";
  var flags = {};

  try {
    if (typeof getFlagsRodada_ === "function") {
      flags = getFlagsRodada_(estado.rodada) || {};
    }
  } catch (erroFlags) {}

  if (Number(flags.timestamp_abertura || 0) > 0) {
    props.setProperty(prefixo + "ABERTURA_TS", String(flags.timestamp_abertura));
  }
  if (flags.selecao_inicial_enviada) {
    props.setProperty(prefixo + "SELECAO_INICIAL", "1");
  }
  if (flags.pre_fechamento_times_enviado) {
    props.setProperty(prefixo + "PRE_FECHAMENTO_TIMES", "1");
  }
  if (flags.pre_fechamento_top5_enviado) {
    props.setProperty(prefixo + "PRE_FECHAMENTO_TOP5", "1");
  }
  if (flags.confirmados_enviados) {
    props.setProperty(prefixo + "CONFIRMADOS", "1");
  }

  var ultima20h = props.getProperty(
    "PSS_TG_LAST_20H_DATE_R" + estado.rodada
  );
  if (ultima20h) {
    props.setProperty(prefixo + "ULTIMA_20H_DATA", ultima20h);
  }
}
