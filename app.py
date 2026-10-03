import itertools
import json
import time
from pathlib import Path
from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import otimizador as o

import ui
from ui import TEAL, DARK, RED, GRAY, BLUE, AMB_VIVO as AMB, como_ler, lead, resultado

SUN = "#FACC15"
st.set_page_config(page_title="Despacho de Energia da Fábrica", page_icon=str(Path(__file__).parent / "icone.png"), layout="wide")
ui.aplicar()

ui.hero("Otimização · eficiência energética",
        "Despacho de Energia da Fábrica",
        "Em que horário ligar cada máquina, quando carregar e descarregar a bateria e quanto do solar usar, para o dia "
        "sair o mais barato possível numa tarifa em que o kWh das 18 h às 21 h custa cinco vezes mais e o maior pico do "
        "mês vira cobrança fixa.",
        [("custo do dia", "−36%"), ("pico", "325 → 150 kW"), ("só mudando horários", "69% da economia"), ("solver", "MILP · 14 ms")],
        "Caio Gadotti · Projeto pessoal")
ui.escopo(
    "Na tarifa horo-sazonal da indústria, a mesma energia custa muito mais no horário de ponta, e a conta ainda cobra "
    "pela demanda: o maior consumo do mês, em kW, mesmo que tenha durado uma hora. Muita carga de fábrica não precisa "
    "rodar num horário fixo (forno de cura, compressor, carga de empilhadeira). A pergunta é qual plano de um dia "
    "típico custa menos, e se uma bateria se paga.",
    ["Programação linear inteira mista (MILP) com passo de 1 hora, resolvida pelo HiGHS",
     "Tarifa por hora, crédito por solar injetado e cobrança de demanda",
     "Cargas deslocáveis com janela permitida e potência fixa",
     "Bateria com capacidade, potência, eficiência e fim do dia na carga inicial",
     "Incerteza do sol por Monte Carlo (Beta × lognormal) e valor da informação perfeita",
     "Viabilidade da bateria: VPL, TIR, payback descontado e preço de equilíbrio"],
    ["Mais de um dia por vez (a demanda real é o pico do mês inteiro)",
     "Cargas que podem ser interrompidas ou mudar de potência",
     "Previsão de consumo e de sol com dados reais",
     "Tarifas oficiais de uma distribuidora específica: os valores são ilustrativos",
     "Degradação da bateria pelo uso diário (só a anual, na parte financeira)"])


def layout(fig, h=360, **kw):
    kw.setdefault("hovermode", "x unified")
    fig.update_layout(height=h, **kw)
    return fig


def ponta(fig, tarifa):
    if tarifa.ponta:
        fig.add_vrect(x0=min(tarifa.ponta) - .5, x1=max(tarifa.ponta) + .5, fillcolor=RED, opacity=.07,
                      line_width=0, annotation_text="ponta", annotation_position="top left")


def brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


# ---------------------------------------------------------------- entradas
with st.sidebar:
    st.markdown("### A fábrica")
    nome_tarifa = st.selectbox("Tarifa", list(o.TARIFAS),
                               help="Verde A4 é a tarifa típica de indústria em média tensão. Convencional serve de controle: preço único, nada a deslocar.")
    kwp = st.slider("Solar no telhado (kWp)", 0, 400, 120, 10,
                    help="Potência de pico dos painéis. A geração do dia típico usa 75% do céu limpo.")
    st.markdown("**Bateria**")
    bat_e = st.slider("Capacidade (kWh)", 0, 800, 200, 25, help="Energia que a bateria guarda. 0 = sem bateria.")
    bat_p = st.slider("Potência (kW)", 0, 400, 100, 10, help="Maior potência de carga ou descarga em cada hora.")
    bat_eta = st.slider("Eficiência por sentido", 0.80, 0.99, 0.95, 0.01,
                        help="Fração que sobra a cada passagem. Ida e volta = eficiência².")
    dias = st.number_input("Dias de operação por ano", 100, 365, 264, help="22 dias úteis × 12 meses")
    st.divider()
    t_sel = o.TARIFAS[nome_tarifa]
    st.markdown("**Tarifa escolhida**")
    st.markdown(
        f'<table class="glossario">'
        f'<tr><td>Fora de ponta</td><td></td><td>R&#36; {t_sel.preco.min():.2f}/kWh</td></tr>'
        f'<tr><td>Ponta</td><td></td><td>R&#36; {t_sel.preco.max():.2f}/kWh</td></tr>'
        f'<tr><td>Demanda</td><td></td><td>R&#36; {t_sel.demanda:.0f}/kW·mês</td></tr>'
        f'<tr><td>Injeção de solar</td><td></td><td>R&#36; {t_sel.exportacao:.2f}/kWh</td></tr></table>',
        unsafe_allow_html=True)
    st.caption("Valores ilustrativos, na ordem de grandeza das tarifas de distribuidoras paulistas.")
    st.divider()
    st.markdown("**Caio Gadotti** · Projeto pessoal")

