"""`voight ai` sobre GIFT y Moodle XML con un modelo simulado (sin red).

El modelo siempre recibe GIFT compacto; la respuesta vuelve a cada archivo con su
convención y, en XML, sobre el <question> original.
"""

import re
import types

import pytest
import xml.etree.ElementTree as ET

from click.testing import CliRunner

from voight.cli import cli
from voight.core import ai
from voight.core.moodle_xml import parse_xml
from voight.core.parser import parse_gift

runner = CliRunner()

GIFT = """$CATEGORY: $course$/Java

// [tag:java] [id:J-1]
::Igualdad::[markdown]¿Qué imprime?
```java
if (a == b) {
····System.out.println("si");↵
}
```
{
    =`si` #Bien
    ~nada
    ~error
}
"""

XML = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="category"><category><text>$course$/C</text></category></question>
  <question type="multichoice">
    <name><text>Punteros</text></name>
    <questiontext format="markdown"><text><![CDATA[¿Qué imprime?
```c
int x ＝ 5；↵
printf（＂%d＂, x）；
```]]></text></questiontext>
    <generalfeedback format="markdown"><text></text></generalfeedback>
    <defaultgrade>2.0000000</defaultgrade>
    <penalty>0.5</penalty>
    <idnumber>C-7</idnumber>
    <single>true</single>
    <answer fraction="100" format="markdown"><text>5</text><feedback format="markdown"><text>Sí</text></feedback></answer>
    <answer fraction="0" format="markdown"><text>0</text><feedback format="markdown"><text></text></feedback></answer>
    <answer fraction="0" format="markdown"><text>basura</text><feedback format="markdown"><text></text></feedback></answer>
    <tags><tag><text>punteros</text></tag></tags>
  </question>
