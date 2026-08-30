/*
 * PORTAL SIMONSPORTS — CARTOLA EFICIÊNCIA V2 (MODO SOMBRA)
 * ----------------------------------------------------------
 * Objetivo:
 *  1) separar o ranking por perfil de time;
 *  2) incluir TETO/PISO determinísticos sem usar informação pós-rodada;
 *  3) substituir a montagem gulosa por beam search;
 *  4) escolher capitão com maior peso de teto para modelos ofensivos;
 *  5) NÃO alterar nenhuma aba/time de produção enquanto a V2 não for ativada.
 *
 * Pré-requisitos do código principal V19:
 *  getSS_(), obterRodada_(), obterStatusMercado_(), lerPrecosMercado_(),
 *  lerEsquemaAtivo_(), validarEsquema_(), lerConfigAcertividade_(),
 *  montarRanking_(), lerOrcamentoPatrimonio_(), getOrCreate_().
 */

var PSS_EF2_VERSAO = "2026.08.30.1";
var PSS_EF2_ABA_SHADOW = "EFICIENCIA_V2_SHADOW";

function PSS_EF2_num_(v, padrao) {
  var n = Number(String(v === null || v === undefined ? "" : v).replace(",", "."));
  return isFinite(n) ? n : Number(padrao || 0);
}

function PSS_EF2_clamp_(v, min, max) {
  return Math.max(min, Math.min(max, Number(v || 0)));
}

function PSS_EF2_norm_(s) {
  return String(s || "").trim().toUpperCase();
}

function PSS_EF2_config_(ssParam) {
  var ss = ssParam || ((typeof getSS_ === "function") ? getSS_() : SpreadsheetApp.getActiveSpreadsheet());
  var out = {
    ATIVA: false,
    MODO_SOMBRA: true,
    POOL_POR_POSICAO: 15,
    BEAM_WIDTH: 500,
    CAP_PESO_CEILING: 0.55,
    CEILING: {
      TIME_ECONOMICO: 0.08,
      TIME_INTERMEDIARIO: 0.18,
      TIME_PONTUACAO: 0.35,
      TIME_AVANCADO_PRO: 0.28,
      TIME_OMEGA_MAX: 0.45
    }
  };

  var sh = ss.getSheetByName("CONFIG");
  if (!sh || sh.getLastRow() < 2) return out;

  var vals = sh.getRange(1, 1, sh.getLastRow(), Math.min(2, sh.getLastColumn())).getValues();
  var map = {};
  for (var i = 0; i < vals.length; i++) {
    var k = PSS_EF2_norm_(vals[i][0]);
    if (k) map[k] = vals[i][1];
  }

  out.ATIVA = PSS_EF2_norm_(map.EFICIENCIA_V2_ATIVA) === "SIM";
  out.MODO_SOMBRA = PSS_EF2_norm_(map.EFICIENCIA_V2_MODO_SOMBRA || "SIM") === "SIM";
  out.POOL_POR_POSICAO = Math.max(8, Math.min(30, Math.round(PSS_EF2_num_(map.EF_POOL_POR_POSICAO, 15))));
  out.BEAM_WIDTH = Math.max(100, Math.min(2000, Math.round(PSS_EF2_num_(map.EF_BEAM_WIDTH, 500))));
  out.CAP_PESO_CEILING = PSS_EF2_clamp_(PSS_EF2_num_(map.EF_CAP_PESO_CEILING, 0.55), 0, 1);

  out.CEILING.TIME_ECONOMICO = PSS_EF2_clamp_(PSS_EF2_num_(map.EF_CEILING_PESO_ECONOMICO, 0.08), 0, 1);
  out.CEILING.TIME_INTERMEDIARIO = PSS_EF2_clamp_(PSS_EF2_num_(map.EF_CEILING_PESO_INTERMEDIARIO, 0.18), 0, 1);
  out.CEILING.TIME_PONTUACAO = PSS_EF2_clamp_(PSS_EF2_num_(map.EF_CEILING_PESO_PONTUACAO, 0.35), 0, 1);
  out.CEILING.TIME_AVANCADO_PRO = PSS_EF2_clamp_(PSS_EF2_num_(map.EF_CEILING_PESO_AVANCADO_PRO, 0.28), 0, 1);
  out.CEILING.TIME_OMEGA_MAX = PSS_EF2_clamp_(PSS_EF2_num_(map.EF_CEILING_PESO_OMEGA_MAX, 0.45), 0, 1);
  return out;
}

