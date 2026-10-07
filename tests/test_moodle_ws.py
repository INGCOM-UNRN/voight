"""`voight moodle subir` contra un Moodle simulado (servidor HTTP local)."""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from click.testing import CliRunner

from voight.cli import cli

runner = CliRunner()


@pytest.fixture
def moodle_falso():
    pedidos = []
    estado = {"error": None}

    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
            pedidos.append((self.path, self.headers.get("Content-Type", ""), cuerpo))
            if self.path == "/webservice/upload.php":
                respuesta = [{"component": "user", "filearea": "draft", "itemid": 4242, "filename": "preguntas.xml"}]
            elif estado["error"]:
                respuesta = {"exception": "moodle_exception", "errorcode": "nopermissions", "message": estado["error"]}
            else:
                respuesta = {"status": True, "imported": 2}
            datos = json.dumps(respuesta).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

    servidor = HTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_port}", pedidos, estado
    servidor.shutdown()


def test_subir_un_arbol_gift(tmp_path, moodle_falso):
    url, pedidos, _ = moodle_falso
    (tmp_path / "Punteros").mkdir()
    (tmp_path / "Punteros" / "a.gift").write_text("::A:: ¿Sí? {T}\n", encoding="utf-8")
    (tmp_path / "Arreglos").mkdir()
    (tmp_path / "Arreglos" / "b.gift").write_text("::B:: ¿Cuál? {=a ~b ~c}\n", encoding="utf-8")
    res = runner.invoke(cli, ["moodle", "subir", str(tmp_path), "--url", url, "--curso", "7", "--token", "tk", "--json"])
    assert res.exit_code == 0, res.output
    datos = json.loads(res.output)
    assert datos["preguntas"] == 2 and datos["itemid"] == 4242 and datos["respuesta"] == {"status": True, "imported": 2}

    ruta, tipo, cuerpo = pedidos[0]
    assert ruta == "/webservice/upload.php" and tipo.startswith("multipart/form-data")
    texto = cuerpo.decode("utf-8")
    assert 'name="token"\r\n\r\ntk' in texto and 'name="filearea"\r\n\r\ndraft' in texto
    assert "<quiz>" in texto and "$course$/Punteros" in texto and "$course$/Arreglos" in texto

    ruta, _, cuerpo = pedidos[1]
    campos = urllib.parse.parse_qs(cuerpo.decode())
    assert ruta == "/webservice/rest/server.php"
    assert campos["wsfunction"] == ["local_questions_importer_ws_import_xml"]
    assert campos["courseid"] == ["7"] and campos["draftitemid"] == ["4242"] and campos["wstoken"] == ["tk"]
    assert campos["moodlewsrestformat"] == ["json"]


def test_subir_informa_el_error_de_moodle_y_dry_run_no_contacta(tmp_path, moodle_falso, monkeypatch):
    url, pedidos, estado = moodle_falso
    banco = tmp_path / "b.xml"
    banco.write_text('<quiz><question type="truefalse"><name><text>x</text></name><questiontext><text>q</text>'
                     '</questiontext><answer fraction="100"><text>true</text></answer></question></quiz>', encoding="utf-8")
    res = runner.invoke(cli, ["moodle", "subir", str(banco), "--url", url, "--curso", "7", "-n"])
    assert res.exit_code == 0 and "Se subirían 1 preguntas" in res.output and pedidos == []

    estado["error"] = "Sin permiso para importar preguntas"
    res = runner.invoke(cli, ["moodle", "subir", str(banco), "--url", url, "--curso", "7", "--token", "tk"])
    assert res.exit_code == 1 and "Sin permiso para importar preguntas (nopermissions)" in res.output

    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    monkeypatch.setattr("voight.core.moodle_ws.resolver_token", lambda token=None: token)
    res = runner.invoke(cli, ["moodle", "subir", str(banco), "--url", url, "--curso", "7"])
    assert res.exit_code == 1 and "Falta el token" in res.output
