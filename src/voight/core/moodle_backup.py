"""Generación de copias de seguridad de cuestionarios (MBZ / Moodle 2 backup).

Construye un archivo .mbz (tar.gz) conteniendo un cuestionario (quiz) con preguntas
aleatorias distribuidas por categoría, utilizando los bancos GIFT/XML unificados y
organizados según la estructura de directorios del repositorio.
"""
from __future__ import annotations

import json
import os
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from voight.core.converter import gift_to_xml
from voight.core.moodle_xml import parse_moodle_xml
from voight.core.unifier import unificar


def _cdata_xml(text: str) -> str:
    """Escapa texto simple para XML."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def recolectar_banco_unificado(
    rutas: Sequence[Union[str, Path]], recursivo: bool = True
) -> List[dict]:
    """Unifica las preguntas de las rutas dadas y las devuelve agrupadas por categoría."""
    with tempfile.TemporaryDirectory(prefix="voight-backup-") as tmp:
        # Probamos primero unificar a XML si hay XMLs o si unificar genera el archivo
        archivos = []
        for r in rutas:
            p = Path(r)
            if p.is_file() and p.suffix.lower() in (".gift", ".xml"):
                archivos.append(p)
            elif p.is_dir():
                pattern = "**/*" if recursivo else "*"
                archivos.extend([f for f in p.glob(pattern) if f.is_file() and f.suffix.lower() in (".gift", ".xml")])

        if not archivos:
            return []

        # Usamos unificar_gift o unificar_xml
        # Si unificamos a gift, luego lo convertimos a xml
        tiene_solo_xml = all(a.suffix.lower() == ".xml" for a in archivos)
        if tiene_solo_xml:
            salida = Path(tmp) / "unificado.xml"
            unificar(rutas, salida, formato="xml", recursivo=recursivo)
            xml_content = salida.read_text(encoding="utf-8")
        else:
            salida = Path(tmp) / "unificado.gift"
            unificar(rutas, salida, formato="gift", recursivo=recursivo)
            xml_content = gift_to_xml(salida.read_text(encoding="utf-8"))

        preguntas_modelo = parse_moodle_xml(xml_content)

    categorias: Dict[str, List[dict]] = {}
    categoria_actual = "General"

    for q in preguntas_modelo:
        if q.type == "Category":
            cat_name = (q.title or "").replace("$course$/", "").replace("$course$", "").strip("/")
            categoria_actual = cat_name or "General"
            if categoria_actual not in categorias:
                categorias[categoria_actual] = []
            continue

        if categoria_actual not in categorias:
            categorias[categoria_actual] = []

        q_dict = q.to_dict()
        categorias[categoria_actual].append(q_dict)

    resultado = []
    for cat_name, qs in categorias.items():
        if qs:  # solo categorías con preguntas
            resultado.append({"name": cat_name, "questions": qs})

    return resultado


def generar_quiz_mbz(
    rutas: Sequence[Union[str, Path]],
    archivo_salida: Path,
    titulo: str = "Cuestionario",
    preguntas_por_categoria: int = 1,
    recursivo: bool = True,
    tiempo_limite: int = 3600,
    calificacion_maxima: float = 10.0,
    intentos: int = 1,
    shuffle_respuestas: bool = True,
    curso_id: int = 101,
    curso_nombre: str = "Curso Moodle",
) -> dict:
    """Genera un archivo .mbz con las preguntas unificadas y slots aleatorios por categoría."""
    categorias = recolectar_banco_unificado(rutas, recursivo=recursivo)
    if not categorias:
        raise ValueError("No se encontraron preguntas en las rutas especificadas.")

    timestamp = int(time.time())
    quiz_id = 50001
    module_id = 10001
    section_id = 20001
    context_module = 30001
    context_course = 40001

    with tempfile.TemporaryDirectory(prefix="voight-mbz-build-") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Crear directorios
        quiz_dir = tmp_path / f"activities/quiz_{module_id}"
        quiz_dir.mkdir(parents=True)
        (tmp_path / "files").mkdir(parents=True)

        # 2. Generar questions.xml y recopilar categorías
        # Estructura:
        # question_categories -> top, default, subcategorías
        qcat_root = ET.Element("question_categories")

        # Top category
        top_cat_id = 1001
        top_qc = ET.SubElement(qcat_root, "question_category", {"id": str(top_cat_id)})
        ET.SubElement(top_qc, "name").text = "top"
        ET.SubElement(top_qc, "contextid").text = str(context_course)
        ET.SubElement(top_qc, "contextlevel").text = "50"
        ET.SubElement(top_qc, "contextinstanceid").text = str(curso_id)
        ET.SubElement(top_qc, "info").text = ""
        ET.SubElement(top_qc, "infoformat").text = "0"
        ET.SubElement(top_qc, "stamp").text = f"voight+{timestamp}+top"
        ET.SubElement(top_qc, "parent").text = "0"
        ET.SubElement(top_qc, "sortorder").text = "0"
        ET.SubElement(top_qc, "idnumber").text = "$@NULL@$"
        ET.SubElement(top_qc, "question_bank_entries")

        # Categoría por defecto en curso (padre de las subcategorías)
        default_cat_id = 1002
        def_qc = ET.SubElement(qcat_root, "question_category", {"id": str(default_cat_id)})
        ET.SubElement(def_qc, "name").text = f"Por defecto en {curso_nombre}"
        ET.SubElement(def_qc, "contextid").text = str(context_course)
        ET.SubElement(def_qc, "contextlevel").text = "50"
        ET.SubElement(def_qc, "contextinstanceid").text = str(curso_id)
        ET.SubElement(def_qc, "info").text = f"Categoría por defecto para preguntas en {curso_nombre}."
        ET.SubElement(def_qc, "infoformat").text = "0"
        ET.SubElement(def_qc, "stamp").text = f"voight+{timestamp}+default"
        ET.SubElement(def_qc, "parent").text = str(top_cat_id)
        ET.SubElement(def_qc, "sortorder").text = "1"
        ET.SubElement(def_qc, "idnumber").text = "$@NULL@$"
        ET.SubElement(def_qc, "question_bank_entries")

        cat_ids = {}
        next_cat_id = 2001
        next_qbe_id = 50001
        next_qv_id = 60001
        next_q_id = 70001
        next_ans_id = 80001

        total_questions_count = 0

        for cat_info in categorias:
            cname = cat_info["name"]
            cid = next_cat_id
            next_cat_id += 1
            cat_ids[cname] = cid

            qc = ET.SubElement(qcat_root, "question_category", {"id": str(cid)})
            ET.SubElement(qc, "name").text = cname
            ET.SubElement(qc, "contextid").text = str(context_course)
            ET.SubElement(qc, "contextlevel").text = "50"
            ET.SubElement(qc, "contextinstanceid").text = str(curso_id)
            ET.SubElement(qc, "info").text = ""
            ET.SubElement(qc, "infoformat").text = "0"
            ET.SubElement(qc, "stamp").text = f"voight+{timestamp}+{cid}"
            ET.SubElement(qc, "parent").text = str(default_cat_id)
            ET.SubElement(qc, "sortorder").text = "1"
            ET.SubElement(qc, "idnumber").text = "$@NULL@$"
            qbes = ET.SubElement(qc, "question_bank_entries")

            for q_data in cat_info["questions"]:
                total_questions_count += 1
                qbe_id = next_qbe_id
                next_qbe_id += 1
                qv_id = next_qv_id
                next_qv_id += 1
                q_id = next_q_id
                next_q_id += 1

                qbe = ET.SubElement(qbes, "question_bank_entry", {"id": str(qbe_id)})
                ET.SubElement(qbe, "questioncategoryid").text = str(cid)
                ET.SubElement(qbe, "idnumber").text = str(q_data.get("id") or "$@NULL@$")
                ET.SubElement(qbe, "ownerid").text = "2"
                ET.SubElement(qbe, "nextversion").text = "$@NULL@$"

                q_version = ET.SubElement(qbe, "question_version")
                q_versions = ET.SubElement(q_version, "question_versions", {"id": str(qv_id)})
                ET.SubElement(q_versions, "version").text = "1"
                ET.SubElement(q_versions, "status").text = "ready"

                questions_elem = ET.SubElement(q_versions, "questions")
                q_elem = ET.SubElement(questions_elem, "question", {"id": str(q_id)})

                ET.SubElement(q_elem, "parent").text = "0"
                ET.SubElement(q_elem, "name").text = q_data.get("title") or "Pregunta"

                stem_obj = q_data.get("stem") or {}
                stem_text = stem_obj.get("text", "")
                stem_fmt = "4" if stem_obj.get("format") == "markdown" else "1"

                ET.SubElement(q_elem, "questiontext").text = stem_text
                ET.SubElement(q_elem, "questiontextformat").text = stem_fmt

                gf_obj = q_data.get("globalFeedback") or {}
                ET.SubElement(q_elem, "generalfeedback").text = gf_obj.get("text", "") if gf_obj else ""
                ET.SubElement(q_elem, "generalfeedbackformat").text = "1"

                moodle_meta = q_data.get("moodle") or {}
                ET.SubElement(q_elem, "defaultmark").text = f"{float(moodle_meta.get('defaultgrade', 1.0)):.7f}"
                ET.SubElement(q_elem, "penalty").text = f"{float(moodle_meta.get('penalty', 0.3333333)):.7f}"

                tipo = q_data.get("type", "MC")
                qtype_map = {
                    "MC": "multichoice",
                    "TF": "truefalse",
                    "Short": "shortanswer",
                    "Numerical": "numerical",
                    "Description": "description",
                }
                moodle_qtype = qtype_map.get(tipo, "multichoice")
                ET.SubElement(q_elem, "qtype").text = moodle_qtype
                ET.SubElement(q_elem, "length").text = "1"
                ET.SubElement(q_elem, "stamp").text = f"voight+{timestamp}+{q_id}"
                ET.SubElement(q_elem, "timecreated").text = str(timestamp)
                ET.SubElement(q_elem, "timemodified").text = str(timestamp)
                ET.SubElement(q_elem, "createdby").text = "2"
                ET.SubElement(q_elem, "modifiedby").text = "2"

                # Subplugins según el tipo
                if moodle_qtype == "multichoice":
                    plugin_mc = ET.SubElement(q_elem, "plugin_qtype_multichoice_question")
                    answers_elem = ET.SubElement(plugin_mc, "answers")
                    choices = q_data.get("choices") or []
                    for c in choices:
                        ans_id = next_ans_id
                        next_ans_id += 1
                        ans_elem = ET.SubElement(answers_elem, "answer", {"id": str(ans_id)})
                        c_text_obj = c.get("text") or {}
                        ET.SubElement(ans_elem, "answertext").text = c_text_obj.get("text", "")
                        ET.SubElement(ans_elem, "answerformat").text = "4" if c_text_obj.get("format") == "markdown" else "1"
                        frac = 1.0 if c.get("is_correct") else 0.0
                        if c.get("weight") is not None:
                            frac = float(c["weight"]) / 100.0
                        ET.SubElement(ans_elem, "fraction").text = f"{frac:.7f}"
                        ET.SubElement(ans_elem, "feedback").text = (c.get("feedback") or {}).get("text", "")
                        ET.SubElement(ans_elem, "feedbackformat").text = "1"

                    mc_elem = ET.SubElement(plugin_mc, "multichoice", {"id": str(q_id)})
                    ET.SubElement(mc_elem, "layout").text = "0"
                    single = "1" if sum(1 for c in choices if c.get("is_correct")) <= 1 else "0"
                    ET.SubElement(mc_elem, "single").text = single
                    ET.SubElement(mc_elem, "shuffleanswers").text = "1" if shuffle_respuestas else "0"
                    ET.SubElement(mc_elem, "correctfeedback").text = ""
                    ET.SubElement(mc_elem, "correctfeedbackformat").text = "1"
                    ET.SubElement(mc_elem, "partiallycorrectfeedback").text = ""
                    ET.SubElement(mc_elem, "partiallycorrectfeedbackformat").text = "1"
                    ET.SubElement(mc_elem, "incorrectfeedback").text = ""
                    ET.SubElement(mc_elem, "incorrectfeedbackformat").text = "1"
                    ET.SubElement(mc_elem, "answernumbering").text = "abc"
                    ET.SubElement(mc_elem, "shownumcorrect").text = "0"
                    ET.SubElement(mc_elem, "showstandardinstruction").text = "0"

                elif moodle_qtype == "truefalse":
                    plugin_tf = ET.SubElement(q_elem, "plugin_qtype_truefalse_question")
                    answers_elem = ET.SubElement(plugin_tf, "answers")
                    ans_true_id = next_ans_id
                    next_ans_id += 1
                    ans_false_id = next_ans_id
                    next_ans_id += 1

                    is_true = bool(q_data.get("isTrue", True))
                    t_ans = ET.SubElement(answers_elem, "answer", {"id": str(ans_true_id)})
                    ET.SubElement(t_ans, "answertext").text = "Verdadero"
                    ET.SubElement(t_ans, "answerformat").text = "0"
                    ET.SubElement(t_ans, "fraction").text = "1.0000000" if is_true else "0.0000000"
                    ET.SubElement(t_ans, "feedback").text = (q_data.get("trueFeedback") or {}).get("text", "")
                    ET.SubElement(t_ans, "feedbackformat").text = "1"

                    f_ans = ET.SubElement(answers_elem, "answer", {"id": str(ans_false_id)})
                    ET.SubElement(f_ans, "answertext").text = "Falso"
                    ET.SubElement(f_ans, "answerformat").text = "0"
                    ET.SubElement(f_ans, "fraction").text = "0.0000000" if is_true else "1.0000000"
                    ET.SubElement(f_ans, "feedback").text = (q_data.get("falseFeedback") or {}).get("text", "")
                    ET.SubElement(f_ans, "feedbackformat").text = "1"

                    tf_elem = ET.SubElement(plugin_tf, "truefalse", {"id": str(q_id)})
                    ET.SubElement(tf_elem, "trueanswer").text = str(ans_true_id)
                    ET.SubElement(tf_elem, "falseanswer").text = str(ans_false_id)
                    ET.SubElement(tf_elem, "showstandardinstruction").text = "1"

                ET.SubElement(q_elem, "plugin_qbank_comment_question").append(ET.Element("comments"))
                ET.SubElement(q_elem, "plugin_qbank_customfields_question").append(ET.Element("customfields"))
                ET.SubElement(q_elem, "question_hints")
                ET.SubElement(q_elem, "tags")

        # Serializar questions.xml
        (tmp_path / "questions.xml").write_bytes(
            ET.tostring(qcat_root, encoding="utf-8", xml_declaration=True)
        )

        # 3. Generar quiz.xml con question_instances (slots aleatorios)
        # Cada slot es una pregunta aleatoria de una categoría
        act_root = ET.Element(
            "activity",
            {
                "id": str(quiz_id),
                "moduleid": str(module_id),
                "modulename": "quiz",
                "contextid": str(context_module),
            },
        )
        quiz_elem = ET.SubElement(act_root, "quiz", {"id": str(quiz_id)})
        ET.SubElement(quiz_elem, "name").text = titulo
        ET.SubElement(quiz_elem, "intro").text = ""
        ET.SubElement(quiz_elem, "introformat").text = "1"
        ET.SubElement(quiz_elem, "timeopen").text = "0"
        ET.SubElement(quiz_elem, "timeclose").text = "0"
        ET.SubElement(quiz_elem, "timelimit").text = str(tiempo_limite)
        ET.SubElement(quiz_elem, "overduehandling").text = "autosubmit"
        ET.SubElement(quiz_elem, "graceperiod").text = "0"
        ET.SubElement(quiz_elem, "preferredbehaviour").text = "deferredfeedback"
        ET.SubElement(quiz_elem, "canredoquestions").text = "0"
        ET.SubElement(quiz_elem, "attempts_number").text = str(intentos)
        ET.SubElement(quiz_elem, "attemptonlast").text = "0"
        ET.SubElement(quiz_elem, "grademethod").text = "1"
        ET.SubElement(quiz_elem, "decimalpoints").text = "0"
        ET.SubElement(quiz_elem, "questiondecimalpoints").text = "-1"
        ET.SubElement(quiz_elem, "reviewattempt").text = "69888"
        ET.SubElement(quiz_elem, "reviewcorrectness").text = "4352"
        ET.SubElement(quiz_elem, "reviewmaxmarks").text = "69888"
        ET.SubElement(quiz_elem, "reviewmarks").text = "4352"
        ET.SubElement(quiz_elem, "reviewspecificfeedback").text = "4352"
        ET.SubElement(quiz_elem, "reviewgeneralfeedback").text = "4352"
        ET.SubElement(quiz_elem, "reviewrightanswer").text = "4352"
        ET.SubElement(quiz_elem, "reviewoverallfeedback").text = "4352"
        ET.SubElement(quiz_elem, "questionsperpage").text = "1"
        ET.SubElement(quiz_elem, "navmethod").text = "free"
        ET.SubElement(quiz_elem, "shuffleanswers").text = "1" if shuffle_respuestas else "0"

        # Calculamos slots totales
        total_slots = len(categorias) * preguntas_por_categoria
        ET.SubElement(quiz_elem, "sumgrades").text = f"{float(total_slots):.5f}"
        ET.SubElement(quiz_elem, "grade").text = f"{float(calificacion_maxima):.5f}"
        ET.SubElement(quiz_elem, "timecreated").text = str(timestamp)
        ET.SubElement(quiz_elem, "timemodified").text = str(timestamp)
        ET.SubElement(quiz_elem, "password").text = ""
        ET.SubElement(quiz_elem, "subnet").text = ""
        ET.SubElement(quiz_elem, "browsersecurity").text = "-"
        ET.SubElement(quiz_elem, "delay1").text = "0"
        ET.SubElement(quiz_elem, "delay2").text = "0"
        ET.SubElement(quiz_elem, "showuserpicture").text = "0"
        ET.SubElement(quiz_elem, "showblocks").text = "0"
        ET.SubElement(quiz_elem, "completionattemptsexhausted").text = "0"
        ET.SubElement(quiz_elem, "completionminattempts").text = "0"
        ET.SubElement(quiz_elem, "allowofflineattempts").text = "0"
        ET.SubElement(quiz_elem, "precreateattempts").text = "$@NULL@$"
        ET.SubElement(quiz_elem, "subplugin_quizaccess_seb_quiz")
        ET.SubElement(quiz_elem, "quiz_grade_items")

        q_instances = ET.SubElement(quiz_elem, "question_instances")

        current_slot = 1
        next_qi_id = 10001
        next_qsr_id = 20001

        for cat_info in categorias:
            cname = cat_info["name"]
            cid = cat_ids[cname]

            for _ in range(preguntas_por_categoria):
                qi_id = next_qi_id
                next_qi_id += 1
                qsr_id = next_qsr_id
                next_qsr_id += 1

                qi = ET.SubElement(q_instances, "question_instance", {"id": str(qi_id)})
                ET.SubElement(qi, "quizid").text = str(quiz_id)
                ET.SubElement(qi, "slot").text = str(current_slot)
                ET.SubElement(qi, "page").text = str(current_slot)
                ET.SubElement(qi, "displaynumber").text = "$@NULL@$"
                ET.SubElement(qi, "requireprevious").text = "0"
                ET.SubElement(qi, "maxmark").text = "1.0000000"
                ET.SubElement(qi, "quizgradeitemid").text = "$@NULL@$"

                qsr = ET.SubElement(qi, "question_set_reference", {"id": str(qsr_id)})
                ET.SubElement(qsr, "usingcontextid").text = str(context_module)
                ET.SubElement(qsr, "component").text = "mod_quiz"
                ET.SubElement(qsr, "questionarea").text = "slot"
                ET.SubElement(qsr, "questionscontextid").text = str(context_course)

                filtercondition = {
                    "filter": {
                        "category": {
                            "name": "category",
                            "jointype": 1,
                            "values": [cid],
                            "filteroptions": {"includesubcategories": False},
                        }
                    },
                    "cmid": module_id,
                    "courseid": curso_id,
                    "jointype": 2,
                    "qpage": 0,
                    "qperpage": 100,
                    "sortdata": {
                        "qbank_viewquestiontype__question_type_column": 4,
                        "mod_quiz__question__bank__question_name_text_column": 4,
                    },
                    "cat": f"{default_cat_id},{context_course}",
                    "tabname": "questions",
                }
                ET.SubElement(qsr, "filtercondition").text = json.dumps(
                    filtercondition, separators=(",", ":")
                )

                current_slot += 1

        sections_elem = ET.SubElement(quiz_elem, "sections")
        sec = ET.SubElement(sections_elem, "section", {"id": "1"})
        ET.SubElement(sec, "firstslot").text = "1"
        ET.SubElement(sec, "heading").text = ""
        ET.SubElement(sec, "shufflequestions").text = "0"

        feedbacks_elem = ET.SubElement(quiz_elem, "feedbacks")
        fb = ET.SubElement(feedbacks_elem, "feedback", {"id": "1"})
        ET.SubElement(fb, "feedbacktext").text = ""
        ET.SubElement(fb, "feedbacktextformat").text = "1"
        ET.SubElement(fb, "mingrade").text = "0.00000"
        ET.SubElement(fb, "maxgrade").text = f"{float(calificacion_maxima) + 1.0:.5f}"

        ET.SubElement(quiz_elem, "overrides")
        ET.SubElement(quiz_elem, "grades")
        ET.SubElement(quiz_elem, "attempts")

        (quiz_dir / "quiz.xml").write_bytes(
            ET.tostring(act_root, encoding="utf-8", xml_declaration=True)
        )

        # 4. Generar inforef.xml para la actividad quiz
        inforef_root = ET.Element("inforef")

        # grade_itemref es indispensable para que Moodle mapee el grade_item de grades.xml
        giref = ET.SubElement(inforef_root, "grade_itemref")
        gi_entry = ET.SubElement(giref, "grade_item")
        ET.SubElement(gi_entry, "id").text = "1"

        qcref = ET.SubElement(inforef_root, "question_categoryref")
        # Incluir categoría top y default
        qc_top = ET.SubElement(qcref, "question_category")
        ET.SubElement(qc_top, "id").text = str(top_cat_id)
        qc_def = ET.SubElement(qcref, "question_category")
        ET.SubElement(qc_def, "id").text = str(default_cat_id)
        for cid in cat_ids.values():
            qc_entry = ET.SubElement(qcref, "question_category")
            ET.SubElement(qc_entry, "id").text = str(cid)

        (quiz_dir / "inforef.xml").write_bytes(
            ET.tostring(inforef_root, encoding="utf-8", xml_declaration=True)
        )

        # 5. Generar module.xml
        mod_root = ET.Element("module", {"id": str(module_id), "version": "2025100602"})
        ET.SubElement(mod_root, "modulename").text = "quiz"
        ET.SubElement(mod_root, "sectionid").text = str(section_id)
        ET.SubElement(mod_root, "sectionnumber").text = "1"
        ET.SubElement(mod_root, "idnumber").text = ""
        ET.SubElement(mod_root, "added").text = str(timestamp)
        ET.SubElement(mod_root, "score").text = "0"
        ET.SubElement(mod_root, "indent").text = "0"
        ET.SubElement(mod_root, "visible").text = "1"
        ET.SubElement(mod_root, "visibleoncoursepage").text = "1"
        ET.SubElement(mod_root, "visibleold").text = "1"
        ET.SubElement(mod_root, "groupmode").text = "0"
        ET.SubElement(mod_root, "groupingid").text = "0"
        ET.SubElement(mod_root, "completion").text = "0"
        ET.SubElement(mod_root, "completiongradeitemnumber").text = "$@NULL@$"
        ET.SubElement(mod_root, "completionpassgrade").text = "0"
        ET.SubElement(mod_root, "completionview").text = "0"
        ET.SubElement(mod_root, "completionexpected").text = "0"
        ET.SubElement(mod_root, "availability").text = "$@NULL@$"
        ET.SubElement(mod_root, "showdescription").text = "0"
        ET.SubElement(mod_root, "downloadcontent").text = "1"
        ET.SubElement(mod_root, "lang").text = ""
        ET.SubElement(mod_root, "enableaitools").text = "$@NULL@$"
        ET.SubElement(mod_root, "enabledaiactions").text = "$@NULL@$"
        ET.SubElement(mod_root, "tags")

        (quiz_dir / "module.xml").write_bytes(
            ET.tostring(mod_root, encoding="utf-8", xml_declaration=True)
        )

        # 6. Generar grades.xml
        grades_root = ET.Element("activity_gradebook")
        grade_items = ET.SubElement(grades_root, "grade_items")
        gi = ET.SubElement(grade_items, "grade_item", {"id": "1"})
        ET.SubElement(gi, "categoryid").text = "1"
        ET.SubElement(gi, "itemname").text = titulo
        ET.SubElement(gi, "itemtype").text = "mod"
        ET.SubElement(gi, "itemmodule").text = "quiz"
        ET.SubElement(gi, "iteminstance").text = str(quiz_id)
        ET.SubElement(gi, "itemnumber").text = "0"
        ET.SubElement(gi, "iteminfo").text = "$@NULL@$"
        ET.SubElement(gi, "idnumber").text = ""
        ET.SubElement(gi, "calculation").text = "$@NULL@$"
        ET.SubElement(gi, "gradetype").text = "1"
        ET.SubElement(gi, "grademax").text = f"{float(calificacion_maxima):.5f}"
        ET.SubElement(gi, "grademin").text = "0.00000"
        ET.SubElement(gi, "scaleid").text = "$@NULL@$"
        ET.SubElement(gi, "outcomeid").text = "$@NULL@$"
        ET.SubElement(gi, "gradepass").text = "0.00000"
        ET.SubElement(gi, "multfactor").text = "1.00000"
        ET.SubElement(gi, "plusfactor").text = "0.00000"
        ET.SubElement(gi, "aggregationcoef").text = "0.00000"
        ET.SubElement(gi, "aggregationcoef2").text = "0.00000"
        ET.SubElement(gi, "weightoverride").text = "0"
        ET.SubElement(gi, "sortorder").text = "1"
        ET.SubElement(gi, "display").text = "0"
        ET.SubElement(gi, "decimals").text = "$@NULL@$"
        ET.SubElement(gi, "hidden").text = "0"
        ET.SubElement(gi, "locked").text = "0"
        ET.SubElement(gi, "locktime").text = "0"
        ET.SubElement(gi, "needsupdate").text = "0"
        ET.SubElement(gi, "timecreated").text = str(timestamp)
        ET.SubElement(gi, "timemodified").text = str(timestamp)
        ET.SubElement(gi, "grade_grades")

        (quiz_dir / "grades.xml").write_bytes(
            ET.tostring(grades_root, encoding="utf-8", xml_declaration=True)
        )

        # 7. Resto de XMLs de la actividad
        (quiz_dir / "calendar.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<events>\n</events>\n', encoding="utf-8"
        )
        (quiz_dir / "comments.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<comments>\n</comments>\n', encoding="utf-8"
        )
        (quiz_dir / "competencies.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<course_module_competencies>\n  <competencies>\n  </competencies>\n</course_module_competencies>\n',
            encoding="utf-8",
        )
        (quiz_dir / "completion.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<completions>\n  <completionviews>\n  </completionviews>\n</completions>\n',
            encoding="utf-8",
        )
        (quiz_dir / "filters.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<filters>\n  <filter_actives>\n  </filter_actives>\n  <filter_configs>\n  </filter_configs>\n</filters>\n',
            encoding="utf-8",
        )
        (quiz_dir / "grade_history.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<grade_history>\n  <grade_grades>\n  </grade_grades>\n</grade_history>\n',
            encoding="utf-8",
        )
        (quiz_dir / "roles.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<roles>\n  <role_overrides>\n  </role_overrides>\n  <role_assignments>\n  </role_assignments>\n</roles>\n',
            encoding="utf-8",
        )
        (quiz_dir / "xapistate.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<states>\n</states>\n', encoding="utf-8"
        )

        # 8. Archivos XML en la raíz del respaldo
        (tmp_path / "badges.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<badges>\n</badges>\n', encoding="utf-8"
        )
        (tmp_path / "completion.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<course_completion>\n</course_completion>\n',
            encoding="utf-8",
        )
        (tmp_path / "files.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<files>\n</files>\n', encoding="utf-8"
        )
        (tmp_path / "groups.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<groups>\n  <groupcustomfields>\n  </groupcustomfields>\n  <groupings>\n    <groupingcustomfields>\n    </groupingcustomfields>\n  </groupings>\n</groups>\n',
            encoding="utf-8",
        )
        (tmp_path / "outcomes.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<outcomes_definition>\n</outcomes_definition>\n',
            encoding="utf-8",
        )
        (tmp_path / "roles.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<roles_definition>\n</roles_definition>\n',
            encoding="utf-8",
        )
        (tmp_path / "scales.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<scales_definition>\n</scales_definition>\n',
            encoding="utf-8",
        )
        (tmp_path / "users.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<users>\n</users>\n', encoding="utf-8"
        )
        (tmp_path / "moodle_backup.log").write_text("", encoding="utf-8")

        # 9. Generar moodle_backup.xml
        mb_root = ET.Element("moodle_backup")
        info_elem = ET.SubElement(mb_root, "information")
        ET.SubElement(info_elem, "name").text = archivo_salida.name
        ET.SubElement(info_elem, "moodle_version").text = "2025100605.03"
        ET.SubElement(info_elem, "moodle_release").text = "5.1.5+ (Build: 20260630)"
        ET.SubElement(info_elem, "backup_version").text = "2025100600"
        ET.SubElement(info_elem, "backup_release").text = "5.1"
        ET.SubElement(info_elem, "backup_date").text = str(timestamp)
        ET.SubElement(info_elem, "mnet_remoteusers").text = "0"
        ET.SubElement(info_elem, "include_files").text = "0"
        ET.SubElement(info_elem, "include_file_references_to_external_content").text = "0"
        ET.SubElement(info_elem, "original_wwwroot").text = "http://localhost"
        ET.SubElement(info_elem, "original_site_identifier_hash").text = "00000000000000000000000000000000"
        ET.SubElement(info_elem, "original_course_id").text = str(curso_id)
        ET.SubElement(info_elem, "original_course_format").text = "topics"
        ET.SubElement(info_elem, "original_course_fullname").text = curso_nombre
        ET.SubElement(info_elem, "original_course_shortname").text = curso_nombre
        ET.SubElement(info_elem, "original_course_startdate").text = str(timestamp)
        ET.SubElement(info_elem, "original_course_enddate").text = str(timestamp + 365 * 86400)
        ET.SubElement(info_elem, "original_course_contextid").text = str(context_course)
        ET.SubElement(info_elem, "original_system_contextid").text = "1"

        details_elem = ET.SubElement(info_elem, "details")
        detail_elem = ET.SubElement(details_elem, "detail", {"backup_id": f"voight_{timestamp}"})
        ET.SubElement(detail_elem, "type").text = "activity"
        ET.SubElement(detail_elem, "format").text = "moodle2"
        ET.SubElement(detail_elem, "interactive").text = "1"
        ET.SubElement(detail_elem, "mode").text = "10"
        ET.SubElement(detail_elem, "execution").text = "1"
        ET.SubElement(detail_elem, "executiontime").text = "0"

        contents_elem = ET.SubElement(info_elem, "contents")
        acts_elem = ET.SubElement(contents_elem, "activities")
        act_entry = ET.SubElement(acts_elem, "activity")
        ET.SubElement(act_entry, "moduleid").text = str(module_id)
        ET.SubElement(act_entry, "sectionid").text = str(section_id)
        ET.SubElement(act_entry, "modulename").text = "quiz"
        ET.SubElement(act_entry, "title").text = titulo
        ET.SubElement(act_entry, "directory").text = f"activities/quiz_{module_id}"
        ET.SubElement(act_entry, "insubsection")

        settings_elem = ET.SubElement(info_elem, "settings")
        # Settings estándar
        config_settings = [
            ("root", "filename", archivo_salida.name),
            ("root", "users", "0"),
            ("root", "anonymize", "0"),
            ("root", "role_assignments", "0"),
            ("root", "activities", "1"),
            ("root", "blocks", "0"),
            ("root", "files", "0"),
            ("root", "filters", "0"),
            ("root", "comments", "0"),
            ("root", "badges", "0"),
            ("root", "calendarevents", "0"),
            ("root", "userscompletion", "0"),
            ("root", "logs", "0"),
            ("root", "grade_histories", "0"),
            ("root", "groups", "0"),
            ("root", "competencies", "0"),
            ("root", "customfield", "0"),
            ("root", "contentbankcontent", "0"),
            ("root", "xapistate", "0"),
            ("root", "legacyfiles", "0"),
            ("activity", f"quiz_{module_id}_included", "1"),
            ("activity", f"quiz_{module_id}_userinfo", "0"),
        ]
        for level, sname, sval in config_settings:
            s_elem = ET.SubElement(settings_elem, "setting")
            ET.SubElement(s_elem, "level").text = level
            if level == "activity":
                ET.SubElement(s_elem, "activity").text = f"quiz_{module_id}"
            ET.SubElement(s_elem, "name").text = sname
            ET.SubElement(s_elem, "value").text = sval

        (tmp_path / "moodle_backup.xml").write_bytes(
            ET.tostring(mb_root, encoding="utf-8", xml_declaration=True)
        )

        # 10. Recolectar archivos y empaquetar todo en tar.gz (archivo .mbz)
        # Nota sobre .ARCHIVE_INDEX:
        # En Moodle tgz_packer::$includeindex es opcional y solo se usa para listar archivos sin descomprimir.
        # En tgz_extractor, si .ARCHIVE_INDEX está presente, calcula el progreso como
        # ($beforeprogress + ($donefiles / $numfiles) * (PROGRESS_MAX - $beforeprogress)),
        # lo que genera "Division by zero" si Count es 0, o "progress() value out of range"
        # si $donefiles diverge de $numfiles.
        # Al omitir .ARCHIVE_INDEX ($numfiles = -1), tgz_extractor utiliza avance estimado por buffers
        # con límite estricto garantizado ($done < PROGRESS_MAX), restaurando de forma completamente
        # robusta e inmune a errores de rango o división.
        entries = []

        def _recurse_archive(curr: Path, prefix: str = ""):
            for item in sorted(os.listdir(curr)):
                if item == ".ARCHIVE_INDEX":
                    continue
                full = curr / item
                rel = (prefix + "/" + item).lstrip("/")
                if full.is_dir():
                    entries.append((rel, True, full))
                    _recurse_archive(full, rel)
                else:
                    entries.append((rel, False, full))

        _recurse_archive(tmp_path)

        archivo_salida.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archivo_salida, "w:gz") as tar:
            for rel, is_dir, full in entries:
                tar.add(full, arcname=rel, recursive=False)

    return {
        "categorias": len(categorias),
        "preguntas": total_questions_count,
        "slots": total_slots,
        "salida": str(archivo_salida),
    }
