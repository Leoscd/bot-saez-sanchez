"""Modo consulta: lo que ve un DT que hace un reemplazo en la obra demo Casa Lomas."""
import json

import pytest

from obra_bot import equipo, herramientas, nucleo, obras, reporte
from obra_bot.whatsapp_api import variantes_ar


@pytest.fixture
def borrador():
    b, _ = reporte.obtener_o_crear(obras.obtener("casa-lomas"), nucleo.hoy(), "test:reemplazo",
                                   "Reemplazo (test)", "test:reemplazo")
    b.estado = "borrador"
    b.guardar()
    return b


def _ejecutar(b, nombre, **args):
    return json.loads(herramientas.ejecutar(b, nombre, args))


def test_resumen_obra_marca_atraso_critico_y_notas(borrador):
    r = _ejecutar(borrador, "resumen_obra")
    assert r["avance_real_pct"] < r["avance_previsto_pct"]
    atrasada = r["tareas_atrasadas"][0]
    assert atrasada["id_tarea"] == "T-040" and atrasada["critica"] and atrasada["pct_real"] == 40
    assert r["ultimo_reporte"]["dt"] == "Martín Gómez (demo)"
    assert r["notas_abiertas"] == 2 and r["notas_vencidas"] == 1


def test_ultimos_reportes_del_mas_nuevo_al_mas_viejo(borrador):
    r = _ejecutar(borrador, "ultimos_reportes", cantidad=2)
    assert len(r) == 2
    assert r[0]["fecha"] > r[1]["fecha"]
    assert "ventana" in r[0]["resumen"]
    assert r[1]["jornada"]["causa"] == "falta de material"


def test_notas_y_pedidos_pendientes(borrador):
    notas = _ejecutar(borrador, "notas_abiertas")
    assert {n["tipo"] for n in notas} == {"nota_de_pedido", "orden_de_servicio"}
    assert any(n["vencida"] for n in notas)
    pedidos = _ejecutar(borrador, "pedidos_pendientes")
    ladrillo = pedidos["pedidos_sin_recibir"][0]
    assert ladrillo["material"].startswith("ladrillo") and ladrillo["entrega_vencida"]
    assert pedidos["marcados_pendientes"][0]["id_tarea"] == "T-070"


def test_fotos_recientes_y_envio(borrador):
    fotos = _ejecutar(borrador, "fotos_recientes", id_tarea="T-040", cantidad=3)
    assert len(fotos) == 3 and all(f["id_tarea"] == "T-040" for f in fotos)
    r = _ejecutar(borrador, "enviar_fotos", foto_ids=[fotos[0]["foto_id"], 99999])
    assert r["se_envian_despues_de_tu_respuesta"] == [fotos[0]["foto_id"]]
    assert r["no_encontradas"] == [99999]
    assert len(borrador.salientes) == 1 and borrador.salientes[0].exists()


def test_enviar_fotos_no_manda_fotos_de_otra_obra(borrador):
    otra, _ = reporte.obtener_o_crear(obras.obtener("local-mate-de-luna"), nucleo.hoy(), "test:otra",
                                      "Otra (test)", "test:otra")
    foto_local = _ejecutar(otra, "fotos_recientes")[0]["foto_id"]
    r = _ejecutar(borrador, "enviar_fotos", foto_ids=[foto_local])
    assert r["no_encontradas"] == [foto_local]


def test_buscar_en_reportes_ignora_acentos(borrador):
    r = _ejecutar(borrador, "buscar_en_reportes", texto="corralon ladrillo")
    assert r and all("corral" in x["texto"].lower() for x in r)
    assert _ejecutar(borrador, "buscar_en_reportes", texto="xilofón") == "Sin coincidencias"


def test_reporte_confirmado_solo_permite_consultas(borrador):
    borrador.estado = "confirmado"
    with pytest.raises(ValueError, match="confirmado"):
        herramientas.ejecutar(borrador, "registrar_jornada", {"tipo": "completa"})
    assert _ejecutar(borrador, "resumen_obra")["obra"]


def test_borrador_solo_con_consultas_no_se_recuerda(borrador):
    assert not reporte.tiene_datos(borrador)
    assert all(b.id != borrador.id for b in nucleo.para_recordar())


@pytest.mark.parametrize("entrada", [
    "+54 9 381 555-0000", "5493815550000", "543815550000", "0381 15 555-0000", "381 5550000", "38115-5550000",
])
def test_normalizar_celular_argentino(entrada):
    assert equipo.normalizar(entrada) == "5493815550000"


def test_variantes_de_numero_argentino():
    v = variantes_ar("5493815550000")
    assert v[0] == "5493815550000" and "543815550000" in v and "54381155550000" in v
    assert variantes_ar("15556563099") == ["15556563099"]