</quiz>
"""


class Modelo:
    """Cliente simulado: aplica `transformar` a cada pregunta del prompt."""

    def __init__(self, transformar=lambda n, texto: [texto]):
        self.transformar = transformar
        self.models = self
        self.prompts = []

    def generate_content(self, model, contents):
        self.prompts.append(contents)
        bloques = contents.split("\n\n--- PREGUNTA 1 ---\n", 1)[1]
        partes = ai._MARCADOR.split("--- PREGUNTA 1 ---\n" + bloques)
        salida = []
        for numero, texto in zip(partes[1::2], partes[2::2], strict=False):
            for resultado in self.transformar(int(numero), texto.strip()):
                salida.append(f"--- PREGUNTA {numero} ---\n{resultado}")
        return types.SimpleNamespace(text="\n\n".join(salida))

    def generar(self, prompt, *, sistema=None, modelo=None):
        """La interfaz de yutani.ia que usa voight."""
        return self.generate_content(modelo, prompt).text


def _procesar(tmp_path, nombre, contenido, modelo, mode="improve"):
    origen = tmp_path / "banco"
    origen.mkdir(exist_ok=True)
    archivo = origen / nombre
    archivo.write_text(contenido, encoding="utf-8")
    salida = tmp_path / "salida"
    ai.run_global_ai_processing(modelo, "simulado", [archivo], salida, mode)
    return (salida / f"{archivo.stem}_{mode}{archivo.suffix}").read_text(encoding="utf-8")


def test_gift_se_envia_compacto_y_vuelve_con_su_convencion(tmp_path):
    modelo = Modelo(lambda n, t: [t.replace("nada", "no imprime nada")])
    salida = _procesar(tmp_path, "b.gift", GIFT, modelo)
    prompt = modelo.prompts[0]
    # Ni comentarios, ni categoría, ni marcas; el código va en ASCII sin escapar.
    assert "[tag:java]" not in prompt and "$CATEGORY" not in prompt
    assert "·" not in prompt and "↵" not in prompt
    assert 'if (a == b) {\n    System.out.println("si");\n}' in prompt
    # Al volver: metadatos, código protegido y marcas como en el original.
    assert salida.startswith("$CATEGORY: $course$/Java\n\n// [tag:java] [id:J-1]\n::Igualdad::")
    assert 'if （a ⩵ b） ｛↵\n····System.out.println（＂si＂）；↵\n｝' in salida
    pregunta = parse_gift(salida)["questions"][1]
    assert [c["text"]["text"] for c in pregunta["choices"]] == ["`si`", "no imprime nada", "error"]


def test_xml_conserva_metadatos_y_convencion_del_codigo(tmp_path):
    modelo = Modelo(lambda n, t: [t.replace("basura", "un valor indeterminado").replace("::Punteros::", "::Punteros en C::")])
    salida = _procesar(tmp_path, "b.xml", XML, modelo)
    prompt = modelo.prompts[0]
    assert "<question" not in prompt and "penalty" not in prompt
    assert "int x = 5;\nprintf(\"%d\", x);" in prompt
    pregunta = ET.fromstring(salida).findall("question")[1]
    assert pregunta.findtext("name/text") == "Punteros en C"
    assert pregunta.findtext("penalty") == "0.5" and pregunta.findtext("defaultgrade") == "2.0000000"
    assert pregunta.findtext("idnumber") == "C-7" and pregunta.findtext("tags/tag/text") == "punteros"
    assert "int x ＝ 5；↵\nprintf（＂%d＂, x）；↵\n```" in pregunta.findtext("questiontext/text")
    respuestas = pregunta.findall("answer")
    assert [a.findtext("text") for a in respuestas] == ["5", "0", "un valor indeterminado"]
    assert [a.get("fraction") for a in respuestas] == ["100", "0", "0"]
    assert respuestas[0].findtext("feedback/text") == "Sí" and respuestas[0].get("format") == "markdown"
    assert ET.fromstring(salida).find("question/category/text").text == "$course$/C"


def test_multiply_en_xml_crea_variaciones_sin_repetir_idnumber(tmp_path):
    modelo = Modelo(lambda n, t: [t.replace("Punteros", f"Punteros {i}") for i in range(1, 4)])
    salida = _procesar(tmp_path, "b.xml", XML, modelo, mode="multiply")
    preguntas = [q for q in ET.fromstring(salida).findall("question") if q.get("type") != "category"]
    assert [q.findtext("name/text") for q in preguntas] == ["Punteros 1", "Punteros 2", "Punteros 3"]
    assert [q.findtext("idnumber") for q in preguntas] == ["C-7", "", ""]


def test_respuestas_invalidas_o_que_cambian_la_forma_conservan_el_original(tmp_path, capsys):
    casos = {
        "sin GIFT": lambda n, t: ["Perdón, no puedo ayudar con eso."],
        "otro tipo": lambda n, t: ["::P:: ¿Sí? {T}"],
        "parte una opción": lambda n, t: [t.replace("~nada", "~int x = 5")],
    }
    for nombre, transformar in casos.items():
        salida = _procesar(tmp_path, "b.gift", GIFT, Modelo(transformar))
        assert salida == GIFT.strip() + "\n", nombre
    salida_xml = _procesar(tmp_path, "b.xml", XML, Modelo(lambda n, t: ["::X:: Q {T}"]))
    assert parse_xml(salida_xml)["questions"] == parse_xml(XML)["questions"]
    assert "se conserva el original" in capsys.readouterr().out


def test_separar_respuesta_con_cercos_y_sin_marcadores():
    texto = "```gift\n--- PREGUNTA 2 ---\n::B:: b {T}\n--- PREGUNTA 1 ---\n```\n::A:: a {T}\n```\n```"
    assert ai.separar_respuesta(texto, 2) == {2: ["::B:: b {T}"], 1: ["::A:: a {T}"]}
    assert ai.separar_respuesta("::A:: a {T}\n---\n::B:: b {F}", 2) == {1: ["::A:: a {T}"], 2: ["::B:: b {F}"]}


def test_la_salida_conserva_la_estructura_de_directorios(tmp_path):
    for carpeta in ("u1", "u2"):
        (tmp_path / "banco" / carpeta).mkdir(parents=True)
        (tmp_path / "banco" / carpeta / "q01.gift").write_text(f"::{carpeta}:: ¿Sí? {{T}}\n", encoding="utf-8")
    archivos = sorted((tmp_path / "banco").rglob("*.gift"))
    ai.run_global_ai_processing(Modelo(), "simulado", archivos, tmp_path / "salida", "improve")
    assert (tmp_path / "salida" / "u1" / "q01_improve.gift").read_text(encoding="utf-8").startswith("::u1::")
    assert (tmp_path / "salida" / "u2" / "q01_improve.gift").read_text(encoding="utf-8").startswith("::u2::")


def test_cli_dry_run_no_necesita_clave_y_muestra_el_ahorro(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "load_config", lambda: (_ for _ in ()).throw(AssertionError("no debe llamarse")))
    (tmp_path / "b.xml").write_text(XML, encoding="utf-8")
    (tmp_path / "b.gift").write_text(GIFT, encoding="utf-8")
    res = runner.invoke(cli, ["ai", str(tmp_path), "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "2 preguntas" in res.output and "% menos" in res.output
    assert "--- PREGUNTA 2 ---" in res.output
    assert not list(tmp_path.glob("output_*"))


def test_titulos_gift_se_desescapan():
    assert parse_gift("::C\\: punteros:: ¿Sí? {T}")["questions"][0]["title"] == "C: punteros"


def test_xml_conserva_los_comentarios(tmp_path):
    con_comentario = XML.replace("<quiz>", "<quiz>\n  <!-- question: 1854266 -->", 1)
    salida = _procesar(tmp_path, "b.xml", con_comentario, Modelo())
    assert "<!-- question: 1854266 -->" in salida


def _con_feedback(n, texto):
    """Modelo que recibe la vista de feedback (enunciado, opciones numeradas y FALTA) y devuelve sólo
    líneas 'n# …'; además intenta reescribir un feedback que ya existe (1# …), que debe ignorarse."""
    opciones = {}
    for linea in texto.splitlines():
        m = re.match(r"^(\d+)\. [=~](?:%-?[\d.]+%)?(.*)$", linea)
        if m:
            opciones[m.group(1)] = m.group(2).strip()
    faltan = [x.strip() for x in texto.rsplit("FALTA:", 1)[1].split(",")]
    salida = [f"{i}# Explicación de {opciones[i]}" for i in faltan if i in opciones]
    salida += ["1# Muy bien"] + (["G# Repasá el concepto."] if "G" in faltan else [])
    return ["\n".join(salida)]


def test_feedback_completa_solo_lo_que_falta_en_gift(tmp_path):
    modelo = Modelo(_con_feedback)
    salida = _procesar(tmp_path, "b.gift", GIFT, modelo, mode="feedback")
    q = parse_gift(salida)["questions"][1]
    assert "¿Qué imprime?" in q["stem"]["text"]
    retros = [c["feedback"]["text"] for c in q["choices"]]
    assert retros == ["Bien", "Explicación de nada", "Explicación de error"]
    assert q["globalFeedback"]["text"] == "Repasá el concepto."
    assert salida.startswith("$CATEGORY: $course$/Java\n\n// [tag:java] [id:J-1]\n")
    assert "if （a ⩵ b） ｛↵" in salida


def test_feedback_en_xml_solo_toca_los_nodos_de_retroalimentacion(tmp_path):
    salida = _procesar(tmp_path, "b.xml", XML, Modelo(_con_feedback), mode="feedback")
    pregunta = ET.fromstring(salida).findall("question")[1]
    assert [a.findtext("feedback/text") for a in pregunta.findall("answer")] == [
        "Sí", "Explicación de 0", "Explicación de basura"]
    assert pregunta.findtext("generalfeedback/text") == "Repasá el concepto."
    assert pregunta.findtext("questiontext/text") == ET.fromstring(XML).findall("question")[1].findtext("questiontext/text")
    assert pregunta.findtext("penalty") == "0.5"


def test_feedback_saltea_las_preguntas_completas(tmp_path, capsys):
    archivo = tmp_path / "c.gift"
    archivo.write_text("::C:: ¿Sí? {=a #bien ~b #mal ####general}\n", encoding="utf-8")
    modelo = Modelo(_con_feedback)
    ai.run_global_ai_processing(modelo, "simulado", [archivo], tmp_path / "salida", "feedback")
    assert modelo.prompts == [] and "No se encontraron preguntas" in capsys.readouterr().out


def test_cache_evita_volver_a_consultar_al_modelo(tmp_path):
    modelo = Modelo(lambda n, t: [t.replace("nada", "no imprime nada")])
    primera = _procesar(tmp_path, "b.gift", GIFT, modelo)
    assert len(modelo.prompts) == 1
    segunda = _procesar(tmp_path, "b.gift", GIFT, modelo)
    assert len(modelo.prompts) == 1 and segunda == primera
    # Otro modo u otra instrucción no comparten la respuesta.
    _procesar(tmp_path, "b.gift", GIFT, modelo, mode="transform")
    assert len(modelo.prompts) == 2
    archivo = tmp_path / "banco" / "b.gift"
    ai.run_global_ai_processing(modelo, "simulado", [archivo], tmp_path / "salida", "improve", usar_cache=False)
    assert len(modelo.prompts) == 3


def test_estimacion_de_tokens_y_costo(tmp_path):
    from click.testing import CliRunner

    from voight.cli import cli

    (tmp_path / "b.gift").write_text(GIFT, encoding="utf-8")
    res = CliRunner().invoke(cli, ["ai", str(tmp_path), "--dry-run", "--precio-entrada", "1", "--precio-salida", "5"])
    assert res.exit_code == 0, res.output
    assert "tokens de entrada" in res.output and "costo estimado ≈ USD 0.00" in res.output
    pocos = ai.estimar_tokens(ai.unidades_de(ai.leer_archivos([tmp_path / "b.gift"])), "improve", None, 5)
    muchos = ai.estimar_tokens(ai.unidades_de(ai.leer_archivos([tmp_path / "b.gift"])), "multiply", None, 5)
    assert pocos["entrada"] > pocos["salida"] > 0 and abs(muchos["salida"] - 3 * pocos["salida"]) <= 3


def _con_distractores(n, texto):
    """Devuelve sólo distractores (uno repetido de los existentes, que se ignora)."""
    return ["~Un número aleatorio #confunde con basura\n~error\n~Una excepción en tiempo de ejecución"]


def test_distractors_agrega_solo_opciones_incorrectas_nuevas(tmp_path):
    salida = _procesar(tmp_path, "b.gift", GIFT, Modelo(_con_distractores), mode="distractors")
    q = parse_gift(salida)["questions"][1]
    textos = [c["text"]["text"] for c in q["choices"]]
    assert textos == ["`si`", "nada", "error", "Un número aleatorio"]  # hasta 4 opciones, sin repetir "error"
    assert q["choices"][3]["feedback"]["text"] == "confunde con basura" and not q["choices"][3]["is_correct"]


def test_distractors_en_xml_agrega_respuestas_con_fraccion_cero(tmp_path):
    salida = _procesar(tmp_path, "b.xml", XML, Modelo(_con_distractores), mode="distractors")
    pregunta = ET.fromstring(salida).findall("question")[1]
    respuestas = pregunta.findall("answer")
    assert [a.findtext("text") for a in respuestas] == ["5", "0", "basura", "Un número aleatorio"]
    assert respuestas[3].get("fraction") == "0" and respuestas[3].get("format") == "markdown"
    assert pregunta.findtext("penalty") == "0.5"


def test_distractors_nunca_cambia_las_opciones_originales(tmp_path):
    """Con la vista parcial el modelo sólo puede agregar: si devuelve la vista entera con una opción
    reescrita, el enunciado y las originales quedan como estaban."""
    def cambia(n, texto):
        return [texto.replace("~nada", "~nada de nada").replace("ENUNCIADO: ", "ENUNCIADO: Nuevo ")]

    salida = _procesar(tmp_path, "b.gift", GIFT, Modelo(cambia), mode="distractors")
    q = parse_gift(salida)["questions"][1]
    textos = [c["text"]["text"] for c in q["choices"]]
    assert textos[:3] == ["`si`", "nada", "error"] and "Nuevo" not in q["stem"]["text"]


def test_necesita_distractores():
    from voight.core.parser import GiftParser

    def modelo(gift):
        return GiftParser()._manual_parse(gift)[0]

    assert not ai.necesita_distractores(modelo("::A:: q {=a ~b ~c ~d}"), 4)
    assert ai.necesita_distractores(modelo("::A:: q {=a ~b ~c}"), 4)
    assert ai.necesita_distractores(modelo("::A:: q {=una respuesta muy larga y detallada ~b ~c ~d}"), 4)


class _SDKFalso:
    """Imita client.beta.messages.create del SDK de Anthropic."""

    def __init__(self, stop_reason="end_turn", bloques=None):
        self.llamadas = []
        self.stop_reason = stop_reason
        self.bloques = bloques if bloques is not None else [
            types.SimpleNamespace(type="thinking", thinking=""),
            types.SimpleNamespace(type="text", text="--- PREGUNTA 1 ---\n"),
            types.SimpleNamespace(type="text", text="::A:: ¿Sí? {T}"),
        ]
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self._crear))

    def _crear(self, **kwargs):
        self.llamadas.append(kwargs)
        return types.SimpleNamespace(stop_reason=self.stop_reason, content=self.bloques,
                                     stop_details=types.SimpleNamespace(category="cyber"))