function PSS_EF2_tipoBase_(tipo) {
  var t = PSS_EF2_norm_(tipo).replace(/_OFICIAL$/, "");
  if (t === "ECONOMICO") t = "TIME_ECONOMICO";
  if (t === "INTERMEDIARIO") t = "TIME_INTERMEDIARIO";
  if (t === "PONTUACAO") t = "TIME_PONTUACAO";
  if (t === "AVANCADO_PRO") t = "TIME_AVANCADO_PRO";
  if (t === "OMEGA_MAX") t = "TIME_OMEGA_MAX";
  return t;
}

function PSS_EF2_paramModelo_(tipo, cfg) {
  var t = PSS_EF2_tipoBase_(tipo);
  var p = {
    ceilingWeight: cfg.CEILING[t] !== undefined ? cfg.CEILING[t] : 0.20,
    floorWeight: 0.10,
    valueWeight: 0.05,
    factorWeight: 0.10,
    captainCeiling: cfg.CAP_PESO_CEILING
  };

  if (t === "TIME_ECONOMICO") {
    p.floorWeight = 0.30; p.valueWeight = 0.25; p.factorWeight = 0.08; p.captainCeiling = 0.35;
  } else if (t === "TIME_INTERMEDIARIO") {
    p.floorWeight = 0.18; p.valueWeight = 0.12; p.factorWeight = 0.10; p.captainCeiling = 0.45;
  } else if (t === "TIME_PONTUACAO") {
    p.floorWeight = 0.05; p.valueWeight = 0.02; p.factorWeight = 0.12; p.captainCeiling = 0.60;
  } else if (t === "TIME_AVANCADO_PRO") {
    p.floorWeight = 0.10; p.valueWeight = 0.05; p.factorWeight = 0.15; p.captainCeiling = 0.58;
  } else if (t === "TIME_OMEGA_MAX") {
    p.floorWeight = 0.00; p.valueWeight = 0.00; p.factorWeight = 0.12; p.captainCeiling = 0.68;
  }
  return p;
}

function PSS_EF2_posVol_(pos) {
  var p = PSS_EF2_norm_(pos);
  if (p === "ATA") return 1.15;
  if (p === "MEI") return 1.10;
  if (p === "LAT") return 1.05;
  if (p === "ZAG") return 0.96;
  if (p === "GOL") return 0.95;
  if (p === "TEC") return 0.85;
  return 1.00;
}

function PSS_EF2_metricasAtleta_(p) {
  var exp = Math.max(0, PSS_EF2_num_(p && p.score, 0));
  var jogos = Math.max(0, PSS_EF2_num_(p && p.jogos, 0));
  var fatorExperiencia = 0.80 + 0.50 / Math.sqrt(Math.max(1, jogos));
  fatorExperiencia = PSS_EF2_clamp_(fatorExperiencia, 0.80, 1.30);

  var sigma = exp * 0.28 * fatorExperiencia * PSS_EF2_posVol_(p && p.pos);
  var z90 = 1.281551565545;
  var piso = Math.max(0, exp - z90 * sigma);
  var teto = exp + z90 * sigma;

  var preco = Math.max(0, PSS_EF2_num_(p && p.preco, 0));
  var media = Math.max(0, PSS_EF2_num_(p && p.media, 0));
  var indiceValor = preco > 0 ? media / preco : 0;
  var valorSignal = PSS_EF2_clamp_(indiceValor - 0.20, -0.30, 0.30);

  var factor = PSS_EF2_num_(p && p.factor, 1);
  if (!factor) factor = 1;
  var factorSignal = PSS_EF2_clamp_(factor - 1, -0.30, 0.35);

  return {
    exp: exp,
    sigma: sigma,
    piso: piso,
    teto: teto,
    valorSignal: valorSignal,
    factorSignal: factorSignal
  };
}

