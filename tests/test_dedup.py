"""`voight dedup`: eliminar duplicados (GIFT y XML), log de eliminaciones y TUI de revisión."""

import asyncio
import contextlib
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.lector import leer_archivos, unidades_de
from voight.core.converter import gift_to_xml
from voight.core.deduplicar import Revision, agrupar, aplicar, registrar

runner = CliRunner()

PREGUNTA = "::Punteros{n}:: ¿Qué guarda un puntero en lenguaje C cuando se declara?\n{{=Una dirección de memoria ~Un entero ~Un carácter ~Nada}}\n"
COMPLETA = ("::Punteros:: ¿Qué guarda un puntero en lenguaje C cuando se declara?\n"
            "{=Una dirección de memoria #Bien ~Un entero #No ~Un carácter #No ~Nada #No}\n")


def _banco(tmp_path, archivos: dict) -> Path:
    raiz = tmp_path / "banco"
    for nombre, contenido in archivos.items():
        ruta = raiz / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
    return raiz


def _leer(raiz):
    with contextlib.redirect_stdout(io.StringIO()):
        archivos = leer_archivos(sorted(raiz.rglob("*.gift")) + sorted(raiz.rglob("*.xml")))
    return archivos, [u for u in unidades_de(archivos) if u.pregunta]


def test_conserva_la_mas_completa_y_detecta_entre_formatos(tmp_path):
    raiz = _banco(tmp_path, {
        "a/p1.gift": PREGUNTA.format(n=""),
        "b/p2.gift": COMPLETA,
        "c/p3.xml": gift_to_xml(PREGUNTA.format(n="")),
    })
    _, unidades = _leer(raiz)
    grupos = agrupar(unidades, 0.9)
    assert len(grupos) == 1
    assert grupos[0].conservada.archivo.name == "p2.gift"
    assert sorted(u.archivo.name for u, _ in grupos[0].duplicadas) == ["p1.gift", "p3.xml"]
    assert agrupar(unidades, 0.9, "primera")[0].conservada.archivo.name == "p1.gift"


def test_no_son_duplicados_con_otra_correcta_otro_tipo_u_otro_enunciado(tmp_path):
    otra_correcta = PREGUNTA.format(n="").replace("=Una dirección", "~Una dirección").replace("~Un entero", "=Un entero")
    otro_enunciado = PREGUNTA.format(n="").replace("cuando se declara", "cuando se libera")
    raiz = _banco(tmp_path, {
        "p1.gift": PREGUNTA.format(n=""),
        "p2.gift": otra_correcta,
        "p3.gift": otro_enunciado,
        "p4.gift": "::Punteros:: ¿Qué guarda un puntero en lenguaje C cuando se declara? {T}\n",
    })
    _, unidades = _leer(raiz)
    assert agrupar(unidades, 0.85) == []


def test_eliminar_en_gift_y_xml_conserva_categorias_y_comentarios_ajenos(tmp_path):
    xml = gift_to_xml(PREGUNTA.format(n="") + "\n::Otra:: ¿Cuánto es 2+2? {=4 ~3 ~5}\n")
    xml = xml.replace("<quiz>", '<quiz>\n<!-- question: 1 -->', 1)
    raiz = _banco(tmp_path, {
        "multi.gift": "$CATEGORY: $course$/C\n\n" + COMPLETA + "\n::Otra:: ¿Cuánto es 3+3? {=6 ~5 ~7}\n",
        "solo.gift": "$CATEGORY: $course$/C\n" + PREGUNTA.format(n=""),
        "banco.xml": xml,
    })
    archivos, unidades = _leer(raiz)
    grupos = agrupar(unidades, 0.9)
    cambios = aplicar(archivos, grupos)
    assert [p.name for p in cambios["borrados"]] == ["solo.gift"]
    assert [p.name for p in cambios["modificados"]] == ["banco.xml"]
    texto = (raiz / "banco.xml").read_text(encoding="utf-8")
    assert "question: 1" not in texto and "¿Cuánto es 2+2?" in texto
    assert [q.findtext("name/text") for q in ET.fromstring(texto).findall("question")] == ["Otra"]
    assert (raiz / "multi.gift").read_text(encoding="utf-8").startswith("$CATEGORY: $course$/C\n\n::Punteros::")


