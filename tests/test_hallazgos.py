"""Hallazgos de health navegables, arreglos automáticos y la TUI que los usa."""

import asyncio

import pytest

from voight.core.banco import expandir_rutas, parse_archivo
from voight.core.hallazgos import ARREGLOS, archivos_de, arreglar, elementos, hallazgos
from voight.core.moodle_health import auditar_archivos

# `=` en el código sin proteger: GIFT lo toma como respuesta correcta.
SIN_PROTEGER = "::Asignación:: ¿Qué imprime `int x = 3; printf(\"%d\", x);`?\n{=3 #Bien ~0 #No ~x #No}\n"
SIN_LENGUAJE = "::Bloque:: ¿Qué hace?\n```\nint x;\nprintf(\"%d\", x);\n```\n{=Basura #Bien ~Nada #No ~Falla #No}\n"
SIN_FEEDBACK = "::Simple:: ¿Sí? {T}\n"


def _banco(tmp_path):
    raiz = tmp_path / "banco"
    raiz.mkdir()
    for nombre, texto in {"a.gift": SIN_PROTEGER, "b.gift": SIN_LENGUAJE, "c.gift": SIN_FEEDBACK}.items():
        (raiz / nombre).write_text(texto, encoding="utf-8")
    return raiz


def _auditar(raiz):
    return auditar_archivos(expandir_rutas([raiz], True))


def test_elementos_coinciden_con_el_resumen_y_arreglos_disponibles(tmp_path):
    resultado = _auditar(_banco(tmp_path))
    lista = {h["clave"]: h for h in hallazgos(resultado)}
    assert lista["codigo_gift_sin_proteger"]["nivel"] == "error" and lista["codigo_gift_sin_proteger"]["arreglo"]
    assert lista["sin_feedback"]["nivel"] == "advertencia" and not lista["sin_feedback"]["arreglo"]
    for clave, h in lista.items():
        assert len(elementos(resultado, clave)) == h["cantidad"], clave
    assert [p.name for p in archivos_de(resultado, "codigo_gift_sin_proteger")] == ["a.gift"]
    assert elementos(resultado, "sin_feedback")[0]["titulo"] == "Simple"


def test_arreglar_quita_el_hallazgo_sin_cambiar_la_pregunta(tmp_path):
    raiz = _banco(tmp_path)
    resultado = _auditar(raiz)
    for clave in ("codigo_gift_sin_proteger", "codigo_sin_lenguaje"):
        for archivo in archivos_de(resultado, clave):
            assert arreglar(archivo, clave, simular=True) > 0
            antes = archivo.read_text(encoding="utf-8")
            assert arreglar(archivo, clave) > 0 and archivo.read_text(encoding="utf-8") != antes
    claves = {h["clave"] for h in hallazgos(_auditar(raiz))}
    assert not claves & {"codigo_gift_sin_proteger", "codigo_sin_lenguaje"}
    pregunta = parse_archivo(raiz / "a.gift")["questions"][0]
    assert [c["text"]["text"] for c in pregunta["choices"] if c["is_correct"]] == ["3"]
    assert "＝" in (raiz / "a.gift").read_text(encoding="utf-8")
    assert "```c" in (raiz / "b.gift").read_text(encoding="utf-8")
    with pytest.raises(KeyError):
        arreglar(raiz / "c.gift", "sin_feedback")
    assert set(ARREGLOS) >= {"codigo_gift_sin_proteger", "codigo_sin_lenguaje", "html_obsoleto"}


def _tui(raiz, teclas, elegir=None):
    """Corre la TUI con esas teclas; `elegir` (una clave) selecciona antes ese hallazgo."""
    pytest.importorskip("textual", reason="TUI: requiere el extra opcional 'tui' (uv sync --extra tui)")
    from voight.tui.health import HealthApp

    app = HealthApp(lambda: _auditar(raiz))

    async def correr():
        async with app.run_test(size=(160, 40)) as pilot:
            if elegir:
                app.query_one("#hallazgos").index = [h["clave"] for h in app.lista].index(elegir)
                await pilot.pause()
            for tecla in teclas:
                await pilot.press(tecla)
                await pilot.pause()
        return app.return_value

    return asyncio.run(correr())


def test_tui_arregla_todos_los_archivos_de_un_hallazgo(tmp_path):
    raiz = _banco(tmp_path)
    # El primer hallazgo es el error de código sin proteger: F, confirmar, salir.
    arreglados = _tui(raiz, ["F", "s", "q"])
    assert list(arreglados) == ["codigo_gift_sin_proteger"]
    assert [p.rsplit("/", 1)[-1] for p in arreglados["codigo_gift_sin_proteger"]] == ["a.gift"]
    assert "codigo_gift_sin_proteger" not in {h["clave"] for h in hallazgos(_auditar(raiz))}


def test_tui_cancelar_o_hallazgo_sin_arreglo_no_toca_nada(tmp_path):
    raiz = _banco(tmp_path)
    antes = {p.name: p.read_text(encoding="utf-8") for p in raiz.iterdir()}
    assert _tui(raiz, ["F", "escape", "q"]) == {}  # cancelar la confirmación
    assert _tui(raiz, ["f", "F", "q"], elegir="sin_feedback") == {}  # sin arreglo automático
    assert {p.name: p.read_text(encoding="utf-8") for p in raiz.iterdir()} == antes
