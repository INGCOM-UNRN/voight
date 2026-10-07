"""Clasificación con Jev (Bloom y dificultad) con un cliente simulado, sin red."""

import io
import json
import urllib.error
import xml.etree.ElementTree as ET

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core import clasificacion as cl
from voight.core.moodle_xml import parse_moodle_xml
from voight.core.parser import GiftParser, parse_gift

runner = CliRunner()

GIFT = """// [tag:java] [id:J-1]
::Igualdad::[markdown]¿Qué imprime?
```java
if (a ＝＝ b) ｛
····System.out.println（＂si＂）；↵
｝
```
{
    =`si` #Bien, compara referencias
    ~nada
    ~error
}

::VF:: ¿Java compila a bytecode? {T}
"""

XML = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <!-- question: 1854266 -->
  <question type="multichoice">
    <name><text>Punteros</text></name>
    <questiontext format="markdown"><text><![CDATA[¿Qué imprime `*p`?]]></text></questiontext>
    <answer fraction="100"><text>5</text><feedback><text>Porque p apunta a x</text></feedback></answer>
    <answer fraction="0"><text>0</text></answer>
    <tags><tag><text>punteros</text></tag><tag><text>bloom:recordar</text></tag></tags>
  </question>
</quiz>
"""


def respuesta(bloom="aplicar", enunciado=2.4, respuestas=1.5, modelo="jev-1.13.0"):
    datos = {
        "model": modelo,
        "answers": {
            "bloom": {"type": "choice", "choice": bloom, "confidence": 0.81},
            "enunciado": {"type": "score", "score": enunciado, "confidence": 0.7},
        },
        "usage": {"input_tokens": 100, "output_tokens": 10},
    }
    if respuestas is not None:
        datos["answers"]["respuestas"] = {"type": "score", "score": respuestas, "confidence": 0.6}
    return datos


class Cliente:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.pedidos = []

    def consultar(self, state, questions):
        self.pedidos.append((state, questions))
        return respuesta(respuestas=self.kwargs.get("respuestas", 1.5) if "respuestas" in questions else None,
                         bloom=self.kwargs.get("bloom", "aplicar"))


def test_estado_sin_feedback_con_codigo_en_ascii_y_correcta_marcada():
    q = GiftParser()._manual_parse(GIFT)[0]
    datos = cl.estado(q, "P2 (Java)")
    assert datos["contexto"] == "P2 (Java)" and datos["tipo"] == "opción múltiple"
    assert 'if (a == b) {\n    System.out.println("si");\n}' in datos["enunciado"]
    assert datos["opciones"][0] == {"texto": "`si`", "correcta": True}
    assert "compara referencias" not in json.dumps(datos, ensure_ascii=False)


def test_dificultad_de_respuestas_solo_con_opciones():
    mc, vf = GiftParser()._manual_parse(GIFT)
    assert set(cl.preguntas_jev(mc)) == {"bloom", "enunciado", "respuestas"}
    assert set(cl.preguntas_jev(vf)) == {"bloom", "enunciado"}
    assert cl.estado(vf)["respuesta_correcta"] == "verdadero"
    assert len(cl.preguntas_jev(mc)["enunciado"]["criteria"]) == 5


def test_clasificacion_y_comentario():
    c = cl.Clasificacion.desde_respuesta(respuesta())
    assert (c.bloom, c.enunciado, c.respuestas) == ("aplicar", 3.4, 2.5)
    assert c.comentario() == ("[bloom:B3-aplicar] [dificultad-enunciado:3.4/5] [dificultad-respuestas:2.5/5] "
                              "[clasificacion:jev-1.13.0 confianza=0.81,0.7,0.6]")
    assert c.tags() == ["bloom:aplicar", "dificultad-enunciado:3", "dificultad-respuestas:2"]


def test_gift_agrega_el_comentario_y_no_repite_al_volver_a_correr(tmp_path):
    banco = tmp_path / "b.gift"
    banco.write_text(GIFT, encoding="utf-8")
    cliente = Cliente()
    datos = cl.run_clasificacion([banco], None, in_place=True, cliente=cliente, tags=True)
    assert datos["clasificadas"] == 2 and datos["uso"] == {"input_tokens": 200, "output_tokens": 20}
    texto = banco.read_text(encoding="utf-8")
    assert texto.startswith("// [tag:java] [id:J-1]\n// [bloom:B3-aplicar] [dificultad-enunciado:3.4/5]")
    assert "::VF::" in texto and texto.count("[clasificacion:") == 2
    # El resto queda igual, y los tags llegan al modelo (Moodle los importa).
    preguntas = parse_gift(texto)["questions"]
    assert preguntas[0]["tags"] == ["java", "bloom:aplicar", "dificultad-enunciado:3", "dificultad-respuestas:2"]
    assert preguntas[0]["choices"] == parse_gift(GIFT)["questions"][0]["choices"]

    otro = Cliente()
    assert cl.run_clasificacion([banco], None, in_place=True, cliente=otro) is None
    assert otro.pedidos == []

    cl.run_clasificacion([banco], None, in_place=True, cliente=Cliente(bloom="analizar"), reclasificar=True)
    texto = banco.read_text(encoding="utf-8")
    assert texto.count("[clasificacion:") == 2 and "[bloom:B4-analizar]" in texto and "B3-aplicar" not in texto


def test_xml_comentario_antes_de_la_pregunta_y_tags_reemplazados(tmp_path):
    banco = tmp_path / "b.xml"
    banco.write_text(XML, encoding="utf-8")
    for _ in range(2):
        cl.run_clasificacion([banco], None, in_place=True, cliente=Cliente(), tags=True, reclasificar=True)
    texto = banco.read_text(encoding="utf-8")
    assert "<!-- question: 1854266 -->" in texto
    assert texto.count("[clasificacion:") == 1
    assert texto.index("[bloom:B3-aplicar]") < texto.index("<question")
    q = parse_moodle_xml(texto)[0]
    assert q.tags == ["punteros", "bloom:aplicar", "dificultad-enunciado:3", "dificultad-respuestas:2"]
    assert ET.fromstring(texto).find("question/answer/feedback/text").text == "Porque p apunta a x"


def test_salida_en_directorio_y_errores_no_detienen_el_resto(tmp_path, capsys):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "b.gift").write_text(GIFT, encoding="utf-8")

    class Falla(Cliente):
        def consultar(self, state, questions):
            if state["tipo"] == "verdadero/falso":
                raise RuntimeError("TypeSafe respondió 422")
            return super().consultar(state, questions)

    datos = cl.run_clasificacion([tmp_path / "in" / "b.gift"], tmp_path / "out", cliente=Falla())
    assert datos["errores"] == 1 and datos["clasificadas"] == 1
    salida = (tmp_path / "out" / "b_classify.gift").read_text(encoding="utf-8")
    assert salida.count("[clasificacion:") == 1
    assert (tmp_path / "in" / "b.gift").read_text(encoding="utf-8") == GIFT
    assert "422" in capsys.readouterr().out


def test_cliente_reintenta_ante_429_y_no_ante_401(monkeypatch):
    llamadas = []

    def urlopen(pedido, timeout):
        llamadas.append(json.loads(pedido.data))
        if len(llamadas) == 1:
            raise urllib.error.HTTPError(pedido.full_url, 429, "lento", {}, io.BytesIO(b"rate"))
        return io.BytesIO(json.dumps(respuesta()).encode())

    monkeypatch.setattr(cl.urllib.request, "urlopen", urlopen)
    cliente = cl.ClienteJev(clave="k", espera=0)
    assert cliente.consultar({"a": 1}, {"q": {}})["answers"]["bloom"]["choice"] == "aplicar"
    assert len(llamadas) == 2 and llamadas[0]["model"] == "jev-latest"

    def no_autorizado(pedido, timeout):
        llamadas.append(1)
        raise urllib.error.HTTPError(pedido.full_url, 401, "no", {}, io.BytesIO(b"bad key"))

    llamadas.clear()
    monkeypatch.setattr(cl.urllib.request, "urlopen", no_autorizado)
    with pytest.raises(RuntimeError, match="401"):
        cliente.consultar({}, {})
    assert len(llamadas) == 1


def test_resolver_clave_desde_env(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(cl.Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cl.resolver_clave() is None
    (tmp_path / ".env").write_text('OTRA=1\nTYPESAFE_API_KEY="apikey_x"\n', encoding="utf-8")
    assert cl.resolver_clave() == "apikey_x"
    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_env")
    assert cl.resolver_clave() == "apikey_env"


def test_cli_classify_dry_run_sin_clave(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "resolver_clave", lambda: None)
    (tmp_path / "b.xml").write_text(XML, encoding="utf-8")
    res = runner.invoke(cli, ["ai", str(tmp_path), "--mode", "classify", "--dry-run", "--contexto", "P1 (C)"])
    assert res.exit_code == 0, res.output
    assert '"contexto": "P1 (C)"' in res.output and '"respuestas"' in res.output
    res = runner.invoke(cli, ["ai", str(tmp_path), "--mode", "classify"])
    assert res.exit_code == 1 and "TYPESAFE_API_KEY" in res.output


def test_cliente_jev_usa_la_cache(monkeypatch):
    from voight.core.cache import Cache

    llamadas = []

    def urlopen(pedido, timeout):
        llamadas.append(1)
        return io.BytesIO(json.dumps(respuesta()).encode())

    monkeypatch.setattr(cl.urllib.request, "urlopen", urlopen)
    cliente = cl.ClienteJev(clave="k", espera=0, cache=Cache("jev"))
    assert cliente.consultar({"a": 1}, {"q": {}}) == cliente.consultar({"a": 1}, {"q": {}})
    assert len(llamadas) == 1
    cliente.consultar({"a": 2}, {"q": {}})
    assert len(llamadas) == 2


def test_calibracion_contra_una_referencia(tmp_path):
    banco = tmp_path / "b.gift"
    banco.write_text(GIFT, encoding="utf-8")
    referencia = tmp_path / "ref.csv"
    cl.agregar_referencia(referencia, banco, "Igualdad", "aplicar", 3, 2)
    cl.agregar_referencia(referencia, banco, "VF", "B1-recordar")
    cl.agregar_referencia(referencia, banco, "VF", "comprender")  # reemplaza la anterior
    filas = cl.leer_referencias(referencia)
    assert [(f["titulo"], f["bloom"]) for f in filas] == [("Igualdad", "aplicar"), ("VF", "comprender")]

    datos = cl.calibrar(filas, Cliente())  # Jev simulado: siempre "aplicar", enunciado 3.4, respuestas 2.5
    assert datos["preguntas"] == 2 and datos["exacta"] == 0.5 and datos["adyacente"] == 1.0
    assert datos["matriz"]["comprender"]["aplicar"] == 1
    assert datos["error_dificultad_enunciado"] == 0.4 and datos["error_dificultad_respuestas"] == 0.5
    texto = cl.describir_calibracion(datos)
    assert "Bloom exacto: 50%" in texto and "a ±1 nivel: 100%" in texto


def test_kappa():
    c = cl.Clasificacion
    perfecto = [({"bloom": b}, c(b, 1, 1, 1)) for b in ("recordar", "aplicar", "analizar")]
    assert cl.medir_concordancia(perfecto)["kappa"] == 1.0


# --- revisión de las clasificaciones con poca confianza ----------------------

_REVISAR = (
    "// [bloom:B2-comprender] [dificultad-enunciado:2/5] [clasificacion:systemone-v1 confianza=0.41,0.9]\n"
    "::A:: ¿Qué guarda un puntero? {=Una dirección ~Un valor ~Nada}\n\n"
    "// [bloom:B1-recordar] [dificultad-enunciado:1/5] [clasificacion:systemone-v1 confianza=0.95,0.9]\n"
    "::B:: ¿C es compilado? {T}\n\n"
    "// [bloom:B3-aplicar] [dificultad-enunciado:3/5] [clasificacion:systemone-v1 confianza=0.2,0.3]\n"
    "::C:: ¿Qué imprime? {=1 ~2 ~3}\n"
)


def _leer_revision(tmp_path):
    import contextlib
    import io

    from voight.core.lector import leer_archivos, unidades_de

    ruta = tmp_path / "banco.gift"
    if not ruta.exists():
        ruta.write_text(_REVISAR, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        archivos = leer_archivos([ruta])
    return ruta, archivos, [u for u in unidades_de(archivos) if u.pregunta]


def test_para_revisar_corregir_y_guardar(tmp_path):
    from voight.core.clasificacion import corregida, guardar_correcciones, leer_referencias, para_revisar

    ruta, archivos, unidades = _leer_revision(tmp_path)
    revisar = para_revisar(unidades)
    assert [u.pregunta.title for u in revisar] == ["C", "A"]  # de la menos a la más confiable
    assert [u.pregunta.title for u in para_revisar(unidades, todas=True)] == ["C", "A", "B"]

    c = corregida(revisar[0], "analizar", 4)
    assert (c.bloom, c.enunciado, c.modelo, c.bloom_confianza) == ("analizar", 4.0, "manual", 1.0)
    csv = tmp_path / "referencias.csv"
    resultado = guardar_correcciones(archivos, {id(revisar[0]): c}, referencias=csv)
    assert resultado == {"archivos": [ruta], "referencias": 1}
    texto = ruta.read_text(encoding="utf-8")
    assert "// [bloom:B4-analizar] [dificultad-enunciado:4/5] [clasificacion:manual confianza=1,1]\n::C::" in texto
    assert texto.count("[clasificacion:") == 3 and "confianza=0.2" not in texto
    assert [(r["titulo"], r["bloom"], r["dificultad_enunciado"]) for r in leer_referencias(csv)] == [("C", "analizar", "4.0")]

    # Releída, la corregida a mano ya no se pide revisar ni se reclasifica.
    _, archivos, unidades = _leer_revision(tmp_path)
    assert [u.pregunta.title for u in para_revisar(unidades)] == ["A"]
    from voight.core.clasificacion import _pendientes

    assert [u.pregunta.title for u in _pendientes(archivos, reclasificar=True)] == ["A", "B"]


def test_tui_de_revision(tmp_path):
    import asyncio

    import pytest

    pytest.importorskip("textual", reason="TUI: requiere el extra opcional 'tui' (uv sync --extra tui)")
    from voight.core.clasificacion import leer_referencias, para_revisar
    from voight.tui.clasificacion import ClasificacionApp

    ruta, archivos, unidades = _leer_revision(tmp_path)
    csv = tmp_path / "ref.csv"
    app = ClasificacionApp(archivos, para_revisar(unidades), referencias=csv)

    async def correr(teclas):
        async with app.run_test(size=(140, 40)) as pilot:
            for tecla in teclas:
                await pilot.press(tecla)
                await pilot.pause()
        return app.return_value

    # C → B5 (evaluar) y pasa sola a A; A: aceptar la del modelo; volver a C y subir la dificultad.
    resultado = asyncio.run(correr(["5", "a", "up", "plus", "s"]))
    assert resultado["correcciones"] == 2 and resultado["referencias"] == 2
    texto = ruta.read_text(encoding="utf-8")
    assert "[bloom:B5-evaluar] [dificultad-enunciado:4/5] [clasificacion:manual" in texto
    assert "[bloom:B2-comprender] [dificultad-enunciado:2/5] [clasificacion:manual" in texto
    assert {r["titulo"]: r["bloom"] for r in leer_referencias(csv)} == {"C": "evaluar", "A": "comprender"}


def test_tui_de_revision_salir_no_guarda(tmp_path):
    import asyncio

    import pytest

    pytest.importorskip("textual", reason="TUI: requiere el extra opcional 'tui' (uv sync --extra tui)")
    from voight.core.clasificacion import para_revisar
    from voight.tui.clasificacion import ClasificacionApp

    ruta, archivos, unidades = _leer_revision(tmp_path)
    app = ClasificacionApp(archivos, para_revisar(unidades))

    async def correr():
        async with app.run_test(size=(140, 40)) as pilot:
            for tecla in ["3", "u", "4", "q"]:
                await pilot.press(tecla)
                await pilot.pause()
        return app.return_value

    assert asyncio.run(correr()) is None and ruta.read_text(encoding="utf-8") == _REVISAR