COLS = {"nome": "Carga", "potencia": "Potência (kW)", "duracao": "Duração (h)", "janela_ini": "Pode começar às",
        "janela_fim": "Termina até", "inicio_atual": "Hoje liga às"}
if "cargas" not in st.session_state:
    st.session_state.cargas = pd.DataFrame([{k: getattr(c, k) for k in COLS} for c in o.CARGAS_PADRAO]).rename(columns=COLS)

with st.expander("Cargas deslocáveis e consumo fixo da fábrica (editável)", expanded=False, icon=":material/factory:"):
    st.caption("Cargas que podem mudar de horário sem atrapalhar a produção: o que importa é rodar dentro da janela. "
               "Adicione, remova ou mude à vontade.")
    df = st.data_editor(st.session_state.cargas, num_rows="dynamic", width="stretch", hide_index=True, key="ed",
                        column_config={c: st.column_config.NumberColumn(min_value=0, max_value=24 if "h" in c.lower() or "às" in c or "até" in c else 2000, step=1)
                                       for c in list(COLS.values())[1:]})
    escala = st.slider("Consumo fixo (iluminação, máquinas de linha, ar) em % do padrão", 50, 150, 100, 5,
                       help="O consumo que não dá para mudar de horário. Padrão: 150 kW nos turnos, 45 kW à noite.")

df = df.dropna()
try:
    cargas = [o.Carga(str(r["Carga"]), float(r["Potência (kW)"]), int(r["Duração (h)"]), int(r["Pode começar às"]),
                      int(r["Termina até"]), int(r["Hoje liga às"])) for _, r in df.iterrows()]
    for c in cargas:
        if not c.inicios:
            raise ValueError(f"'{c.nome}' dura {c.duracao} h e não cabe na janela {c.janela_ini}–{c.janela_fim} h")
        if not (0 <= c.inicio_atual <= 24 - c.duracao):
            raise ValueError(f"'{c.nome}' hoje liga às {c.inicio_atual} h e passaria da meia-noite")
except ValueError as e:
    st.error(f"Ajuste a tabela de cargas: {e}")
    st.stop()

chave_cargas = tuple((c.nome, c.potencia, c.duracao, c.janela_ini, c.janela_fim, c.inicio_atual) for c in cargas)


def montar(chave_cargas, tarifa, kwp, e, p, eta, escala, solar=None):
    cs = [o.Carga(*c) for c in chave_cargas]
    sol = kwp * o.forma_solar() * 0.75 if solar is None else np.asarray(solar)
    return o.Cenario(o.base_padrao() * escala / 100, sol, o.TARIFAS[tarifa], cs, o.Bateria(e, p, eta))


@st.cache_data(show_spinner=False)
def resolver(chave_cargas, tarifa, kwp, e, p, eta, escala):
    cen = montar(chave_cargas, tarifa, kwp, e, p, eta, escala)
    return o.plano_atual(cen), o.otimizar(replace(cen, bateria=o.Bateria())), o.otimizar(cen)


args = (chave_cargas, nome_tarifa, kwp, bat_e, bat_p, bat_eta, escala)
cen = montar(*args)
with st.spinner("Otimizando o dia..."):
    atual, so_cargas, otimo = resolver(*args)

tabs = st.tabs([":material/sports_esports: Brinque", ":material/bolt: Despacho", ":material/schedule: Horários das cargas",
                ":material/partly_cloudy_day: Incerteza do sol", ":material/savings: Vale comprar a bateria?",
                ":material/verified: Validação"], on_change="rerun", key="aba")