def test_log_con_rutas_completas(tmp_path):
    raiz = _banco(tmp_path, {"u1/a.gift": COMPLETA, "u2/b.gift": PREGUNTA.format(n="")})
    archivos, unidades = _leer(raiz)
    grupos = agrupar(unidades, 0.9)
    cambios = aplicar(archivos, grupos)
    log = tmp_path / "dedup.log"
    assert registrar(grupos, cambios, log, 0.9) == 1
    assert registrar(grupos, cambios, log, 0.9) == 1  # se agrega al final
    lineas = log.read_text(encoding="utf-8").splitlines()
    assert lineas[0].split("\t") == ["fecha", "accion", "eliminado", "conservado", "similitud", "umbral", "tipo", "titulo"]
    campos = lineas[1].split("\t")
    assert campos[1] == "archivo-borrado"
    assert campos[2] == str((raiz / "u2" / "b.gift").resolve()) and Path(campos[2]).is_absolute()
    assert campos[3] == str((raiz / "u1" / "a.gift").resolve())
    assert campos[6:] == ["MC", "Punteros"]
    assert len(lineas) == 3


def test_cli_simula_por_defecto_y_aplica_con_log(tmp_path):
    raiz = _banco(tmp_path, {"u1/a.gift": COMPLETA, "u2/b.gift": PREGUNTA.format(n="")})
    log = tmp_path / "registro.tsv"
    res = runner.invoke(cli, ["dedup", str(raiz), "-r", "-s", "0.9", "--log", str(log)])
    assert res.exit_code == 0, res.output
    assert "Se eliminarían 1" in res.output and (raiz / "u2" / "b.gift").exists() and not log.exists()
    res = runner.invoke(cli, ["dedup", str(raiz), "-r", "-s", "0.9", "--log", str(log), "--aplicar", "--json",
                              "--respaldo", str(tmp_path / "respaldos")])
    datos = json.loads(res.output)
    assert datos["eliminadas"] == 1 and datos["log"] == str(log.resolve())
    assert datos["grupos"][0]["elimina"][0]["archivo"].endswith("b.gift")
    assert not (raiz / "u2" / "b.gift").exists() and log.exists()
    res = runner.invoke(cli, ["dedup", str(raiz), "-r", "-s", "0.9"])
    assert "No hay duplicados" in res.output


def test_revision_manual(tmp_path):
    raiz = _banco(tmp_path, {"a.gift": COMPLETA, "b.gift": PREGUNTA.format(n=""), "c.gift": PREGUNTA.format(n="")})
    _, unidades = _leer(raiz)
    revision = Revision(agrupar(unidades, 0.9))
    principal, b, c = revision.miembros[0]
    assert revision.a_eliminar() == 2
    revision.alternar(0, b)
    revision.alternar(0, principal)  # la principal no se elimina nunca
    assert revision.a_eliminar() == 1 and not revision.se_elimina(principal)
    revision.hacer_principal(0, c)
    assert revision.principal[0] is c and revision.se_elimina(principal) and not revision.se_elimina(c)
    assert [(g.conservada, [u for u, _ in g.duplicadas]) for g in revision.grupos()] == [(c, [principal])]
    revision.conservar_todas(0)
    assert revision.grupos() == []


def _tui(raiz, log, teclas):
    pytest.importorskip("textual", reason="TUI: requiere el extra opcional 'tui' (uv sync --extra tui)")
    from voight.tui.dedup import DedupApp

    archivos, unidades = _leer(raiz)
    app = DedupApp(archivos, Revision(agrupar(unidades, 0.9)), 0.9, log, log.parent / "respaldos")

    async def correr():
        async with app.run_test(size=(140, 40)) as pilot:
            for tecla in teclas:
                await pilot.press(tecla)
            await pilot.pause()
        return app.return_value

    return asyncio.run(correr())


def test_tui_decide_y_aplica_con_confirmacion(tmp_path):
    raiz = _banco(tmp_path, {"a.gift": COMPLETA, "b.gift": PREGUNTA.format(n=""), "c.gift": PREGUNTA.format(n="")})
    log = tmp_path / "dedup.log"
    # Conservar el duplicado que se ve (b) y aplicar: sólo se elimina c.
    resultado = _tui(raiz, log, ["d", "a", "s"])
    assert resultado["eliminadas"] == 1
    assert (resultado["respaldo"] / "manifiesto.json").is_file()
    assert (raiz / "a.gift").exists() and (raiz / "b.gift").exists() and not (raiz / "c.gift").exists()
    assert str((raiz / "c.gift").resolve()) in log.read_text(encoding="utf-8")


