"""Inspección sin extracción y planificación que coincide con el MBZ generado."""

import io
import json
import tarfile
import zipfile

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.mbz_inspector import inspeccionar_mbz
from voight.core.moodle_backup import generar_quiz_mbz

runner = CliRunner()


@pytest.fixture
def banco(tmp_path):
    root = tmp_path / "banco"
    (root / "C").mkdir(parents=True)
    (root / "Java").mkdir()
    (root / "C" / "a.gift").write_text(
        "::A:: ¿Sí? {T}\n\n::B:: ¿No? {F}\n", encoding="utf-8"
    )
    (root / "Java" / "b.xml").write_text(
        """<quiz><question type="multichoice">
      <name><text>XML</text></name><questiontext><text>Elegí</text></questiontext>
      <answer fraction="100"><text>Una</text></answer><answer fraction="0"><text>Otra</text></answer>
    </question></quiz>""",
        encoding="utf-8",
    )
    return root


def test_plan_mixed_and_generated_backup_match(banco, tmp_path):
    plan = runner.invoke(cli, ["moodle", "backup-quiz", str(banco), "--plan", "--json"])
    assert plan.exit_code == 0, plan.output
    data = json.loads(plan.stdout)
    assert data["schema_version"] == "1.0.0" and data["ok"]
    assert (data["preguntas"], data["categorias"], data["slots"]) == (3, 2, 2)
    assert {c["categoria"] for c in data["cupos"]} == {"C", "Java"}
    out = tmp_path / "nuevo.mbz"
    info = generar_quiz_mbz(
        [banco], out, titulo="Mi examen", tiempo_limite=120, intentos=2
    )
    result = runner.invoke(cli, ["moodle", "inspeccionar", str(out), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["preguntas"] == info["preguntas"] == 3
    assert report["versiones"] == 3 and report["tipos"] == {
        "multichoice": 1,
        "truefalse": 2,
    }
    (quiz,) = report["cuestionarios"]
    assert (
        quiz["titulo"] == "Mi examen"
        and quiz["tiempo_limite"] == 120
        and quiz["intentos"] == 2
    )
    assert quiz["slots"] == quiz["aleatorios"] == info["slots"] == 2
    assert {c["categorias"][0]["nombre"] for c in quiz["cupos"]} == {"C", "Java"}


def test_plan_insufficient_never_writes_and_generation_rejects(banco, tmp_path):
    out = tmp_path / "existente.mbz"
    out.write_bytes(b"original")
    result = runner.invoke(
        cli,
        [
            "moodle",
            "backup-quiz",
            str(banco),
            "--plan",
            "-k",
            "2",
            "-o",
            str(out),
            "--json",
        ],
    )
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert not report["ok"]
    assert [(c["categoria"], c["faltantes"]) for c in report["cupos"]] == [
        ("C", 0),
        ("Java", 1),
    ]
    assert out.read_bytes() == b"original"
    result = runner.invoke(
        cli, ["moodle", "backup-quiz", str(banco), "-k", "2", "-o", str(out)]
    )
    assert result.exit_code == 1 and "faltan 1" in result.output
    assert out.read_bytes() == b"original"


def test_plan_reports_unsupported_writer_types(tmp_path):
    bank = tmp_path / "short.gift"
    bank.write_text("::Corta:: Capital {=Viedma}\n", encoding="utf-8")
    result = runner.invoke(
        cli, ["moodle", "backup-quiz", str(bank), "--plan", "--json"]
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["cupos"][0]["tipos_no_soportados"] == ["Short"]
    assert "no implementa" in " ".join(data["errores"])


@pytest.mark.parametrize(
    "args",
    [
        ["-k", "0", "--plan"],
        ["--intentos", "-1", "--plan"],
        ["--calificacion-maxima", "nan", "--plan"],
        [],
    ],
)
def test_bad_configuration(banco, args):
    result = runner.invoke(cli, ["moodle", "backup-quiz", str(banco), *args])
    assert result.exit_code != 0


def test_inspect_zip_and_latest_question_version(banco, tmp_path):
    out = tmp_path / "tar.mbz"
    generar_quiz_mbz([banco], out)
    zip_path = tmp_path / "zip.mbz"
    with tarfile.open(out) as tar, zipfile.ZipFile(zip_path, "w") as zipped:
        for entry in tar:
            if not entry.isfile():
                continue
            data = tar.extractfile(entry).read()
            if entry.name == "questions.xml":
                import xml.etree.ElementTree as ET

                root = ET.fromstring(data)
                version = root.find(".//question_version")
                first = version.find("question_versions")
                other = ET.fromstring(ET.tostring(first))
                other.find("version").text = "2"
                other.find("questions/question/name").text = "Nueva versión"
                version.append(other)
                data = ET.tostring(root)
            zipped.writestr("./" + entry.name, data)
    report = inspeccionar_mbz(zip_path)
    assert report["preguntas"] == 3 and report["versiones"] == 4
    assert report["cuestionarios"][0]["slots"] == 2


def test_inspect_legacy_questions_and_slots(tmp_path):
    archive = tmp_path / "legacy.mbz"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("moodle_backup.xml", "<moodle_backup><information/></moodle_backup>")
        z.writestr(
            "questions.xml",
            """<question_categories><question_category id="7"><name>Tema</name>
          <questions><question id="1"><qtype>truefalse</qtype></question></questions>
          </question_category></question_categories>""",
        )
        z.writestr(
            "activities/quiz_1/quiz.xml",
            """<activity><quiz><name>Viejo</name><question_instances>
          <question_instance><slot>1</slot><questioncategoryid>7</questioncategoryid></question_instance>
          </question_instances></quiz></activity>""",
        )
    report = inspeccionar_mbz(archive)
    assert report["preguntas"] == 1
    assert report["cuestionarios"][0]["tiempo_limite"] is None
    assert report["cuestionarios"][0]["shuffle_respuestas"] is None
    assert report["cuestionarios"][0]["cupos"][0]["categorias"] == [
        {"id": "7", "nombre": "Tema"}
    ]


@pytest.mark.parametrize(
    "name,content",
    [
        ("../questions.xml", "<root/>"),
        ("questions.xml", "<root>"),
        ("questions.xml", '<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>'),
    ],
)
def test_inspect_rejects_invalid_without_extracting(tmp_path, name, content):
    path = tmp_path / "bad.mbz"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("moodle_backup.xml", "<moodle_backup/>")
        z.writestr(name, content)
    with pytest.raises(ValueError):
        inspeccionar_mbz(path)
    assert not (tmp_path.parent / "questions.xml").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bad.mbz"]


def test_tar_link_and_missing_manifest(tmp_path):
    archive = tmp_path / "link.mbz"
    with tarfile.open(archive, "w:gz") as tar:
        link = tarfile.TarInfo("questions.xml")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    with pytest.raises(ValueError, match="regular"):
        inspeccionar_mbz(archive)
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("ignored.txt")
        member.size = 3
        tar.addfile(member, io.BytesIO(b"abc"))
    with pytest.raises(ValueError, match="moodle_backup"):
        inspeccionar_mbz(archive)


def test_distinct_filters_are_not_merged(banco, tmp_path):
    import xml.etree.ElementTree as ET

    source = tmp_path / "source.mbz"
    generar_quiz_mbz([banco], source)
    target = tmp_path / "filters.mbz"
    with tarfile.open(source) as tar, zipfile.ZipFile(target, "w") as zipped:
        for member in tar:
            if not member.isfile():
                continue
            data = tar.extractfile(member).read()
            if member.name.endswith("/quiz.xml"):
                root = ET.fromstring(data)
                slots = root.find("quiz/question_instances")
                first = slots.find("question_instance")
                extra = ET.fromstring(ET.tostring(first))
                field = extra.find("question_set_reference/filtercondition")
                condition = json.loads(field.text)
                condition["filter"]["category"]["filteroptions"][
                    "includesubcategories"
                ] = True
                condition["filter"]["tag"] = {"values": [42]}
                field.text = json.dumps(condition)
                slots.append(extra)
                data = ET.tostring(root)
            zipped.writestr(member.name, data)
    (quiz,) = inspeccionar_mbz(target)["cuestionarios"]
    assert quiz["aleatorios"] == 3 and len(quiz["cupos"]) == 3
    assert any(
        c["filtro"]["filter"].get("tag") == {"values": [42]} for c in quiz["cupos"]
    )