# ---------------------------------------------------------------- brinque
with tabs[0]:
    if tabs[0].open:
        st.markdown("### Você contra o otimizador")
        lead("Sem bateria, só mudando horários. Tudo roda no seu navegador: arraste e veja a conta mudar na hora. "
             "A tarifa, o solar e as cargas vêm da barra lateral e da tabela de cargas.")
        dados = {"base": list(cen.base), "solar": list(cen.solar), "preco": list(cen.tarifa.preco),
                 "demanda_dia": cen.tarifa.demanda_dia, "exportacao": cen.tarifa.exportacao, "ponta": list(cen.tarifa.ponta),
                 "cargas": [{"nome": c.nome, "potencia": c.potencia, "duracao": c.duracao, "ini": c.janela_ini,
                             "fim": c.janela_fim, "atual": c.inicio_atual} for c in cargas],
                 "otimo": so_cargas.inicios}
        html = (Path(__file__).parent / "brinque.html").read_text(encoding="utf-8").replace("__DADOS__", json.dumps(dados))
        st.iframe(html, height=380 + 40 * len(cargas) + 70)
        como_ler([
            ("Seu custo do dia", "R$", "Energia comprada × tarifa de cada hora, mais a cota diária da demanda, menos o crédito do solar injetado."),
            ("Pico de demanda", "kW", "Maior compra da rede numa hora do dia. É cobrado por kW no mês, então um pico curto sai caro."),
            ("Economia contra hoje", "R$/dia", "Quanto o seu arranjo economiza em relação aos horários de hoje (contorno vermelho)."),
            ("Quanto você chegou do ótimo", "%", "0% é o custo de hoje, 100% é o custo que o otimizador encontrou só mudando horários."),
            ("Faixa vermelha", "18 h às 21 h", "Horário de ponta: o kWh custa cerca de 5 vezes mais."),
            ("Área amarela", "kW", "Geração solar esperada. Consumo que cai dentro dela não compra da rede."),
        ])