function PSS_EF2_rankingModelo_(ranking, tipo, cfgParam) {
  var cfg = cfgParam || PSS_EF2_config_();
  var par = PSS_EF2_paramModelo_(tipo, cfg);
  var out = [];

  (ranking || []).forEach(function(orig) {
    if (!orig || !orig.id || !orig.pos) return;
    var m = PSS_EF2_metricasAtleta_(orig);
    if (!(m.exp > 0)) return;

    var scoreModelo = m.exp
      + par.ceilingWeight * (m.teto - m.exp)
      + par.floorWeight * (m.piso - m.exp)
      + m.exp * par.valueWeight * m.valorSignal
      + m.exp * par.factorWeight * m.factorSignal;

    var p = {};
    Object.keys(orig).forEach(function(k) { p[k] = orig[k]; });
    p.ef2ScoreBase = m.exp;
    p.ef2Sigma = m.sigma;
    p.ef2Piso = m.piso;
    p.ef2Teto = m.teto;
    p.ef2ScoreModelo = scoreModelo;
    p.ef2Tipo = PSS_EF2_tipoBase_(tipo);
    out.push(p);
  });

  out.sort(function(a, b) {
    if (b.ef2ScoreModelo !== a.ef2ScoreModelo) return b.ef2ScoreModelo - a.ef2ScoreModelo;
    if (b.ef2Teto !== a.ef2Teto) return b.ef2Teto - a.ef2Teto;
    return PSS_EF2_num_(a.preco, 0) - PSS_EF2_num_(b.preco, 0);
  });
  return out;
}

function PSS_EF2_slots_(esquema) {
  var e = (typeof validarEsquema_ === "function") ? validarEsquema_(esquema) : esquema;
  var ordem = ["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"];
  var slots = [];
  ordem.forEach(function(pos) {
    var qtd = Math.max(0, Number(e && e[pos] || 0));
    for (var i = 0; i < qtd; i++) slots.push(pos);
  });
  return slots;
}

function PSS_EF2_minRestante_(slots, pools) {
  var mins = new Array(slots.length + 1).fill(0);
  for (var i = slots.length - 1; i >= 0; i--) {
    var pool = pools[slots[i]] || [];
    var min = Infinity;
    for (var j = 0; j < pool.length; j++) {
      var pr = Math.max(0, PSS_EF2_num_(pool[j].preco, 0));
      if (pr < min) min = pr;
    }
    if (!isFinite(min)) min = 0;
    mins[i] = mins[i + 1] + min;
  }
  return mins;
}

function PSS_EF2_otimizarTitulares_(rankingModelo, esquema, orcamentoMax, cfgAcert, cfgEf) {
  var cfg = cfgEf || PSS_EF2_config_();
  var slots = PSS_EF2_slots_(esquema);
  if (!slots.length) return { titulares: [], custo: 0, score: 0, motivo: "ESQUEMA_VAZIO" };

  var maxPorClube = Number(cfgAcert && cfgAcert.MAX_POR_CLUBE || 0);
  var limite = (orcamentoMax === null || orcamentoMax === undefined || orcamentoMax === "")
    ? Infinity : Number(orcamentoMax);
  if (!isFinite(limite) || limite <= 0) limite = Infinity;

  var pools = {};
  ["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"].forEach(function(pos) {
    pools[pos] = (rankingModelo || []).filter(function(p) {
      return PSS_EF2_norm_(p.pos) === pos && PSS_EF2_num_(p.preco, 0) >= 0;
    }).slice(0, cfg.POOL_POR_POSICAO);
  });

  // Processa primeiro posições com menor pool para reduzir ramificação.
  slots.sort(function(a, b) { return (pools[a] || []).length - (pools[b] || []).length; });
  var minRest = PSS_EF2_minRestante_(slots, pools);

  var beam = [{ time: [], usados: {}, clubes: {}, custo: 0, score: 0 }];

  for (var s = 0; s < slots.length; s++) {
    var pos = slots[s];
    var cand = pools[pos] || [];
    if (!cand.length) return { titulares: [], custo: 0, score: 0, motivo: "SEM_CANDIDATO_" + pos };

    var prox = [];
    for (var bi = 0; bi < beam.length; bi++) {
      var st = beam[bi];
      for (var ci = 0; ci < cand.length; ci++) {
        var p = cand[ci];
        var id = Number(p.id || p.atleta_id || 0);
        if (!id || st.usados[id]) continue;

        var preco = Math.max(0, PSS_EF2_num_(p.preco, 0));
        var novoCusto = st.custo + preco;
        if (novoCusto > limite + 1e-9) continue;
        if (novoCusto + minRest[s + 1] > limite + 1e-9) continue;

        var clube = String(p.clube || p.clube_id || "").trim();
        var qtdClube = clube ? Number(st.clubes[clube] || 0) : 0;
        if (maxPorClube > 0 && clube && qtdClube >= maxPorClube) continue;

        var usados2 = {};
        Object.keys(st.usados).forEach(function(k) { usados2[k] = true; });
        usados2[id] = true;

        var clubes2 = {};
        Object.keys(st.clubes).forEach(function(k) { clubes2[k] = st.clubes[k]; });
        if (clube) clubes2[clube] = qtdClube + 1;

        prox.push({
          time: st.time.concat([p]),
          usados: usados2,
          clubes: clubes2,
          custo: novoCusto,
          score: st.score + PSS_EF2_num_(p.ef2ScoreModelo, p.score)
        });
      }
    }

    if (!prox.length) return { titulares: [], custo: 0, score: 0, motivo: "SEM_SOLUCAO_SLOT_" + s };
    prox.sort(function(a, b) {
      if (b.score !== a.score) return b.score - a.score;
      return a.custo - b.custo;
    });
    if (prox.length > cfg.BEAM_WIDTH) prox = prox.slice(0, cfg.BEAM_WIDTH);
    beam = prox;
  }

  beam.sort(function(a, b) { return b.score - a.score; });
  var melhor = beam[0];
  return { titulares: melhor.time, custo: melhor.custo, score: melhor.score, motivo: "OK" };
}