def test_cliente_claude_ante_una_negativa_conserva_las_preguntas(tmp_path, capsys):
    """El cliente de Claude es el de yutani.ia; una negativa deja el lote como estaba."""
    from yutani import ia as yia

    cliente = yia.ClienteClaude(yia.configuracion(proveedor="claude"), sdk=_SDKFalso(stop_reason="refusal", bloques=[]))
    salida = _procesar(tmp_path, "b.gift", GIFT, cliente)
    assert salida == GIFT.strip() + "\n"
    assert "declinó" in capsys.readouterr().out


@pytest.fixture
def sin_config_ia(monkeypatch, tmp_path):
    for var in ("P1_IA_PROVEEDOR", "P1_IA_MODELO", "P1_IA_URL", "VOIGHT_PROVEEDOR", "GEMINI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("P1_IA_CONFIG", str(tmp_path / "ia.toml"))
    monkeypatch.setattr(ai, "cargar_entorno", lambda: None)  # sin el ~/.voight/.env de la máquina


def test_modelo_por_defecto_segun_proveedor(sin_config_ia):
    assert ai.modelo_por_defecto("claude") == "claude-opus-5"
    assert ai.modelo_por_defecto("gemini").startswith("gemini")
    assert ai.modelo_por_defecto("opencode") == "opencode-go/qwen3.8-max"


def test_configuracion_ia_respeta_lo_de_antes_y_lo_comun(sin_config_ia, monkeypatch):
    """N-ECO-26: sin nada, Gemini; VOIGHT_PROVEEDOR y GEMINI_MODEL siguen valiendo; P1_IA_* también."""
    assert ai.configuracion_ia().proveedor == "google"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    assert ai.configuracion_ia().modelo == "gemini-2.5-pro"
    monkeypatch.setenv("P1_IA_PROVEEDOR", "ollama")
    monkeypatch.setenv("P1_IA_MODELO", "qwen2.5-coder:7b")
    c = ai.configuracion_ia()
    assert (c.proveedor, c.modelo) == ("local", "qwen2.5-coder:7b")
    monkeypatch.setenv("VOIGHT_PROVEEDOR", "claude")
    assert ai.configuracion_ia().proveedor == "claude"
    assert ai.configuracion_ia("opencode", "x/y").modelo == "x/y"


def test_cli_ai_con_servidor_local(sin_config_ia, monkeypatch, tmp_path):
    """--proveedor local usa el cliente de yutani.ia con el modelo pedido."""
    from yutani import ia as yia

    pedidos = []
    modelo = Modelo()

    def cliente(config, directorio=None):
        pedidos.append(config)
        return modelo

    monkeypatch.setattr(yia, "cliente", cliente)
    (tmp_path / "b.gift").write_text(GIFT, encoding="utf-8")
    res = runner.invoke(cli, ["ai", str(tmp_path / "b.gift"), "--proveedor", "local", "--model", "qwen2.5-coder:7b",
                              "--output", str(tmp_path / "out"), "--sin-cache"])
    assert res.exit_code == 0, res.output
    assert (pedidos[-1].proveedor, pedidos[-1].modelo) == ("local", "qwen2.5-coder:7b")
    assert modelo.prompts and list((tmp_path / "out").glob("*.gift"))


def test_cli_ai_proveedor_desconocido(sin_config_ia, tmp_path):
    (tmp_path / "b.gift").write_text(GIFT, encoding="utf-8")
    res = runner.invoke(cli, ["ai", str(tmp_path / "b.gift"), "--proveedor", "watson"])
    assert res.exit_code != 0


# ── Vistas parciales: sólo se envía y se recibe lo que cambia ─────────────────────

def _procesar_parte(tmp_path, nombre, contenido, modelo, parte):
    origen = tmp_path / "banco"
    origen.mkdir(exist_ok=True)
    archivo = origen / nombre
    archivo.write_text(contenido, encoding="utf-8")
    ai.run_global_ai_processing(modelo, "simulado", [archivo], tmp_path / "salida", "improve", parte=parte)
    return (tmp_path / "salida" / f"{archivo.stem}_improve{archivo.suffix}").read_text(encoding="utf-8")


def test_parte_enunciado_envia_y_recibe_solo_el_enunciado_gift(tmp_path):
    modelo = Modelo(lambda n, t: [t.replace("¿Qué imprime?", "¿Qué muestra en pantalla este fragmento?")])
    salida = _procesar_parte(tmp_path, "b.gift", GIFT, modelo, "enunciado")
    enviado = modelo.prompts[0].split("--- PREGUNTA 1 ---\n", 1)[1]
    assert "{" not in enviado.replace("if (a == b) {", "") and "nada" not in enviado and "Bien" not in enviado
    assert "if (a == b) {" in enviado  # el código va en ASCII, sin marcas · ni ↵
    q = parse_gift(salida)["questions"][1]
    assert "¿Qué muestra en pantalla este fragmento?" in q["stem"]["text"]
    assert [c["text"]["text"] for c in q["choices"]] == ["`si`", "nada", "error"]
    assert q["choices"][0]["feedback"]["text"] == "Bien"
    assert "if （a ⩵ b） ｛↵" in salida  # el código recupera la convención del original
    assert salida.startswith("$CATEGORY: $course$/Java\n\n// [tag:java] [id:J-1]\n")


def test_parte_enunciado_en_xml_solo_toca_questiontext(tmp_path):
    modelo = Modelo(lambda n, t: [t.replace("¿Qué imprime?", "¿Qué se imprime?")])
    salida = _procesar_parte(tmp_path, "b.xml", XML, modelo, "enunciado")
    assert "<answer" not in modelo.prompts[0] and "basura" not in modelo.prompts[0]
    pregunta = ET.fromstring(salida).findall("question")[1]
    assert pregunta.findtext("questiontext/text").startswith("¿Qué se imprime?")
    assert [a.findtext("text") for a in pregunta.findall("answer")] == ["5", "0", "basura"]
    assert pregunta.findtext("penalty") == "0.5" and pregunta.findtext("idnumber") == "C-7"


def test_parte_respuestas_envia_opciones_sin_retroalimentacion(tmp_path):
    def mejora(n, texto):
        opciones = [linea for linea in texto.splitlines() if linea.startswith(("=", "~"))]
        return ["\n".join(o.replace("nada", "No imprime nada").replace("error", "Error de compilación")
                          for o in opciones)]

    modelo = Modelo(mejora)
    salida = _procesar_parte(tmp_path, "b.gift", GIFT, modelo, "respuestas")
    assert "Bien" not in modelo.prompts[0]  # la retroalimentación no viaja
    q = parse_gift(salida)["questions"][1]
    assert [c["text"]["text"] for c in q["choices"]] == ["`si`", "No imprime nada", "Error de compilación"]
    assert q["choices"][0]["feedback"]["text"] == "Bien" and q["choices"][0]["is_correct"]


def test_parte_respuestas_rechaza_si_cambia_la_correcta(tmp_path, capsys):
    modelo = Modelo(lambda n, t: ["~`si`\n=nada\n~error"])
    salida = _procesar_parte(tmp_path, "b.gift", GIFT, modelo, "respuestas")
    assert salida == GIFT.strip() + "\n" and "forma pedida" in capsys.readouterr().out


def test_las_vistas_parciales_envian_menos(tmp_path):
    (tmp_path / "b.xml").write_text(XML, encoding="utf-8")
    unidades = ai.unidades_de(ai.leer_archivos([tmp_path / "b.xml"]))
    completo = ai.estimar_tokens(unidades, "improve", None, 5)
    enunciado = ai.estimar_tokens(unidades, "improve", None, 5, parte="enunciado")
    assert enunciado["entrada"] < completo["entrada"] and enunciado["salida"] < completo["salida"]
    # feedback devuelve sólo lo que falta; antes volvía la pregunta entera además de eso.
    feedback = ai.estimar_tokens(unidades, "feedback", None, 5)
    antes = sum(len(u.texto) for u in unidades) / ai.CARACTERES_POR_TOKEN + feedback["salida"]
    assert feedback["salida"] < antes


def test_parte_solo_con_improve(tmp_path):
    (tmp_path / "b.gift").write_text(GIFT, encoding="utf-8")
    res = runner.invoke(cli, ["ai", str(tmp_path), "--mode", "feedback", "--parte", "enunciado", "--dry-run"])
    assert res.exit_code != 0 and "--parte" in res.output


def test_dry_run_con_parte_muestra_la_vista(tmp_path):
    (tmp_path / "b.gift").write_text(GIFT, encoding="utf-8")
    res = runner.invoke(cli, ["ai", str(tmp_path), "--parte", "enunciado", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert "sólo el enunciado" in res.output and "~nada" not in res.output


def test_parte_enunciado_rechaza_marcadores_deformados(tmp_path, capsys):
    """Un modelo chico que devuelve varias «preguntas» con marcadores mal escritos no pisa el enunciado."""
    modelo = Modelo(lambda n, t: ["--- PREGUNQA 1 ---\nOtra cosa\n\n--- PREGUNTA 2 |\nY otra"])
    salida = _procesar_parte(tmp_path, "b.gift", GIFT, modelo, "enunciado")
    assert salida == GIFT.strip() + "\n" and "forma pedida" in capsys.readouterr().out