# ---------------------------------------------------------------- despacho
with tabs[1]:
    if tabs[1].open:
        eco = atual.custo - otimo.custo
        c = st.columns(4)
        c[0].metric("Custo do dia hoje", brl(atual.custo),
                    help="Cargas nos horários de hoje e sem bateria. É a referência para todas as economias.")
        c[1].metric("Custo do dia otimizado", brl(otimo.custo), f"-{100 * eco / atual.custo:.0f}%", delta_color="inverse",
                    delta_arrow="off", help="Melhor plano com horários e bateria juntos.")
        c[2].metric("Pico de demanda", f"{otimo.pico:.0f} kW", f"era {atual.pico:.0f} kW", delta_color="off", delta_arrow="off",
                    help="Maior potência comprada da rede numa hora. Entra na conta como demanda (R$/kW·mês).")
        c[3].metric("Economia no ano", brl(eco * dias), f"{dias} dias", delta_color="off", delta_arrow="off",
                    help="Economia do dia típico vezes os dias de operação. Não desconta o investimento na bateria.")

        st.markdown('<div class="eyebrow">De onde vem a energia em cada hora (plano otimizado)</div>', unsafe_allow_html=True)
        solar_usado = cen.solar - otimo.exportacao
        fig = go.Figure()
        fig.add_bar(x=o.HORAS, y=otimo.rede, name="rede", marker_color=GRAY)
        fig.add_bar(x=o.HORAS, y=solar_usado, name="solar", marker_color=SUN)
        fig.add_bar(x=o.HORAS, y=otimo.descarga_bat, name="bateria (descarga)", marker_color=TEAL)
        fig.add_bar(x=o.HORAS, y=-otimo.carga_bat, name="bateria (carga)", marker_color="#99F6E4")
        fig.add_bar(x=o.HORAS, y=-otimo.exportacao, name="solar injetado", marker_color="#FDE68A")
        fig.add_scatter(x=o.HORAS, y=cen.base + otimo.carga_flex, name="consumo da fábrica", mode="lines",
                        line=dict(color=DARK, width=2, shape="hvh"))
        fig.add_scatter(x=o.HORAS, y=cen.base + atual.carga_flex, name="consumo hoje", mode="lines",
                        line=dict(color=RED, width=2, dash="dot", shape="hvh"))
        ponta(fig, cen.tarifa)
        layout(fig, 420, barmode="relative", xaxis=dict(title="hora", dtick=2), yaxis_title="kW")
        st.plotly_chart(fig, width="stretch")
        st.markdown('<div class="hint">Barras abaixo de zero são energia saindo do balanço da fábrica: indo para a bateria '
                    'ou sendo injetada na rede. A linha vermelha pontilhada é o consumo do jeito que a fábrica opera hoje.</div>',
                    unsafe_allow_html=True)

        a, b = st.columns(2)
        with a:
            st.markdown('<div class="eyebrow">Carga da bateria</div>', unsafe_allow_html=True)
            fig = go.Figure(go.Scatter(x=np.arange(o.T + 1), y=otimo.soc, fill="tozeroy", line=dict(color=TEAL, width=3),
                                       fillcolor="rgba(15,118,110,.12)"))
            fig2 = go.Scatter(x=o.HORAS, y=cen.tarifa.preco, name="tarifa", yaxis="y2", line=dict(color=AMB, shape="hvh"))
            fig.add_trace(fig2)
            ponta(fig, cen.tarifa)
            layout(fig, 300, showlegend=False, xaxis=dict(title="hora", dtick=2), yaxis_title="kWh",
                   yaxis2=dict(title="R$/kWh", overlaying="y", side="right", showgrid=False))
            st.plotly_chart(fig, width="stretch")
        with b:
            st.markdown('<div class="eyebrow">Onde está a economia (R$/dia)</div>', unsafe_allow_html=True)
            nomes = ["Hoje", "Só mudar horários", "Horários + bateria"]
            planos = [atual, so_cargas, otimo]
            fig = go.Figure()
            fig.add_bar(x=nomes, y=[p.custo_energia for p in planos], name="energia", marker_color=TEAL)
            fig.add_bar(x=nomes, y=[p.custo_demanda for p in planos], name="demanda", marker_color=AMB)
            fig.add_bar(x=nomes, y=[-p.receita_exportacao for p in planos], name="injeção (crédito)", marker_color=SUN)
            for i, p in enumerate(planos):
                fig.add_annotation(x=nomes[i], y=p.custo_energia + p.custo_demanda, text=brl(p.custo), showarrow=False, yshift=12)
            layout(fig, 300, barmode="relative", yaxis_title="R$/dia")
            st.plotly_chart(fig, width="stretch")
        if bat_e > 0:
            parte = (atual.custo - so_cargas.custo) / max(eco, 1e-9)
            st.markdown(f'<div class="hint">Só mudar os horários das cargas já entrega <b>{100 * parte:.0f}%</b> da economia, '
                        'sem gastar nada. A bateria completa o resto, mas custa caro: a aba Vale comprar a bateria? diz se compensa.</div>',
                        unsafe_allow_html=True)
        como_ler([
            ("Rede", "kW", "Energia comprada da distribuidora naquela hora."),
            ("Solar", "kW", "Geração dos painéis consumida pela própria fábrica."),
            ("Solar injetado", "kW", "Sobra de solar mandada para a rede, com crédito menor que o preço de compra."),
            ("Bateria (carga / descarga)", "kW", "Abaixo de zero é energia indo para a bateria; acima, saindo dela."),
            ("Consumo hoje", "linha vermelha", "Consumo com os horários de hoje, para comparar com o plano."),
            ("Carga da bateria", "kWh", "Energia guardada ao longo do dia. Enche nas horas baratas e esvazia na ponta."),
            ("Energia / demanda / injeção", "R$/dia", "As três partes da conta. Demanda é o pico × tarifa de demanda ÷ 30."),
        ])