function PSS_EF2_escolherCapitao_(titulares, tipo, cfgParam) {
  var cfg = cfgParam || PSS_EF2_config_();
  var par = PSS_EF2_paramModelo_(tipo, cfg);
  var multPos = { ATA:1.10, MEI:1.08, LAT:1.02, ZAG:0.96, GOL:0.94, TEC:0 };
  var melhor = null;
  var melhorScore = -Infinity;

  (titulares || []).forEach(function(p) {
    var pos = PSS_EF2_norm_(p && p.pos);
    if (!p || pos === "TEC") return;
    var exp = PSS_EF2_num_(p.ef2ScoreBase, p.score);
    var teto = PSS_EF2_num_(p.ef2Teto, exp);
    var w = PSS_EF2_clamp_(par.captainCeiling, 0, 1);
    var sc = ((1 - w) * exp + w * teto) * (multPos[pos] || 1);

    var mando = PSS_EF2_norm_(p.mando);
    if (mando === "CASA" || mando === "HOME") sc *= 1.03;
    else if (mando === "FORA" || mando === "AWAY") sc *= 0.98;

    var factor = PSS_EF2_num_(p.factor, 1);
    if (factor > 1) sc *= 1 + Math.min(0.05, (factor - 1) * 0.08);

    p.ef2CapScore = sc;
    if (sc > melhorScore) { melhorScore = sc; melhor = p; }
  });
  return melhor;
}

function PSS_EF2_orcamento_(ss, tipo) {
  try {
    if (typeof lerOrcamentoPatrimonio_ === "function") {
      var v = lerOrcamentoPatrimonio_(ss, tipo);
      if (v !== null && v !== undefined && v !== "" && Number(v) > 0) return Number(v);
    }
  } catch (e) {}
  return null;
}

