import itertools
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import otimizador as o  # noqa: E402


@pytest.fixture(scope="module")
def cen():
    return o.cenario_padrao()


@pytest.fixture(scope="module")
def plano(cen):
    return o.otimizar(cen)


def test_balanco_de_energia_fecha_toda_hora(cen, plano):
    oferta = plano.rede + cen.solar + plano.descarga_bat
    demanda = cen.base + plano.carga_flex + plano.carga_bat + plano.exportacao
    assert np.allclose(oferta, demanda, atol=1e-6)


def test_bateria_respeita_limites_e_dinamica(cen, plano):
    b = cen.bateria
    assert plano.soc.min() >= -1e-6 and plano.soc.max() <= b.energia + 1e-6
    assert plano.carga_bat.max() <= b.potencia + 1e-6
    prox = plano.soc[:-1] + b.eficiencia * plano.carga_bat - plano.descarga_bat / b.eficiencia
    assert np.allclose(prox, plano.soc[1:], atol=1e-6)
    assert plano.soc[-1] >= plano.soc[0] - 1e-6


def test_cargas_dentro_da_janela(cen, plano):
    for c in cen.cargas:
        s = plano.inicios[c.nome]
        assert c.janela_ini <= s and s + c.duracao <= c.janela_fim


def test_milp_bate_com_forca_bruta():
    cargas = [o.Carga("A", 80, 3, 0, 24, 18), o.Carga("B", 50, 2, 6, 22, 18), o.Carga("C", 40, 4, 0, 24, 17)]
    cen = o.Cenario(o.base_padrao(), 100 * o.forma_solar() * 0.7, o.TARIFAS["Verde A4 (indústria, horo-sazonal)"],
                    cargas, o.Bateria())
    melhor = min(o.custo_direto(cen, dict(zip("ABC", comb)))
                 for comb in itertools.product(*(c.inicios for c in cargas)))
    assert o.otimizar(cen).custo == pytest.approx(melhor, rel=1e-6)


def test_bateria_nunca_piora(cen):
    sem = o.otimizar(replace(cen, bateria=o.Bateria())).custo
    custos = [o.otimizar(replace(cen, bateria=o.Bateria(e, e / 2))).custo for e in (50, 150, 300)]
    assert all(c <= sem + 1e-6 for c in custos)
    assert custos == sorted(custos, reverse=True)


def test_tarifa_unica_sem_demanda_nao_tem_o_que_deslocar():
    cen = o.cenario_padrao("Convencional (preço único)", kwp=0, bateria=o.Bateria())
    assert o.otimizar(cen).custo == pytest.approx(o.plano_atual(cen).custo, rel=1e-9)


def test_executar_com_o_sol_previsto_reproduz_o_custo(cen, plano):
    assert o.executar(plano, cen, cen.solar) == pytest.approx(plano.custo, rel=1e-6)


def test_otimo_ganha_do_jeito_atual(cen, plano):
    assert plano.custo < o.plano_atual(cen).custo


def test_sorteio_solar_tem_a_media_pedida():
    rng = np.random.default_rng(0)
    s = o.sortear_solar(100, 4000, rng, media_nuvem=0.7)
    ceu_limpo = 100 * o.forma_solar()
    assert s.sum() / (4000 * ceu_limpo.sum()) == pytest.approx(0.7, abs=0.02)
    assert s.max() <= 100


def test_financas():
    fluxo = np.array([-1000, 400, 400, 400])
    assert o.vpl(fluxo, o.tir(fluxo)) == pytest.approx(0, abs=1e-6)
    assert o.payback(fluxo) == pytest.approx(2.5)
    assert np.isnan(o.payback(np.array([-1000, 100, 100])))


def test_custo_direto_igual_ao_lp_com_horario_fixo(cen):
    sem = replace(cen, bateria=o.Bateria())
    inicios = {c.nome: c.inicio_atual for c in cen.cargas}
    assert o.custo_direto(sem, inicios) == pytest.approx(o.otimizar(sem, inicios).custo, rel=1e-9)


def test_preco_de_equilibrio_zera_o_vpl():
    taxa, vida, degr, om, eco = 0.12, 10, 0.02, 0.01, 30000.0
    desconto = 1 / (1 + taxa) ** np.arange(1, vida + 1)
    capex = eco * ((1 - degr) ** np.arange(vida) * desconto).sum() / (1 + om * desconto.sum())
    assert o.vpl(o.fluxo_bateria(capex, eco, vida, degr, om), taxa) == pytest.approx(0, abs=1e-6)