# ---------------------------------------------------------------- cargas
with tabs[2]:
    if tabs[2].open:
        st.markdown("### Que horas ligar cada carga")
        st.markdown('<div class="box">Cada barra é uma carga ligada. A faixa clara mostra a <b>janela</b> em que ela pode rodar. '
                    'O otimizador escolhe o horário dentro da janela olhando três coisas ao mesmo tempo: tarifa da hora, '
                    'sol disponível e o pico de demanda, que é cobrado pelo maior valor do mês.</div>', unsafe_allow_html=True)
        fig = go.Figure()
        nomes_c = [c.nome for c in cargas]
        for i, c in enumerate(cargas):
            y = len(cargas) - 1 - i
            fig.add_shape(type="rect", x0=c.janela_ini - .5, x1=c.janela_fim - .5, y0=y - .42, y1=y + .42,
                          fillcolor="#E6F2F1", line_width=0, layer="below")
            fig.add_bar(y=[y + .18], x=[c.duracao], base=[c.inicio_atual - .5], orientation="h", width=.3,
                        marker_color=RED, opacity=.55, name="hoje", showlegend=i == 0,
                        hovertemplate=f"{c.nome}: hoje {c.inicio_atual}h–{c.inicio_atual + c.duracao}h<extra></extra>")
            s = otimo.inicios[c.nome]
            fig.add_bar(y=[y - .18], x=[c.duracao], base=[s - .5], orientation="h", width=.3, marker_color=TEAL,
                        name="otimizado", showlegend=i == 0,
                        hovertemplate=f"{c.nome}: ótimo {s}h–{s + c.duracao}h<extra></extra>")
        ponta(fig, cen.tarifa)
        layout(fig, 70 * len(cargas) + 80, barmode="overlay",
               xaxis=dict(title="hora", range=[-.5, 23.5], dtick=2),
               yaxis=dict(tickvals=list(range(len(cargas))), ticktext=nomes_c[::-1]))
        st.plotly_chart(fig, width="stretch")
        tab = pd.DataFrame({"Carga": nomes_c,
                            "Hoje": [f"{c.inicio_atual}h–{c.inicio_atual + c.duracao}h" for c in cargas],
                            "Otimizado": [f"{otimo.inicios[c.nome]}h–{otimo.inicios[c.nome] + c.duracao}h" for c in cargas],
                            "Energia (kWh)": [c.energia for c in cargas],
                            "Custo médio hoje (R$/kWh)": [cen.tarifa.preco[c.inicio_atual:c.inicio_atual + c.duracao].mean() for c in cargas],
                            "Custo médio otimizado (R$/kWh)": [cen.tarifa.preco[otimo.inicios[c.nome]:otimo.inicios[c.nome] + c.duracao].mean() for c in cargas]})
        st.dataframe(tab.style.format({"Energia (kWh)": "{:.0f}", "Custo médio hoje (R$/kWh)": "R$ {:.2f}",
                                       "Custo médio otimizado (R$/kWh)": "R$ {:.2f}"}), width="stretch", hide_index=True)
        st.markdown('<div class="hint">Nem toda carga vai para a madrugada. Se todas fossem, o pico iria junto para a madrugada '
                    'e a conta de demanda subiria. O otimizador espalha as cargas para manter o pico baixo, e ainda puxa '
                    'as que cabem para o meio do dia, onde o sol paga a energia.</div>', unsafe_allow_html=True)
        como_ler([
            ("Janela", "faixa clara", "Horário em que a carga pode rodar sem atrapalhar a produção."),
            ("Hoje / otimizado", "barras", "Vermelho é o horário de hoje, verde é o do plano."),
            ("Energia", "kWh", "Potência × duração. Não muda com o horário; o que muda é o preço de cada kWh."),
            ("Custo médio", "R$/kWh", "Média da tarifa nas horas em que a carga roda. Não inclui o efeito no pico, que também pesa."),
        ])