function PSS_EF2_gerarShadow() {
  var ss = (typeof getSS_ === "function") ? getSS_() : SpreadsheetApp.getActiveSpreadsheet();
  var cfgEf = PSS_EF2_config_(ss);
  if (!cfgEf.MODO_SOMBRA) {
    Logger.log("ℹ️ EFICIENCIA V2: modo sombra desativado.");
    return { ok:false, motivo:"MODO_SOMBRA_DESATIVADO" };
  }

  var rodada = (typeof obterRodada_ === "function") ? obterRodada_(ss) : 0;
  if (!rodada) throw new Error("Rodada inválida para EFICIENCIA V2.");

  var shMW = ss.getSheetByName("MW_MAPA_RODADA");
  if (!shMW || shMW.getLastRow() < 2) throw new Error("MW_MAPA_RODADA vazia.");

  var precoMap = lerPrecosMercado_(ss);
  var esquema = lerEsquemaAtivo_(ss);
  var cfgAcert = lerConfigAcertividade_(ss);
  var rankingBase = montarRanking_(shMW.getDataRange().getValues(), precoMap, cfgAcert);
  if (!rankingBase || !rankingBase.length) throw new Error("Ranking base vazio.");

  var tipos = [
    "TIME_ECONOMICO",
    "TIME_INTERMEDIARIO",
    "TIME_PONTUACAO",
    "TIME_AVANCADO_PRO",
    "TIME_OMEGA_MAX",
    "TIME_AVANCADO_PRO_OFICIAL",
    "TIME_OMEGA_MAX_OFICIAL"
  ];

  var now = Utilities.formatDate(new Date(), "America/Sao_Paulo", "dd/MM/yyyy HH:mm:ss");
  var linhas = [];
  var resumo = [];

  tipos.forEach(function(tipo) {
    var ranking = PSS_EF2_rankingModelo_(rankingBase, tipo, cfgEf);
    var orc = PSS_EF2_orcamento_(ss, tipo);
    var ot = PSS_EF2_otimizarTitulares_(ranking, esquema, orc, cfgAcert, cfgEf);
    var titulares = ot.titulares || [];
    var cap = PSS_EF2_escolherCapitao_(titulares, tipo, cfgEf);

    resumo.push({ tipo:tipo, qtd:titulares.length, custo:ot.custo, score:ot.score, motivo:ot.motivo, capitao:cap ? cap.apelido : "" });

    titulares.sort(function(a,b) {
      var ordem = {GOL:1,LAT:2,ZAG:3,MEI:4,ATA:5,TEC:6};
      var oa = ordem[PSS_EF2_norm_(a.pos)] || 99;
      var ob = ordem[PSS_EF2_norm_(b.pos)] || 99;
      if (oa !== ob) return oa - ob;
      return PSS_EF2_num_(b.ef2ScoreModelo,0) - PSS_EF2_num_(a.ef2ScoreModelo,0);
    });

    titulares.forEach(function(p, idx) {
      linhas.push([
        rodada, now, tipo, idx + 1, "TITULAR", p.pos, p.apelido, p.clube,
        PSS_EF2_num_(p.preco,0), PSS_EF2_num_(p.ef2ScoreBase,p.score),
        PSS_EF2_num_(p.ef2Teto,0), PSS_EF2_num_(p.ef2Piso,0),
        PSS_EF2_num_(p.ef2ScoreModelo,0),
        cap && Number(cap.id) === Number(p.id) ? "SIM" : "NAO",
        Number(p.id || 0), PSS_EF2_num_(p.factor,1), p.mando || "", p.adversario || ""
      ]);
    });
  });

  var sh = getOrCreate_(ss, PSS_EF2_ABA_SHADOW);
  sh.clearContents();
  var header = ["RODADA","GERADO_EM","MODELO","ORDEM","STATUS","POS","APELIDO","CLUBE","PRECO","EXP_ATUAL","TETO_V2","PISO_V2","SCORE_MODELO_V2","CAPITAO_V2","ATLETA_ID","FACTOR","MANDO","ADVERSARIO"];
  sh.getRange(1,1,1,header.length).setValues([header]);
  if (linhas.length) sh.getRange(2,1,linhas.length,header.length).setValues(linhas);
  sh.setFrozenRows(1);

  Logger.log("✅ EFICIENCIA V2 SHADOW " + PSS_EF2_VERSAO + " | R" + rodada + " | linhas=" + linhas.length);
  return { ok:true, versao:PSS_EF2_VERSAO, rodada:rodada, linhas:linhas.length, resumo:resumo };
}

/*
 * INTEGRAÇÃO FUTURA — SOMENTE DEPOIS DA VALIDAÇÃO DO SHADOW
 * ----------------------------------------------------------
 * No executarModelo_ atual:
 *   - quando EFICIENCIA_V2_ATIVA=SIM, chamar PSS_EF2_rankingModelo_()
 *   - substituir escalarTitulares_() por PSS_EF2_otimizarTitulares_()
 *   - substituir escolherCapitao_() por PSS_EF2_escolherCapitao_()
 *
 * Enquanto EFICIENCIA_V2_ATIVA=NAO, nenhuma rotina oficial deve usar a V2.
 */