def test_tui_salir_o_cancelar_no_elimina_nada(tmp_path):
    raiz = _banco(tmp_path, {"a.gift": COMPLETA, "b.gift": PREGUNTA.format(n="")})
    log = tmp_path / "dedup.log"
    assert _tui(raiz, log, ["a", "escape", "q"]) is None
    assert (raiz / "b.gift").exists() and not log.exists()


def test_confirmar_con_jev_descarta_los_que_piden_otra_cosa(tmp_path):
    from voight.core.deduplicar import confirmar_con_jev

    raiz = _banco(tmp_path, {
        "a.gift": COMPLETA,
        "b.gift": PREGUNTA.format(n=""),
        "c.gift": PREGUNTA.format(n="").replace("::Punteros::", "::Punteros (otra)::"),
    })
    _, unidades = _leer(raiz)
    grupos = agrupar(unidades, 0.85)
    assert len(grupos[0].duplicadas) == 2

    class Cliente:
        def __init__(self):
            self.estados = []

        def consultar(self, state, questions):
            self.estados.append(state)
            titulo = state["pregunta_b"].get("titulo", "")
            return {"answers": {"misma": {"noul": 0.1 if "otra" in titulo else 0.9}}}

    cliente = Cliente()
    filtrados, descartados = confirmar_con_jev(grupos, cliente, exactas=1.1)
    assert [u.archivo.name for u, _ in filtrados[0].duplicadas] == ["b.gift"]
    assert descartados[0]["descartado"].endswith("c.gift") and descartados[0]["probabilidad"] == 0.1
    assert set(cliente.estados[0]) == {"pregunta_a", "pregunta_b"}
    assert "Bien" not in str(cliente.estados[0])  # sin feedback


def test_respaldo_y_restaurar(tmp_path):
    raiz = _banco(tmp_path, {
        "u1/a.gift": COMPLETA,
        "u2/b.gift": PREGUNTA.format(n=""),
        "u3/multi.gift": PREGUNTA.format(n="") + "\n::Otra:: ¿Cuánto es 3+3? {=6 ~5 ~7}\n",
    })
    originales = {p: p.read_bytes() for p in raiz.rglob("*.gift")}
    respaldos = tmp_path / "respaldos"
    opciones = ["-s", "0.9", "--log", str(tmp_path / "log"), "--respaldo", str(respaldos)]
    datos = json.loads(runner.invoke(cli, ["dedup", str(raiz), "-r", "--aplicar", "--json"] + opciones).output)
    assert not (raiz / "u2" / "b.gift").exists() and "Punteros" not in (raiz / "u3" / "multi.gift").read_text(encoding="utf-8")
    manifiesto = json.loads((Path(datos["respaldo"]) / "manifiesto.json").read_text(encoding="utf-8"))
    assert {Path(e["ruta"]).name: e["accion"] for e in manifiesto["archivos"]} == {"b.gift": "borrado", "multi.gift": "modificado"}

    # Un archivo editado después del dedup no se pisa sin --forzar.
    (raiz / "u3" / "multi.gift").write_text("::Otra:: editada {T}\n", encoding="utf-8")
    res = runner.invoke(cli, ["dedup", "--restaurar", "ultimo"] + opciones)
    assert res.exit_code == 1 and "multi.gift: cambió después del dedup" in res.output
    assert (raiz / "u2" / "b.gift").read_bytes() == originales[raiz / "u2" / "b.gift"]
    res = runner.invoke(cli, ["dedup", "--restaurar", Path(datos["respaldo"]).name, "--forzar", "--json"] + opciones)
    assert res.exit_code == 0 and len(json.loads(res.output)["sin_cambios"]) == 1
    assert {p: p.read_bytes() for p in raiz.rglob("*.gift")} == originales

    res = runner.invoke(cli, ["dedup", "--restaurar", "no-existe"] + opciones)
    assert res.exit_code == 1 and "Disponibles" in res.output