# ---------------------------------------------------------------- incerteza solar
with tabs[3]:
    if tabs[3].open:
        st.markdown("### E se o sol não vier como previsto?")
        st.markdown('<div class="box">O plano é feito na véspera com a geração <b>esperada</b>. No dia, passa nuvem. '
                    'Aqui sorteamos centenas de dias de sol (fator do dia ~ <b>Beta</b>, ruído horário ~ <b>lognormal</b>), '
                    'executamos o plano fixo em cada um e comparamos com dois extremos: operar como hoje, e um '
                    'otimizador <b>vidente</b> que sabe de antemão o sol de cada dia.</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        n = c1.slider("Dias sorteados", 50, 400, 100, 50, help="Cada dia sorteado é otimizado de novo pelo vidente. Mais dias, mais lento.")
        media_n = c2.slider("Fator médio de céu limpo", 0.4, 0.95, 0.75, 0.05,
                            help="Fração média da geração de céu limpo que chega aos painéis. 0,75 é um dia típico com algumas nuvens.")
        var_d = c3.slider("Desvio-padrão do fator do dia", 0.02, 0.25, 0.15, 0.01,
                          help="O quanto um dia varia do outro. Maior = dias muito bons e muito ruins.")

        @st.cache_data(show_spinner=False)
        def monte_carlo(args, n, media_n, var_d):
            cen_ = montar(*args)
            rng = np.random.default_rng(7)
            sois = o.sortear_solar(args[2], n, rng, media_n, var_d)
            cen_prev = replace(cen_, solar=args[2] * o.forma_solar() * media_n)
            plano = o.otimizar(cen_prev)
            atual_ = o.plano_atual(cen_prev)
            linhas = []
            for s in sois:
                cen_r = replace(cen_, solar=s)
                linhas.append({"hoje": o.executar(atual_, cen_r, s), "plano": o.executar(plano, cen_r, s),
                               "vidente": o.otimizar(cen_r).custo, "geracao": s.sum()})
            return pd.DataFrame(linhas)

        t0 = time.time()
        with st.spinner(f"Resolvendo {n} dias com e sem previsão..."):
            mc = monte_carlo(args, n, media_n, var_d)
        fig = go.Figure()
        for col, cor, nome in [("hoje", RED, "operar como hoje"), ("plano", TEAL, "plano da véspera"),
                               ("vidente", BLUE, "vidente (sabe o sol)")]:
            fig.add_histogram(x=mc[col], name=nome, marker_color=cor, opacity=.6, nbinsx=30)
        layout(fig, 360, barmode="overlay", xaxis_title="custo do dia (R$)", yaxis_title="dias")
        st.plotly_chart(fig, width="stretch")
        a, b, cc = st.columns(3)
        with a:
            resultado(brl(mc["hoje"].mean() - mc["plano"].mean()),
                      "de economia média por dia seguindo o plano, mesmo com o sol errando.")
        with b:
            resultado(brl(mc["plano"].mean() - mc["vidente"].mean()),
                      "por dia é o <b>valor da informação perfeita</b>: o máximo que valeria pagar por uma previsão de sol sem erro.")
        with cc:
            resultado(f"{100 * (mc['plano'] < mc['hoje']).mean():.0f}%",
                      f"dos {n} dias o plano ganhou de operar como hoje. P95 do custo: {brl(mc['plano'].quantile(.95))}.")
        if kwp == 0:
            st.info("Sem solar instalado não há incerteza: os três custos não variam de um dia para o outro.", icon=":material/info:")
        como_ler([
            ("Operar como hoje", "R$/dia", "Custo de cada dia sorteado com os horários atuais e sem bateria."),
            ("Plano da véspera", "R$/dia", "O plano otimizado com o sol esperado, executado sem mudanças no dia real. A rede cobre a diferença."),
            ("Vidente", "R$/dia", "Otimização refeita sabendo o sol exato de cada dia. Impossível na prática, serve de limite."),
            ("Valor da informação perfeita", "R$/dia", "Plano da véspera menos vidente: o máximo que uma previsão de sol perfeita economizaria."),
            ("P95", "R$", "95% dos dias custam menos que isso. Mede os dias ruins."),
            ("Beta / lognormal", "distribuições", "O fator do dia vem de uma Beta (fica entre 0 e 1); a variação hora a hora, de uma lognormal (nunca negativa)."),
        ])

# ---------------------------------------------------------------- viabilidade
with tabs[4]:
    if tabs[4].open:
        st.markdown("### Vale comprar a bateria?")
        st.markdown('<div class="box">A economia da bateria é medida contra a fábrica já com <b>horários otimizados</b> '
                    '(a melhoria grátis vem primeiro). Para cada tamanho, o fluxo de caixa é: investimento no ano 0, '
                    'economia anual com <b>degradação</b> da bateria e manutenção. VPL, TIR e payback saem desse fluxo.</div>',
                    unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        custo_kwh = c1.number_input("Custo da bateria (R$/kWh)", 500, 8000, 2800, 100,
                                    help="Preço instalado por kWh de capacidade, com inversor.")
        taxa = c2.slider("Taxa de desconto (% a.a.)", 4.0, 20.0, 12.0, 0.5,
                         help="Quanto o dinheiro renderia em outro lugar. Usada para trazer a economia futura a valor de hoje.") / 100
        vida = c3.slider("Vida útil (anos)", 5, 20, 10, help="Anos de operação considerados no fluxo de caixa.")
        degr = c4.slider("Degradação (% a.a.)", 0.0, 5.0, 2.0, 0.5,
                         help="Perda de capacidade por ano. A economia de cada ano cai na mesma proporção.") / 100
        om = 0.01

        @st.cache_data(show_spinner=False)
        def varrer(args):
            tamanhos = np.arange(0, 801, 50)
            base_ = o.otimizar(replace(montar(*args), bateria=o.Bateria())).custo
            eco_ = []
            for e in tamanhos:
                cen_ = montar(args[0], args[1], args[2], float(e), float(e) / 2, args[5], args[6])
                eco_.append(base_ - o.otimizar(cen_).custo)
            return tamanhos, np.array(eco_)

        with st.spinner("Otimizando cada tamanho de bateria..."):
            tamanhos, eco_dia = varrer(args)
        vpls, tirs, pbs = [], [], []
        for e, ed in zip(tamanhos, eco_dia):
            capex = e * custo_kwh
            if e == 0:
                vpls.append(0.0)
                tirs.append(np.nan)
                pbs.append(np.nan)
                continue
            f = o.fluxo_bateria(capex, ed * dias, vida, degr, om)
            vpls.append(o.vpl(f, taxa))
            tirs.append(o.tir(f))
            pbs.append(o.payback(f, taxa))
        vpls, tirs, pbs = (np.array(v, dtype=float) for v in (vpls, tirs, pbs))
        melhor = int(np.argmax(vpls))
        desconto = 1 / (1 + taxa) ** np.arange(1, vida + 1)
        fd = (1 - degr) ** np.arange(vida) * desconto
        # custo por kWh que zera o VPL: E·c·(1 + om·Σdesconto) = economia·Σ(degradação × desconto)
        equilibrio = np.where(tamanhos > 0, eco_dia * dias * fd.sum() /
                              (np.maximum(tamanhos, 1) * (1 + om * desconto.sum())), np.nan)
        i_eq = int(np.nanargmax(equilibrio))
        a, b = st.columns([3, 2])
        with a:
            fig = go.Figure()
            fig.add_bar(x=tamanhos, y=vpls / 1000, marker_color=[DARK if i == melhor else (TEAL if v >= 0 else RED)
                                                                 for i, v in enumerate(vpls)], name="VPL")
            fig.add_scatter(x=tamanhos, y=eco_dia * dias / 1000, name="economia no 1º ano", yaxis="y2",
                            line=dict(color=AMB, width=2), mode="lines+markers")
            layout(fig, 380, xaxis_title="capacidade da bateria (kWh), potência = metade", yaxis_title="VPL (mil R$)",
                   yaxis2=dict(title="economia/ano (mil R$)", overlaying="y", side="right", showgrid=False))
            st.plotly_chart(fig, width="stretch")
        with b:
            if vpls[melhor] <= 0:
                resultado("Não compensa", f"a R$ {custo_kwh:,}/kWh nenhum tamanho tem VPL positivo com taxa de "
                                          f"{100 * taxa:.1f}% a.a. Baixe o custo ou aumente a vida útil para ver o ponto de virada.".replace(",", "."))
            else:
                resultado(f"{tamanhos[melhor]} kWh",
                          f"é o tamanho de maior VPL: {brl(vpls[melhor])}, TIR de {100 * tirs[melhor]:.0f}% a.a. e payback "
                          f"descontado de {pbs[melhor]:.1f} anos.")
            st.markdown(f'<div class="hint">A bateria passa a se pagar abaixo de <b>{brl(equilibrio[i_eq])}/kWh</b> '
                        f'(no tamanho de {tamanhos[i_eq]} kWh). A economia sobe quase em linha reta até a bateria cobrir '
                        'a ponta inteira e aí para: a ponta dura só 3 horas, e bateria maior que isso fica parada.</div>',
                        unsafe_allow_html=True)
        st.dataframe(pd.DataFrame({"Bateria (kWh)": tamanhos, "Investimento": [brl(v) for v in tamanhos * custo_kwh],
                                   "Economia/dia": [brl(v) for v in eco_dia], "VPL": [brl(v) for v in vpls],
                                   "TIR": ["—" if np.isnan(v) else f"{100 * v:.1f}%" for v in tirs],
                                   "Payback desc. (anos)": ["não paga" if np.isnan(v) and e else ("—" if np.isnan(v) else f"{v:.1f}")
                                                            for v, e in zip(pbs, tamanhos)]}),
                     width="stretch", hide_index=True)
        como_ler([
            ("Economia/dia", "R$", "Quanto a bateria economiza a mais, com os horários já otimizados."),
            ("Investimento", "R$", "Capacidade × custo por kWh, pago no ano zero."),
            ("VPL", "R$", "Valor presente líquido: soma da economia de todos os anos trazida a valor de hoje, menos o investimento. Positivo = se paga."),
            ("TIR", "% a.a.", "Taxa de retorno que zera o VPL. Compensa se for maior que a taxa de desconto."),
            ("Payback descontado", "anos", "Quando a economia acumulada, já descontada, cobre o investimento."),
            ("Preço de equilíbrio", "R$/kWh", "Custo por kWh em que o VPL fica exatamente zero. Abaixo dele a bateria se paga."),
            ("Manutenção", "1% a.a.", "Custo anual fixo de operação, como fração do investimento."),
        ])

# ---------------------------------------------------------------- validação
with tabs[5]:
    if tabs[5].open:
        st.markdown("### O otimizador acha mesmo o melhor?")
        st.markdown('<div class="box">Com poucas cargas e sem bateria dá para testar <b>todas</b> as combinações de horário '
                    'e pegar a mais barata, calculando o custo direto, sem passar pelo solver. Se o MILP encontra o mesmo custo, ele está achando o ótimo. Com 6 cargas a força '
                    'bruta já passaria de 10 milhões de combinações; o MILP resolve o dia completo em décimos de segundo.</div>',
                    unsafe_allow_html=True)
        k = st.slider("Quantas cargas testar por força bruta", 1, min(4, len(cargas)), min(3, len(cargas)),
                      help="Com 4 cargas são centenas de milhares de combinações: leva alguns segundos")

        @st.cache_data(show_spinner=False)
        def forca_bruta(args, k):
            cen_ = replace(montar(*args), bateria=o.Bateria())
            cen_ = replace(cen_, cargas=cen_.cargas[:k])
            t0 = time.time()
            custos = [(o.custo_direto(cen_, {c.nome: s for c, s in zip(cen_.cargas, comb)}), comb)
                      for comb in itertools.product(*(c.inicios for c in cen_.cargas))]
            t_fb = time.time() - t0
            t0 = time.time()
            p = o.otimizar(cen_)
            return min(custos)[0], len(custos), t_fb, p.custo, time.time() - t0, [c[0] for c in custos]

        with st.spinner("Testando todas as combinações..."):
            fb, ncomb, tfb, mi, tmi, todos = forca_bruta(args, k)
        c = st.columns(4)
        c[0].metric("Combinações testadas", f"{ncomb:,}".replace(",", "."), help="Todos os horários possíveis das cargas escolhidas, testados um a um.")
        c[1].metric("Melhor por força bruta", brl(fb), f"{tfb:.1f} s", delta_color="off", delta_arrow="off")
        c[2].metric("MILP", brl(mi), f"{1000 * tmi:.0f} ms", delta_color="off", delta_arrow="off")
        c[3].metric("Diferença", f"{abs(fb - mi):.6f}", help="Zero quer dizer que o MILP achou o mesmo ótimo da força bruta.")
        fig = go.Figure(go.Histogram(x=todos, nbinsx=40, marker_color=GRAY))
        fig.add_vline(x=mi, line_color=TEAL, line_width=3, annotation_text="MILP")
        layout(fig, 300, xaxis_title="custo do dia de cada combinação (R$)", yaxis_title="combinações", showlegend=False)
        st.plotly_chart(fig, width="stretch")

        st.markdown('<div class="eyebrow">Restrições conferidas no plano completo</div>', unsafe_allow_html=True)
        oferta = otimo.rede + cen.solar + otimo.descarga_bat
        demanda = cen.base + otimo.carga_flex + otimo.carga_bat + otimo.exportacao
        prox = otimo.soc[:-1] + bat_eta * otimo.carga_bat - otimo.descarga_bat / max(bat_eta, 1e-9)
        checks = [
            ("Balanço de energia em toda hora", np.abs(oferta - demanda).max(), "kW"),
            ("Dinâmica da bateria (SOC)", np.abs(prox - otimo.soc[1:]).max() if bat_e else 0.0, "kWh"),
            ("Bateria dentro de 0 e capacidade", max(-otimo.soc.min(), otimo.soc.max() - bat_e, 0), "kWh"),
            ("Termina o dia com a carga inicial", max(otimo.soc[0] - otimo.soc[-1], 0), "kWh"),
            ("Cargas dentro da janela", sum(not (c.janela_ini <= otimo.inicios[c.nome] <= c.janela_fim - c.duracao)
                                            for c in cargas), "cargas fora"),
            ("Pico ≥ toda compra da rede", max((otimo.rede - otimo.pico).max(), 0), "kW"),
        ]
        st.dataframe(pd.DataFrame([{"Restrição": n_, "Maior violação": f"{v:.2e} {u}", "OK": "✅" if v < 1e-5 else "❌"}
                                   for n_, v, u in checks]), width="stretch", hide_index=True)
        como_ler([
            ("Força bruta", "todas as combinações", "Testa cada horário possível com uma conta direta, sem solver. Garante o ótimo, mas cresce rápido demais."),
            ("MILP", "programação linear inteira mista", "Modelo com variáveis contínuas (energia) e binárias (horário de cada carga), resolvido pelo HiGHS."),
            ("Maior violação", "kW ou kWh", "O quanto a restrição foi desrespeitada no pior momento. Valores como 1e-11 são arredondamento numérico."),
        ])
