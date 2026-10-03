<div align="center">

# Despacho de Energia da Fábrica

**Que horas ligar cada máquina para pagar menos luz?**

Um painel interativo que otimiza o dia de energia de uma fábrica: em que horário ligar as cargas
que podem mudar de horário, quando carregar e descarregar uma bateria e quanto usar do solar do
telhado, com tarifa horária e cobrança por pico de demanda.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![SciPy](https://img.shields.io/badge/SciPy_MILP-HiGHS-8CAAE6?logo=scipy&logoColor=white)](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Plotly](https://img.shields.io/badge/Plotly-3F4F75?logo=plotly&logoColor=white)](https://plotly.com/python/)
[![pytest](https://img.shields.io/badge/testes-pytest-0A9EDC?logo=pytest&logoColor=white)](tests/)

`Mesmo custo que a força bruta em 6.006 combinações, resolvido em 14 ms`

**Português** &nbsp;·&nbsp; [English](README.en.md)

</div>

![Painel com o despacho otimizado da fábrica](docs/preview.png)

---

## O problema

Na tarifa horo-sazonal da indústria, o kWh no horário de ponta (18 h às 21 h) custa cerca de cinco
vezes o kWh do resto do dia. Além disso, a conta cobra pela **demanda**: o maior consumo
registrado no mês, em kW, mesmo que tenha durado uma hora só.

Muita carga de fábrica não precisa rodar num horário fixo. O forno de cura pode rodar de manhã ou
de tarde, as empilhadeiras podem carregar de madrugada, o chiller pode pré-resfriar antes do turno.
A pergunta do projeto é:

> Dado o que precisa rodar, o sol esperado e uma bateria, qual é o plano de energia mais barato para o dia?

## O modelo

Programação linear inteira mista (MILP), resolvida com o HiGHS pelo `scipy.optimize.milp`, com
passo de 1 hora:

| Decisão | Tipo | Limites |
|---|---|---|
| Compra da rede em cada hora | contínua | ≥ 0 |
| Injeção de solar na rede | contínua | ≤ geração da hora |
| Carga e descarga da bateria | contínua | ≤ potência da bateria |
| Estado de carga da bateria | contínua | entre 0 e a capacidade; termina o dia com a carga inicial |
| Horário de início de cada carga | **binária** | só inícios que cabem na janela da carga |
| Pico de demanda | contínua | ≥ compra da rede em toda hora |

**Objetivo:** Σ tarifa(h) × rede(h) − injeção × crédito + pico × tarifa de demanda / 30.

**Balanço em toda hora:** rede + solar + descarga = consumo fixo + cargas ligadas + carga da bateria + injeção.

**Hipóteses:** dia típico de operação, previsão de consumo fixo conhecida, eficiência da bateria
igual nos dois sentidos, tarifas ilustrativas na ordem de grandeza das distribuidoras paulistas.

## O que cada aba mostra

| Aba | Pergunta | Resultado com a fábrica padrão |
|---|---|---|
| Despacho | Quanto custa o dia e de onde vem a energia em cada hora? | de R$ 3.329 para R$ 2.128 por dia (−36%); pico de 325 kW para 150 kW |
| Horários das cargas | Que horas ligar cada carga? | todas saem da ponta; mudar só os horários já entrega 69% da economia, sem investimento |
| Incerteza do sol | E se o sol não vier como previsto? | o plano da véspera ganhou de operar como hoje em 100% de 150 dias sorteados; valor da previsão perfeita: R$ 18/dia |
| Vale comprar a bateria? | Qual tamanho tem o melhor VPL? | a R$ 2.800/kWh, só a bateria pequena (50 kWh) se paga; ponto de equilíbrio em R$ 2.856/kWh |
| Validação | O otimizador acha mesmo o melhor? | mesmo custo que testar todas as 6.006 combinações; restrições conferidas no plano |

<p align="center">
  <img src="docs/despacho.png" width="49%" alt="Origem da energia em cada hora: rede, solar e bateria">
  <img src="docs/cargas.png" width="49%" alt="Horário de cada carga hoje e no plano otimizado">
</p>

O resultado que mais surpreende é que **nem toda carga vai para a madrugada**. Se fossem todas, o
pico de demanda iria junto e a conta subiria. O otimizador espalha as cargas para manter o pico
baixo e puxa para o meio do dia as que cabem, onde o solar paga a energia.

<p align="center">
  <img src="docs/incerteza.png" width="49%" alt="Distribuição do custo do dia com o sol sorteado">
  <img src="docs/viabilidade.png" width="49%" alt="VPL de cada tamanho de bateria">
</p>

### Incerteza do sol

O plano é feito na véspera com a geração esperada. A aba sorteia centenas de dias: o fator de céu
limpo do dia vem de uma **Beta** com a média e o desvio escolhidos, e cada hora ainda tem ruído
**lognormal** (nuvem passando). Para cada dia sorteado o painel calcula três custos: operar como
hoje, seguir o plano fixo da véspera e um otimizador "vidente" que conhece o sol do dia. A diferença
entre os dois últimos é o **valor da informação perfeita**, o máximo que valeria pagar por uma
previsão do tempo sem erro.

### Viabilidade da bateria

A economia da bateria é medida contra a fábrica já com horários otimizados, porque essa melhoria é
de graça e vem primeiro. O fluxo de caixa considera investimento, degradação anual da capacidade e
manutenção de 1% do investimento ao ano. Do fluxo saem VPL, TIR, payback descontado e o preço por
kWh em que a bateria passa a se pagar.

## Validação

| Teste | O que verifica |
|---|---|
| `test_milp_bate_com_forca_bruta` | com 3 cargas, o MILP acha o mesmo custo que testar todas as combinações |
| `test_custo_direto_igual_ao_lp_com_horario_fixo` | o custo do solver bate com uma conta direta, sem solver |
| `test_balanco_de_energia_fecha_toda_hora` | oferta = demanda em todas as 24 horas |
| `test_bateria_respeita_limites_e_dinamica` | estado de carga, potência e eficiência coerentes hora a hora |
| `test_cargas_dentro_da_janela` | nenhuma carga fora da janela permitida |
| `test_bateria_nunca_piora` | bateria maior nunca aumenta o custo ótimo |
| `test_tarifa_unica_sem_demanda_nao_tem_o_que_deslocar` | com preço único e sem demanda, otimizar não muda o custo |
| `test_executar_com_o_sol_previsto_reproduz_o_custo` | o simulador de execução reproduz o custo do plano |
| `test_sorteio_solar_tem_a_media_pedida` | o sorteio Beta × lognormal tem a média de céu limpo escolhida |
| `test_financas` / `test_preco_de_equilibrio_zera_o_vpl` | VPL, TIR, payback e preço de equilíbrio |

```bash
python -m pytest tests
```

## Como rodar

```bash
git clone https://github.com/caiogadotti/despacho-energia-fabrica.git
cd despacho-energia-fabrica
pip install -r requirements.txt
streamlit run app.py
```

### Publicar no Streamlit Community Cloud

1. Entre em [share.streamlit.io](https://share.streamlit.io) com a conta do GitHub.
2. Clique em **Create app** e escolha este repositório, branch `main`, arquivo `app.py`.
3. Clique em **Deploy**. O tema claro vem de `.streamlit/config.toml`.

## Estrutura

```
app.py                  painel Streamlit (cinco abas)
otimizador.py           MILP do despacho, sorteio solar, simulação de execução e finanças
tests/test_otimizador.py
.streamlit/config.toml  tema visual
docs/                   imagens do README
```

## Referências

- ANEEL. *Procedimentos de Regulação Tarifária (PRORET)*, Submódulo 7.1: Procedimentos gerais. Modalidades tarifárias horárias verde e azul.
- PALENSKY, P.; DIETRICH, D. Demand side management: demand response, intelligent energy systems, and smart loads. *IEEE Transactions on Industrial Informatics*, v. 7, n. 3, p. 381-388, 2011.
- HUANGFU, Q.; HALL, J. A. J. Parallelizing the dual revised simplex method. *Mathematical Programming Computation*, v. 10, p. 119-142, 2018. (HiGHS)
- BIRGE, J. R.; LOUVEAUX, F. *Introduction to Stochastic Programming*. 2. ed. Springer, 2011. (valor da informação perfeita)
- GITMAN, L. J. *Princípios de Administração Financeira*. Pearson.

---

Caio Gadotti · Projeto de portfólio do curso de Engenharia de Sistemas Ciberfísicos (ESCF) da PUC-SP.
