"""Despacho ótimo de energia de uma fábrica em um dia típico (passo de 1 h).

Decide, por programação linear inteira mista (HiGHS via scipy.optimize.milp):
- quanto comprar da rede e quanto exportar de solar em cada hora;
- quando carregar e descarregar a bateria;
- em que horário ligar cada carga deslocável (forno, compressor, carregadores...).

Objetivo: menor custo do dia = energia × tarifa da hora − exportação + demanda máxima × tarifa de demanda.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, brentq, milp
from scipy.sparse import lil_matrix

T = 24
HORAS = np.arange(T)


@dataclass
class Tarifa:
    nome: str
    preco: np.ndarray            # R$/kWh em cada hora
    demanda: float = 0.0         # R$/kW·mês sobre o pico do mês
    exportacao: float = 0.0      # R$/kWh pago pela energia injetada
    ponta: tuple = ()            # horas de ponta, só para desenhar

    @property
    def demanda_dia(self) -> float:
        return self.demanda / 30.0


def _perfil(fora: float, ponta: float, horas_ponta, inter: float | None = None, horas_inter=()):
    p = np.full(T, fora, dtype=float)
    if inter is not None:
        p[list(horas_inter)] = inter
    p[list(horas_ponta)] = ponta
    return p


TARIFAS = {
    "Verde A4 (indústria, horo-sazonal)": Tarifa(
        "Verde A4", _perfil(0.48, 2.35, range(18, 21)), demanda=38.0, exportacao=0.30, ponta=(18, 19, 20)),
    "Branca (baixa tensão)": Tarifa(
        "Branca", _perfil(0.62, 1.48, range(18, 21), 0.96, (17, 21)), exportacao=0.40, ponta=(18, 19, 20)),
    "Convencional (preço único)": Tarifa("Convencional", np.full(T, 0.85), exportacao=0.40),
}


@dataclass
class Carga:
    nome: str
    potencia: float      # kW
    duracao: int         # h
    janela_ini: int      # pode começar a partir desta hora
    janela_fim: int      # precisa terminar até esta hora (exclusiva, ≤ 24)
    inicio_atual: int    # como a fábrica faz hoje

    @property
    def inicios(self) -> list[int]:
        return list(range(self.janela_ini, self.janela_fim - self.duracao + 1))

    @property
    def energia(self) -> float:
        return self.potencia * self.duracao


@dataclass
class Bateria:
    energia: float = 0.0         # kWh úteis
    potencia: float = 0.0        # kW de carga/descarga
    eficiencia: float = 0.95     # por sentido (ida e volta = η²)
    soc_inicial: float = 0.5     # fração da energia


@dataclass
class Cenario:
    base: np.ndarray             # kW de carga fixa por hora
    solar: np.ndarray            # kW gerados por hora
    tarifa: Tarifa
    cargas: list[Carga]
    bateria: Bateria = field(default_factory=Bateria)
    limite_rede: float = 1e4     # kW


@dataclass
class Plano:
    custo: float
    custo_energia: float
    custo_demanda: float
    receita_exportacao: float
    rede: np.ndarray
    exportacao: np.ndarray
    carga_bat: np.ndarray
    descarga_bat: np.ndarray
    soc: np.ndarray
    pico: float
    inicios: dict
    carga_flex: np.ndarray
    status: str = "ótimo"

    @property
    def consumo_total(self) -> np.ndarray:
        return self.rede - self.exportacao + self.descarga_bat - self.carga_bat


def perfil_flex(cargas: list[Carga], inicios: dict) -> np.ndarray:
    f = np.zeros(T)
    for c in cargas:
        s = inicios[c.nome]
        f[s:s + c.duracao] += c.potencia
    return f


def otimizar(cen: Cenario, inicios_fixos: dict | None = None) -> Plano:
    """Resolve o MILP do dia. Com inicios_fixos, as cargas ficam no horário dado
    (serve para avaliar o jeito atual e para a validação por força bruta)."""
    bat = cen.bateria
    cargas = cen.cargas
    opcoes = [[inicios_fixos[c.nome]] if inicios_fixos else c.inicios for c in cargas]
    for c, op in zip(cargas, opcoes):
        if not op:
            raise ValueError(f"Carga '{c.nome}' não cabe na janela {c.janela_ini}–{c.janela_fim}h")

    # índices das variáveis
    G, X, CH, DS = 0, T, 2 * T, 3 * T
    SOC = 4 * T                      # T+1 estados
    D = SOC + T + 1
    XS = D + 1
    idx_x = []
    k = XS
    for op in opcoes:
        idx_x.append(list(range(k, k + len(op))))
        k += len(op)
    n = k

    custo = np.zeros(n)
    custo[G:G + T] = cen.tarifa.preco
    custo[X:X + T] = -cen.tarifa.exportacao
    custo[D] = cen.tarifa.demanda_dia

    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    ub[G:G + T] = cen.limite_rede
    ub[X:X + T] = cen.solar
    ub[CH:CH + T] = bat.potencia
    ub[DS:DS + T] = bat.potencia
    ub[SOC:SOC + T + 1] = bat.energia
    soc0 = bat.soc_inicial * bat.energia
    lb[SOC] = ub[SOC] = soc0
    lb[SOC + T] = soc0                 # termina o dia com pelo menos a carga inicial
    integral = np.zeros(n)
    integral[XS:] = 1
    ub[XS:] = 1

    linhas = T + T + T + len(cargas)
    A = lil_matrix((linhas, n))
    lo = np.zeros(linhas)
    hi = np.zeros(linhas)
    r = 0
    eta = bat.eficiencia
    for t in range(T):
        # rede + solar + descarga = base + flex + carga_bat + exportação
        A[r, G + t] = 1
        A[r, DS + t] = 1
        A[r, CH + t] = -1
        A[r, X + t] = -1
        for c, op, ix in zip(cargas, opcoes, idx_x):
            for s, j in zip(op, ix):
                if s <= t < s + c.duracao:
                    A[r, j] = -c.potencia
        lo[r] = hi[r] = cen.base[t] - cen.solar[t]
        r += 1
    for t in range(T):
        A[r, SOC + t + 1] = 1
        A[r, SOC + t] = -1
        A[r, CH + t] = -eta
        A[r, DS + t] = 1 / eta
        r += 1
    for t in range(T):
        A[r, D] = 1
        A[r, G + t] = -1
        lo[r], hi[r] = 0, np.inf
        r += 1
    for ix in idx_x:
        for j in ix:
            A[r, j] = 1
        lo[r] = hi[r] = 1
        r += 1

    res = milp(custo, constraints=LinearConstraint(A.tocsr(), lo, hi), integrality=integral,
               bounds=Bounds(lb, ub), options={"time_limit": 20})
    if res.x is None:
        raise RuntimeError(f"Sem solução: {res.message}")
    x = res.x
    inicios = {}
    for c, op, ix in zip(cargas, opcoes, idx_x):
        inicios[c.nome] = op[int(np.argmax(x[ix]))]
    rede = x[G:G + T]
    exp = x[X:X + T]
    ce = float(cen.tarifa.preco @ rede)
    cd = float(cen.tarifa.demanda_dia * x[D])
    rx = float(cen.tarifa.exportacao * exp.sum())
    return Plano(custo=ce + cd - rx, custo_energia=ce, custo_demanda=cd, receita_exportacao=rx,
                 rede=rede, exportacao=exp, carga_bat=x[CH:CH + T], descarga_bat=x[DS:DS + T],
                 soc=x[SOC:SOC + T + 1], pico=float(x[D]), inicios=inicios,
                 carga_flex=perfil_flex(cargas, inicios),
                 status="ótimo" if res.status == 0 else res.message)


def plano_atual(cen: Cenario) -> Plano:
    """Como a fábrica opera hoje: cargas no horário de costume e sem bateria."""
    sem_bat = Cenario(cen.base, cen.solar, cen.tarifa, cen.cargas, Bateria(), cen.limite_rede)
    return otimizar(sem_bat, {c.nome: c.inicio_atual for c in cen.cargas})


def executar(plano: Plano, cen: Cenario, solar_real: np.ndarray) -> float:
    """Custo real de seguir o plano quando o sol foi outro: bateria e cargas
    seguem o plano, a rede cobre ou absorve a diferença."""
    liquido = cen.base + plano.carga_flex + plano.carga_bat - plano.descarga_bat - solar_real
    rede = np.maximum(liquido, 0)
    exp = np.maximum(-liquido, 0)
    t = cen.tarifa
    return float(t.preco @ rede + t.demanda_dia * rede.max() - t.exportacao * exp.sum())


def custo_direto(cen: Cenario, inicios: dict) -> float:
    """Custo sem bateria e com horários fixos, calculado sem solver: a rede cobre
    o que falta e o solar que sobra é injetado. Serve de conferência independente."""
    liquido = cen.base + perfil_flex(cen.cargas, inicios) - cen.solar
    rede = np.maximum(liquido, 0)
    t = cen.tarifa
    return float(t.preco @ rede + t.demanda_dia * rede.max() - t.exportacao * np.maximum(-liquido, 0).sum())


# ------------------------------------------------------------------ solar

def forma_solar() -> np.ndarray:
    """Curva de céu limpo normalizada (pico = 1 ao meio-dia), nascer 6 h, pôr 18 h."""
    h = HORAS + 0.5
    return np.clip(np.sin(np.pi * (h - 6) / 12), 0, None)


def sortear_solar(kwp: float, n: int, rng: np.random.Generator, media_nuvem: float = 0.75,
                  var_dia: float = 0.12, ruido_hora: float = 0.18) -> np.ndarray:
    """n dias de geração. Fator do dia ~ Beta com a média e o desvio dados; cada
    hora ainda varia com ruído lognormal (nuvens passando)."""
    m, v = media_nuvem, var_dia ** 2
    comum = m * (1 - m) / v - 1
    a, b = m * comum, (1 - m) * comum
    k = rng.beta(a, b, size=(n, 1))
    ruido = rng.lognormal(-ruido_hora ** 2 / 2, ruido_hora, size=(n, T))
    return np.clip(kwp * forma_solar() * k * ruido, 0, kwp)


# ------------------------------------------------------------------ finanças

def vpl(fluxos: np.ndarray, taxa: float) -> float:
    return float(sum(f / (1 + taxa) ** i for i, f in enumerate(fluxos)))


def tir(fluxos: np.ndarray) -> float:
    if fluxos[1:].sum() <= -fluxos[0]:
        return float("nan")
    return float(brentq(lambda r: vpl(fluxos, r), -0.99, 10))


def payback(fluxos: np.ndarray, taxa: float = 0.0) -> float:
    acumulado = np.cumsum([f / (1 + taxa) ** i for i, f in enumerate(fluxos)])
    if acumulado[-1] < 0:
        return float("nan")
    i = int(np.argmax(acumulado >= 0))
    anterior = acumulado[i - 1]
    return i - 1 + (-anterior) / (acumulado[i] - anterior)


def fluxo_bateria(capex: float, economia_ano: float, anos: int, degradacao: float,
                  om_frac: float) -> np.ndarray:
    anos_arr = np.arange(1, anos + 1)
    entradas = economia_ano * (1 - degradacao) ** (anos_arr - 1) - om_frac * capex
    return np.concatenate([[-capex], entradas])


# ------------------------------------------------------------------ fábrica de exemplo

def base_padrao() -> np.ndarray:
    """Dois turnos (6–22 h): iluminação, máquinas fixas e ar-condicionado."""
    b = np.full(T, 45.0)
    b[6:22] = 150.0
    b[12] = 110.0                       # almoço
    b[13:17] += 15.0                    # ar-condicionado à tarde
    return b


CARGAS_PADRAO = [
    Carga("Forno de cura", 90, 4, 6, 22, inicio_atual=15),
    Carga("Compressor + pulmão", 55, 3, 0, 24, inicio_atual=17),
    Carga("Carga de empilhadeiras", 30, 4, 0, 24, inicio_atual=18),
    Carga("Chiller (pré-resfriar)", 45, 3, 0, 14, inicio_atual=10),
    Carga("Bomba de reúso", 25, 2, 0, 24, inicio_atual=19),
    Carga("Lavagem de filtros", 40, 2, 7, 21, inicio_atual=16),
]


def cenario_padrao(tarifa: str = "Verde A4 (indústria, horo-sazonal)", kwp: float = 120.0,
                   bateria: Bateria | None = None) -> Cenario:
    return Cenario(base_padrao(), kwp * forma_solar() * 0.75, TARIFAS[tarifa], list(CARGAS_PADRAO),
                   bateria or Bateria(200, 100))
