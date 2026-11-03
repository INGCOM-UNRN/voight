"""cerebro — editor web local de bancos de preguntas (absorbe a moodle-visor / mxviz).

Servidor Flask mínimo que sirve la misma interfaz de mxviz extendida con
soporte nativo para archivos GIFT además de Moodle XML.
"""

import os

from flask import Flask, render_template, jsonify, request, send_from_directory

from voight.ui.parsers import QuestionParser, GiftQuestionAdapter
from voight.ui.file_navigator import FileNavigator


def create_app(questions_dir: str) -> Flask:
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'voight-ui-local'
    app.config['BANCO_DIR'] = os.path.abspath(questions_dir)

    parser_xml = QuestionParser()
    parser_gift = GiftQuestionAdapter()
    navigator = FileNavigator(app.config['BANCO_DIR'])

    def _resolver(filepath: str) -> str:
        """Resuelve una ruta relativa dentro del directorio base (anti path-traversal)."""
        full = os.path.realpath(os.path.join(app.config['BANCO_DIR'], filepath))
        base = os.path.realpath(app.config['BANCO_DIR'])
        if not full.startswith(base + os.sep):
            raise ValueError('Ruta fuera del directorio de preguntas')
        return full

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/tree')
    def get_tree():
        try:
            return jsonify(navigator.get_directory_tree())
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/question/<path:filepath>')
    def get_question(filepath):
        try:
            full_path = _resolver(filepath)
            if not os.path.exists(full_path):
                return jsonify({'error': 'Archivo no encontrado'}), 404
            parser = parser_gift if full_path.lower().endswith('.gift') else parser_xml
            return jsonify(parser.parse_question(full_path))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/question/<path:filepath>', methods=['PUT'])
    def update_question(filepath):
        try:
            full_path = _resolver(filepath)
            if not os.path.exists(full_path):
                return jsonify({'error': 'Archivo no encontrado'}), 404
            data = request.get_json(force=True)
            parser = parser_gift if full_path.lower().endswith('.gift') else parser_xml
            parser.save_question(full_path, data)
            return jsonify({'success': True, 'message': 'Pregunta actualizada'})
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/codigo', methods=['POST'])
    def transformar_codigo_api():
        """Transforma las secciones de código del enunciado con el mismo motor que `voight fix
        code-chars` y `code-indent`: el texto fuera del código no se toca.

        operacion: `fullwidth` (símbolos a ancho completo), `normal` (símbolos a ASCII, las marcas
        quedan), `marcas` (indentación con · y saltos con ↵) o `sin-marcas` (las saca).
        """
        from voight.core.codigo import quitar_marcas, transformar_codigo

        data = request.get_json(force=True) or {}
        texto = data.get('texto', '')
        operacion = data.get('operacion')
        # El editor tiene el enunciado sin los escapes de GIFT (se agregan al guardar): para el
        # motor es texto plano, como el de un <text> de Moodle XML.
        if operacion == 'fullwidth':
            nuevo, cambios = transformar_codigo(texto, contexto='xml', fullwidth=True, espacios=False, saltos=False)
        elif operacion == 'normal':
            nuevo, cambios = transformar_codigo(texto, contexto='xml', fullwidth=False, conservar_marcas=True)
        elif operacion == 'marcas':
            nuevo, cambios = transformar_codigo(texto, contexto='xml', fullwidth=None, espacios=True, saltos=True)
        elif operacion == 'sin-marcas':
            # En GIFT una línea en blanco corta la pregunta: dentro del código conserva su ↵.
            nuevo, cambios = quitar_marcas(texto, contexto='xml', proteger_vacias=data.get('formato') == 'gift')
        else:
            return jsonify({'error': f'operación desconocida: {operacion!r}'}), 400
        return jsonify({'texto': nuevo, 'cambios': cambios})

    @app.route('/api/search')
    def search_questions():
        query = request.args.get('q', '')
        if not query:
            return jsonify([])
        try:
            return jsonify(navigator.search_questions(query))
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/static/<path:filename>')
    def serve_static(filename):
        return send_from_directory('static', filename)

    return app


def run(questions_dir: str, host: str = '127.0.0.1', port: int = 5000, debug: bool = False) -> None:
    app = create_app(questions_dir)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║  voight ui - Editor web de bancos (XML + GIFT)         ║
╚══════════════════════════════════════════════════════════╝

📂 Directorio: {app.config['BANCO_DIR']}
🌐 URL: http://{host}:{port}

Presiona Ctrl+C para detener el servidor
""")
    app.run(host=host, port=port, debug=debug)
