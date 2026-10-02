// mxviz - Client-side Application

// Tipos de pregunta de Moodle: ícono y nombre para el árbol y el encabezado.
const TIPOS = {
    multichoice: {icon: '✅', label: 'Opción múltiple'},
    truefalse: {icon: '✔️', label: 'Verdadero/Falso'},
    shortanswer: {icon: '✏️', label: 'Respuesta corta'},
    numerical: {icon: '🔢', label: 'Numérica'},
    essay: {icon: '📝', label: 'Ensayo'},
    matching: {icon: '🔗', label: 'Emparejamiento'},
    description: {icon: '📄', label: 'Descripción'},
    multianswer: {icon: '🧩', label: 'Respuestas anidadas (cloze)'},
    cloze: {icon: '🧩', label: 'Respuestas anidadas (cloze)'},
    calculated: {icon: '🧮', label: 'Calculada'},
    calculatedsimple: {icon: '🧮', label: 'Calculada simple'},
    calculatedmulti: {icon: '🧮', label: 'Calculada de opción múltiple'},
    ordering: {icon: '↕️', label: 'Ordenamiento'},
    gapselect: {icon: '🔽', label: 'Seleccionar palabras faltantes'},
    ddwtos: {icon: '🖱️', label: 'Arrastrar y soltar sobre texto'},
    ddimageortext: {icon: '🖼️', label: 'Arrastrar y soltar sobre imagen'},
    ddmarker: {icon: '📍', label: 'Arrastrar y soltar marcadores'},
    randomsamatch: {icon: '🎲', label: 'Emparejamiento aleatorio de respuestas cortas'},
    unknown: {icon: '❓', label: 'Desconocido'},
};

// Cómo se editan las respuestas de cada tipo (answer_mode, lo decide el servidor).
const MODOS = {
    choices: {titulo: '✅ Respuestas:', agregar: '➕ Agregar respuesta'},
    numerical: {titulo: '🔢 Respuestas numéricas:', agregar: '➕ Agregar respuesta'},
    formulas: {titulo: '🧮 Fórmulas de respuesta:', agregar: '➕ Agregar fórmula'},
    truefalse: {titulo: '✔️ Respuesta correcta:', agregar: null},
    pairs: {titulo: '🔗 Pares (pregunta → respuesta):', agregar: '➕ Agregar par'},
    ordering: {titulo: '↕️ Elementos, en el orden correcto:', agregar: '➕ Agregar elemento'},
    groups: {titulo: '🧩 Opciones de los huecos [[n]]:', agregar: '➕ Agregar opción'},
};

const SI_NO = [['1', 'Sí'], ['0', 'No']];

class MxvizApp {
    constructor() {
        this.currentQuestion = null;
        this.currentFilepath = null;
        this.treeData = []; // Árbol completo tal como lo devuelve /api/tree
        this.allQuestions = []; // Lista lineal de las preguntas visibles (con el filtro aplicado)
        this.currentIndex = -1; // Índice actual en la lista
        this.init();
    }

    async init() {
        this.setupEventListeners();
        this.setupResizer();
        await this.loadTree();
    }

    setupEventListeners() {
        // Search
        document.getElementById('search-btn').addEventListener('click', () => this.handleSearch());
        document.getElementById('search-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleSearch();
        });

        // Filtro por cantidad de opciones
        document.getElementById('options-filter-op').addEventListener('change', () => this.applyOptionsFilter());
        document.getElementById('options-filter-n').addEventListener('input', () => this.applyOptionsFilter());

        // Sidebar toggle
        document.getElementById('toggle-sidebar-btn').addEventListener('click', () => this.toggleSidebar());
        document.getElementById('floating-sidebar-toggle').addEventListener('click', () => this.toggleSidebar());

        // Navigation buttons
        document.getElementById('first-btn').addEventListener('click', () => this.navigateToFirst());
        document.getElementById('prev-btn').addEventListener('click', () => this.navigateToPrevious());
        document.getElementById('next-btn').addEventListener('click', () => this.navigateToNext());
        document.getElementById('last-btn').addEventListener('click', () => this.navigateToLast());

        // Editor actions
        document.getElementById('save-btn').addEventListener('click', () => this.saveQuestion());
        document.getElementById('cancel-btn').addEventListener('click', () => this.cancelEdit());

        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });

        // Tags input
        document.getElementById('tags-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.addTag(e.target.value);
                e.target.value = '';
            }
        });

        // Add answer button
        document.getElementById('add-answer-btn').addEventListener('click', () => this.addAnswer());

        // Question text change for preview
        document.getElementById('question-text').addEventListener('input', () => {
            this.updatePreview();
        });

        // Fullwidth character conversion buttons
        document.getElementById('apply-fullwidth-btn').addEventListener('click', () => this.applyFullwidthConversion());
        document.getElementById('undo-fullwidth-btn').addEventListener('click', () => this.undoFullwidthConversion());
    }

    async loadTree() {
        const loading = document.getElementById('loading');
        const treeContainer = document.getElementById('tree-container');

        try {
            const response = await fetch('/api/tree');
            const data = await response.json();

            loading.style.display = 'none';
            this.treeData = data;
            this.applyOptionsFilter();
            console.log(`Total de preguntas cargadas: ${this.allQuestions.length}`);
        } catch (error) {
            loading.textContent = 'Error cargando árbol: ' + error.message;
        }
    }

    // Filtro por cantidad de opciones: el árbol y la navegación muestran sólo las preguntas
    // que cumplen la condición (las de tipos sin opciones, como V/F o ensayo, quedan afuera).
    optionsFilter() {
        const op = document.getElementById('options-filter-op').value;
        const input = document.getElementById('options-filter-n');
        input.disabled = !op;
        const n = parseInt(input.value, 10);
        if (!op || Number.isNaN(n)) return null;
        return (opciones) => opciones !== null && opciones !== undefined && (
            op === 'lt' ? opciones < n : op === 'gt' ? opciones > n : opciones === n);
    }

    filterTree(items, cumple) {
        const resultado = [];
        items.forEach(item => {
            if (item.type === 'directory') {
                const children = this.filterTree(item.children || [], cumple);
                const total = this.buildQuestionsList(children).length;
                if (total > 0) resultado.push({...item, children, question_count: total});
            } else if (item.type === 'file' && cumple(item.options)) {
                resultado.push(item);
            }
        });
        return resultado;
    }

    applyOptionsFilter() {
        const cumple = this.optionsFilter();
        const items = cumple ? this.filterTree(this.treeData, cumple) : this.treeData;
        const treeContainer = document.getElementById('tree-container');
        treeContainer.innerHTML = '';
        this.renderTree(items, treeContainer);

        this.allQuestions = this.buildQuestionsList(items);
        this.currentIndex = this.allQuestions.findIndex(q => q.path === this.currentFilepath);
        this.updateNavigationBar();

        const contador = document.getElementById('options-filter-count');
        contador.textContent = cumple ? `${this.allQuestions.length} preguntas` : '';
        if (cumple && this.allQuestions.length === 0) {
            treeContainer.innerHTML = '<p class="loading">Ninguna pregunta cumple el filtro.</p>';
        }
    }

    renderTree(items, container) {
        items.forEach(item => {
            const node = document.createElement('div');
            node.className = 'tree-node';

            if (item.type === 'directory') {
                const dirItem = document.createElement('div');
                dirItem.className = 'tree-item';
                
                const hasChildren = item.children && item.children.length > 0;
                
                dirItem.innerHTML = `
                    <span class="icon">📁</span>
                    <span class="name">${item.name}</span>
                    <span class="count">${item.question_count}</span>
                `;
                node.appendChild(dirItem);

                if (hasChildren) {
                    const children = document.createElement('div');
                    children.className = 'tree-children';
                    this.renderTree(item.children, children);
                    node.appendChild(children);
                }
            } else if (item.type === 'file') {
                const fileItem = document.createElement('div');
                fileItem.className = 'tree-item';
                const opciones = item.options === null || item.options === undefined ? ''
                    : `<span class="options-badge" title="Cantidad de opciones">${item.options} op.</span>`;
                fileItem.innerHTML = `
                    <span class="icon">${this.getTypeIcon(item.question_type)}</span>
                    <span class="name">${item.question_name || item.name}</span>
                    ${opciones}
                `;
                fileItem.addEventListener('click', () => this.loadQuestion(item.path));
                node.appendChild(fileItem);
            }

            container.appendChild(node);
        });
    }

    getTypeIcon(type) {
        return (TIPOS[type] || TIPOS.unknown).icon;
    }

    getTypeLabel(type) {
        return (TIPOS[type] || {label: type}).label;
    }

    // Crea un elemento: atributos (class, value, checked, on<evento>) e hijos (nodos o texto).
    el(tag, attrs = {}, ...hijos) {
        const e = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => {
            if (k === 'class') e.className = v;
            else if (k === 'value' || k === 'checked') e[k] = v;
            else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
            else e.setAttribute(k, v);
        });
        hijos.forEach(h => e.append(h));
        return e;
    }

    async loadQuestion(filepath) {
        try {
            this.showStatus('Cargando pregunta...');
            const response = await fetch(`/api/question/${filepath}`);
            const question = await response.json();

            if (question.error) {
                this.showStatus('Error: ' + question.error, 'error');
                return;
            }

            this.currentQuestion = question;
            this.currentFilepath = filepath;
            
            // Actualizar índice actual en la lista de navegación
            this.currentIndex = this.allQuestions.findIndex(q => q.path === filepath);
            
            this.renderQuestion(question);
            this.showEditor();
            this.showStatus('Pregunta cargada');
            this.updateNavigationBar();

            // Highlight active item
            document.querySelectorAll('.tree-item').forEach(item => {
                item.classList.remove('active');
            });
        } catch (error) {
            this.showStatus('Error cargando pregunta: ' + error.message, 'error');
        }
    }

    renderQuestion(question) {
        // Header
        document.getElementById('question-type').textContent = this.getTypeLabel(question.type);
        document.getElementById('question-type').title = question.type;
        document.getElementById('question-name').value = question.name || '';

        // Content
        document.getElementById('question-text').value = question.questiontext || '';
        document.getElementById('general-feedback').value = question.generalfeedback || '';
        document.getElementById('default-grade').value = question.defaultgrade || '1';
        document.getElementById('penalty').value = question.penalty || '0.1';
        
        // Actualizar selector de formato (si existe)
        const textFormatElem = document.getElementById('questiontext-format');
        if (textFormatElem) {
            textFormatElem.value = question.questiontext_format || 'html';
        }

        // Answers (según el tipo)
        this.renderAnswers(question);

        // Tags
        this.renderTags(question.tags || []);

        // Type-specific options
        this.renderTypeSpecificOptions(question);

        // File path
        document.getElementById('file-path').textContent = this.currentFilepath;

        // Update preview
        this.updatePreview();
    }

    renderAnswers(question) {
        const modo = question.answer_mode || 'none';
        const meta = MODOS[modo];
        document.getElementById('answers-edit-section').classList.toggle('sin-respuestas', !meta);
        document.getElementById('answers-preview-section').classList.toggle('sin-respuestas', !meta);
        const container = document.getElementById('answers-container');
        container.innerHTML = '';
        if (!meta) return;

        document.getElementById('answers-label').textContent = meta.titulo;
        document.getElementById('answers-preview-label').textContent = meta.titulo;
        const boton = document.getElementById('add-answer-btn');
        boton.style.display = meta.agregar ? '' : 'none';
        if (meta.agregar) boton.textContent = meta.agregar;

        if (modo === 'truefalse') {
            container.append(this.renderTrueFalse(question.answers || []));
            return;
        }
        const items = modo === 'pairs' ? question.subquestions : modo === 'groups' ? question.choices : question.answers;
        (items || []).forEach(item => container.append(this.renderItem(modo, item)));
    }

    renderItem(modo, item) {
        const fila = this.el('div', {class: 'answer-item', 'data-modo': modo});
        const cabecera = this.el('div', {class: 'answer-header'});
        const borrar = this.el('button', {class: 'answer-delete', type: 'button', onclick: () => fila.remove()}, '🗑️ Eliminar');
        const area = (campo, valor, placeholder, filas = 2) => this.el('textarea', {
            class: `answer-${campo}`, 'data-campo': campo, rows: filas, placeholder, value: valor || ''});
        const numero = (campo, valor, etiqueta, extra = {}) => [
            this.el('label', {}, etiqueta),
            this.el('input', {type: 'number', class: `answer-${campo}`, 'data-campo': campo, value: valor ?? '', ...extra}),
        ];

        if (modo === 'choices' || modo === 'numerical' || modo === 'formulas') {
            cabecera.append(...numero('fraction', item.fraction ?? '0', 'Puntos (%):', {step: 'any', min: '-100', max: '100'}));
            if (modo !== 'choices') {
                cabecera.append(...numero('tolerance', item.tolerance ?? '0', 'Tolerancia ±:', {step: 'any', min: '0'}));
            }
            cabecera.append(borrar);
            const texto = modo === 'numerical' ? 'Valor numérico'
                : modo === 'formulas' ? 'Fórmula, p. ej. {a} + {b}' : 'Texto de la respuesta';
            fila.append(cabecera, area('text', item.text, texto), area('feedback', item.feedback, 'Retroalimentación (opcional)'));
        } else if (modo === 'pairs') {
            cabecera.append(this.el('span', {class: 'answer-hint'}, 'Con la pregunta vacía, la respuesta queda como distractor'), borrar);
            fila.append(cabecera, area('text', item.text, 'Pregunta'),
                this.el('input', {type: 'text', class: 'answer-answer', 'data-campo': 'answer', placeholder: 'Respuesta', value: item.answer || ''}));
        } else if (modo === 'ordering') {
            const mover = (subir) => {
                const vecino = subir ? fila.previousElementSibling : fila.nextElementSibling;
                if (vecino) (subir ? vecino.before(fila) : vecino.after(fila));
            };
            cabecera.append(
                this.el('button', {class: 'btn btn-small', type: 'button', title: 'Subir', onclick: () => mover(true)}, '▲'),
                this.el('button', {class: 'btn btn-small', type: 'button', title: 'Bajar', onclick: () => mover(false)}, '▼'),
                borrar);
            fila.append(cabecera, area('text', item.text, 'Elemento'));
        } else if (modo === 'groups') {
            cabecera.append(...numero('group', item.group || '1', 'Grupo:', {min: '1', step: '1'}));
            if (this.currentQuestion && this.currentQuestion.type === 'ddwtos') {
                cabecera.append(this.el('label', {class: 'answer-check'},
                    this.el('input', {type: 'checkbox', 'data-campo': 'infinite', checked: !!item.infinite}), ' Ilimitada'));
            }
            cabecera.append(borrar);
            fila.append(cabecera, area('text', item.text, 'Texto de la opción', 1));
        }
        return fila;
    }

    renderTrueFalse(answers) {
        const porValor = {};
        answers.forEach(a => { porValor[(a.text || '').toLowerCase()] = a; });
        const fila = this.el('div', {class: 'answer-item', 'data-modo': 'truefalse'});
        const correcta = this.el('select', {'data-campo': 'correcta'},
            this.el('option', {value: 'true'}, 'Verdadero'), this.el('option', {value: 'false'}, 'Falso'));
        correcta.value = parseFloat((porValor.true || {}).fraction) > 0 ? 'true' : 'false';
        fila.append(this.el('div', {class: 'answer-header'}, this.el('label', {}, 'La afirmación es:'), correcta));
        [['true', 'Verdadero'], ['false', 'Falso']].forEach(([valor, nombre]) => fila.append(
            this.el('label', {class: 'answer-hint'}, `Retroalimentación si responde «${nombre}»:`),
            this.el('textarea', {class: 'answer-feedback', 'data-tf': valor, rows: 2, value: (porValor[valor] || {}).feedback || ''})));
        return fila;
    }

    // Lo editado en la sección de respuestas, con la forma que espera el servidor.
    collectRespuestas() {
        const modo = (this.currentQuestion && this.currentQuestion.answer_mode) || 'none';
        const filas = [...document.querySelectorAll('#answers-container .answer-item')];
        const campo = (fila, nombre) => {
            const e = fila.querySelector(`[data-campo="${nombre}"]`);
            return e ? (e.type === 'checkbox' ? e.checked : e.value) : undefined;
        };
        if (modo === 'truefalse') {
            const fila = filas[0];
            if (!fila) return {answers: []};
            const correcta = campo(fila, 'correcta');
            return {answers: ['true', 'false'].map(v => ({
                text: v, fraction: v === correcta ? '100' : '0', feedback: fila.querySelector(`[data-tf="${v}"]`).value}))};
        }
        if (modo === 'pairs') return {subquestions: filas.map(f => ({text: campo(f, 'text'), answer: campo(f, 'answer')}))};
        if (modo === 'groups') {
            return {choices: filas.map(f => ({text: campo(f, 'text'), group: campo(f, 'group'), infinite: !!campo(f, 'infinite')}))};
        }
        if (!MODOS[modo]) return {};
        return {answers: filas.map((f, i) => {
            const a = {text: campo(f, 'text'), feedback: campo(f, 'feedback') ?? '', fraction: campo(f, 'fraction') ?? String(i + 1)};
            const tolerancia = campo(f, 'tolerance');
            if (tolerancia !== undefined) a.tolerance = tolerancia;
            return a;
        })};
    }

    renderTags(tags) {
        const tagsContainer = document.getElementById('tags-container');
        tagsContainer.innerHTML = '';

        tags.forEach(tag => {
            const tagElem = document.createElement('span');
            tagElem.className = 'tag';
            tagElem.innerHTML = `
                ${tag}
                <button class="tag-remove" onclick="app.removeTag('${tag}')">×</button>
            `;
            tagsContainer.appendChild(tagElem);
        });
    }

    renderTypeSpecificOptions(question) {
        const container = document.getElementById('type-specific-options');
        container.innerHTML = '';
        const t = question.type;
        const grupo = (etiqueta, control) => this.el('div', {class: 'form-group'}, this.el('label', {}, etiqueta), control);
        const sel = (campo, etiqueta, opciones, defecto) => {
            const s = this.el('select', {'data-campo': campo}, ...opciones.map(([v, n]) => this.el('option', {value: v}, n)));
            s.value = question[campo] || defecto;
            return grupo(etiqueta, s);
        };
        const num = (campo, etiqueta, defecto, min = '0') => grupo(etiqueta,
            this.el('input', {type: 'number', 'data-campo': campo, min, value: question[campo] || defecto}));
        const nota = (texto) => this.el('p', {class: 'type-note'}, texto);
        const lista = (titulo, items) => this.el('div', {class: 'type-note'}, titulo,
            this.el('ul', {}, ...items.map(i => this.el('li', {}, i))));

        // GIFT no guarda estas opciones: Moodle usa sus valores por defecto al importar.
        const xml = question.source_format !== 'gift';
        if (xml && t === 'multichoice') {
            container.append(
                sel('single', 'Respuesta única:', [['1', 'Sí'], ['0', 'No (múltiples respuestas)']], '1'),
                sel('shuffleanswers', 'Mezclar respuestas:', SI_NO, '1'),
                sel('answernumbering', 'Numeración:', [['abc', 'a, b, c, ...'], ['ABCD', 'A, B, C, ...'], ['123', '1, 2, 3, ...'],
                    ['iii', 'i, ii, iii, ...'], ['IIII', 'I, II, III, ...'], ['none', 'Sin numeración']], 'abc'));
        } else if (xml && t === 'shortanswer') {
            container.append(sel('usecase', 'Distinguir mayúsculas:', [['0', 'No'], ['1', 'Sí']], '0'));
        } else if (xml && ['matching', 'gapselect', 'ddwtos'].includes(t)) {
            container.append(sel('shuffleanswers', 'Mezclar opciones:', SI_NO, '1'));
        } else if (xml && t === 'essay') {
            container.append(
                sel('responseformat', 'Formato de respuesta:', [['editor', 'Editor HTML'], ['editorfilepicker', 'Editor + archivos'],
                    ['plain', 'Texto plano'], ['monospaced', 'Texto plano, monoespaciado'], ['noinline', 'Sin texto (sólo archivos)']], 'editor'),
                sel('responserequired', 'Respuesta obligatoria:', SI_NO, '1'),
                num('responsefieldlines', 'Líneas de respuesta:', '15', '1'),
                sel('attachments', 'Archivos adjuntos:', [['0', 'No'], ['1', '1'], ['2', '2'], ['3', '3'], ['-1', 'Ilimitados']], '0'),
                grupo('Información para quien califica:',
                    this.el('textarea', {'data-campo': 'graderinfo', class: 'editor-textarea', rows: 3, value: question.graderinfo || ''})));
        } else if (t === 'randomsamatch') {
            container.append(num('choose', 'Cantidad de preguntas a elegir:', '2', '2'),
                sel('subcats', 'Incluir subcategorías:', SI_NO, '1'),
                nota('Toma al azar preguntas de respuesta corta de la categoría y las presenta como emparejamiento.'));
        }

        if (question.source_format === 'gift' && question.embedded) {
            container.append(nota('Palabra faltante: el _____ del enunciado marca dónde se muestran las opciones.'));
        }
        if (t === 'description') {
            container.append(nota('Descripción: sólo texto, sin respuestas ni puntaje.'));
        } else if (t === 'multianswer' || t === 'cloze') {
            container.append(nota('Las respuestas van embebidas en el enunciado con la sintaxis cloze: '
                + '{1:MULTICHOICE:=correcta~incorrecta}, {1:SHORTANSWER:=respuesta}, {1:NUMERICAL:=3:0.1}.'));
        } else if (t === 'gapselect' || t === 'ddwtos') {
            container.append(nota('En el enunciado, [[1]], [[2]]… marcan los huecos: el número es la posición de la opción '
                + 'correcta en la lista (desde 1) y cada hueco ofrece las opciones de su grupo.'));
        } else if (t === 'ordering') {
            container.append(nota('El orden de la lista es el orden correcto; Moodle muestra los elementos mezclados.'));
        } else if (t && t.startsWith('calculated')) {
            container.append(nota('Las variables ({a}, {b}…) y sus conjuntos de valores se conservan tal cual; se editan en Moodle.'));
            if ((question.datasets || []).length) {
                container.append(lista('Variables:', question.datasets.map(d => `{${d.name}}: de ${d.min} a ${d.max}`)));
            }
        } else if (t === 'ddimageortext' || t === 'ddmarker') {
            container.append(nota('La imagen de fondo, las zonas y los elementos se conservan tal cual; se editan en Moodle.'));
            if ((question.drags || []).length) container.append(lista('Elementos para arrastrar:', question.drags));
        } else if (!TIPOS[t]) {
            container.append(nota(`Tipo «${t}» sin editor propio: se editan los campos comunes y el resto se conserva.`));
        }
    }

    addAnswer() {
        const modo = this.currentQuestion && this.currentQuestion.answer_mode;
        if (!MODOS[modo] || modo === 'truefalse') return;
        const vacio = {fraction: '0', text: '', feedback: '', tolerance: '0', group: '1', answer: ''};
        document.getElementById('answers-container').append(this.renderItem(modo, vacio));
    }

    addTag(tagText) {
        if (!tagText.trim()) return;

        const tagsContainer = document.getElementById('tags-container');
        const tagElem = document.createElement('span');
        tagElem.className = 'tag';
        tagElem.innerHTML = `
            ${tagText}
            <button class="tag-remove" onclick="app.removeTag('${tagText}')">×</button>
        `;
        tagsContainer.appendChild(tagElem);
    }

    removeTag(tagText) {
        const tags = document.querySelectorAll('.tag');
        tags.forEach(tag => {
            if (tag.textContent.trim().startsWith(tagText)) {
                tag.remove();
            }
        });
    }

    switchTab(tabName) {
        // Update buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        // Update content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.style.display = 'none';
        });

        if (tabName === 'edit') {
            document.getElementById('edit-tab').style.display = 'block';
            // Show edit elements, hide preview elements
            document.querySelectorAll('.edit-only').forEach(el => el.style.display = '');
            document.querySelectorAll('.preview-only').forEach(el => el.style.display = 'none');
        } else if (tabName === 'preview') {
            document.getElementById('preview-tab').style.display = 'block';
            // Hide edit elements, show preview elements
            document.querySelectorAll('.edit-only').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.preview-only').forEach(el => el.style.display = 'block');
            this.updateFullPreview();
        }
    }

    updatePreview() {
        const questionText = document.getElementById('question-text').value;
        const previewBox = document.getElementById('question-preview');
        previewBox.innerHTML = this.renderMarkdown(questionText);
    }
    
    updateFullPreview() {
        // Update question text preview
        this.updatePreview();
        
        // Update general feedback preview
        const generalFeedback = document.getElementById('general-feedback').value;
        const feedbackPreview = document.getElementById('general-feedback-preview');
        feedbackPreview.innerHTML = this.renderMarkdown(generalFeedback) || '<em style="color: #999;">Sin retroalimentación general</em>';
        
        // Update answers preview
        this.updateAnswersPreview();
        
        // Update options preview
        const defaultGrade = document.getElementById('default-grade').value;
        const penalty = document.getElementById('penalty').value;
        document.getElementById('default-grade-preview').textContent = defaultGrade || '1';
        document.getElementById('penalty-preview').textContent = penalty || '0.1';
        
        // Update type-specific options preview
        this.updateTypeSpecificPreview();
        
        // Update tags preview
        this.updateTagsPreview();
    }
    
    updateAnswersPreview() {
        const cont = document.getElementById('answers-preview-container');
        cont.innerHTML = '';
        const modo = (this.currentQuestion && this.currentQuestion.answer_mode) || 'none';
        if (!MODOS[modo]) return;
        const datos = this.collectRespuestas();
        const items = datos.answers || datos.subquestions || datos.choices || [];
        if (items.length === 0) {
            cont.append(this.el('p', {class: 'preview-empty'}, 'No hay respuestas definidas'));
            return;
        }
        const md = (texto, clase = 'answer-preview-text') => {
            const d = this.el('div', {class: clase});
            d.innerHTML = this.renderMarkdown(texto) || '<em style="color: #999;">Vacío</em>';
            return d;
        };

        if (modo === 'pairs') {
            items.forEach(p => cont.append(this.el('div', {class: 'answer-preview-item pair'},
                md(p.text), this.el('span', {class: 'pair-arrow'}, '→'), this.el('strong', {}, p.answer || '—'))));
        } else if (modo === 'ordering') {
            cont.append(this.el('ol', {class: 'ordering-preview'}, ...items.map(a => this.el('li', {}, md(a.text)))));
        } else if (modo === 'groups') {
            const grupos = {};
            items.forEach((c, i) => { (grupos[c.group || '1'] = grupos[c.group || '1'] || []).push(`[[${i + 1}]] ${c.text}`); });
            Object.keys(grupos).sort((a, b) => a - b).forEach(g => cont.append(this.el('div', {class: 'answer-preview-item'},
                this.el('strong', {}, `Grupo ${g}: `), grupos[g].join(' · '))));
        } else {
            const multiple = (document.getElementById('single') || {}).value === '0';
            items.forEach(a => {
                const fraccion = parseFloat(a.fraction) || 0;
                const clase = fraccion >= 100 ? 'correct' : fraccion > 0 ? 'partial' : 'incorrect';
                const texto = modo === 'truefalse' ? md(a.text === 'true' ? 'Verdadero' : 'Falso')
                    : modo === 'choices' ? md(a.text)
                    : this.el('div', {class: 'answer-preview-text'}, `${a.text}` + (parseFloat(a.tolerance) ? ` ± ${a.tolerance}` : ''));
                const contenido = this.el('div', {class: 'answer-preview-content'}, texto);
                if (fraccion > 0) contenido.append(this.el('div', {class: 'answer-preview-points'}, `${fraccion}% de los puntos`));
                if (a.feedback) contenido.append(md(a.feedback, 'answer-preview-feedback'));
                cont.append(this.el('div', {class: `answer-preview-item ${clase}`},
                    this.el('input', {type: multiple ? 'checkbox' : 'radio', class: 'answer-preview-radio', disabled: ''}), contenido));
            });
        }
    }

    updateTypeSpecificPreview() {
        const container = document.getElementById('type-specific-options-preview');
        container.innerHTML = '';
        document.querySelectorAll('#type-specific-options [data-campo]').forEach(e => {
            const etiqueta = e.closest('.form-group')?.querySelector('label')?.textContent || e.dataset.campo;
            const valor = e.tagName === 'SELECT' ? e.options[e.selectedIndex]?.text : e.value;
            container.append(this.el('div', {class: 'preview-item'},
                this.el('span', {class: 'preview-label'}, etiqueta), ' ', this.el('span', {class: 'preview-value'}, valor || '—')));
        });
        document.querySelectorAll('#type-specific-options .type-note').forEach(n => container.append(n.cloneNode(true)));
    }

    updateTagsPreview() {
        const tagsPreview = document.getElementById('tags-preview-container');
        const tags = this.collectTags();
        
        tagsPreview.innerHTML = '';
        
        if (tags.length === 0) {
            tagsPreview.innerHTML = '<em style="color: #999;">Sin tags</em>';
            return;
        }
        
        tags.forEach(tag => {
            const tagElem = document.createElement('span');
            tagElem.className = 'tag';
            tagElem.textContent = tag;
            tagsPreview.appendChild(tagElem);
        });
    }
    
    getNumberingLabel(value) {
        const labels = {
            'abc': 'a, b, c, ...',
            'ABCD': 'A, B, C, ...',
            '123': '1, 2, 3, ...',
            'none': 'Sin numeración'
        };
        return labels[value] || value;
    }
    
    getResponseFormatLabel(value) {
        const labels = {
            'editor': 'Editor HTML',
            'editorfilepicker': 'Editor + archivos',
            'plain': 'Texto plano'
        };
        return labels[value] || value;
    }
    
    renderMarkdown(text) {
        if (!text) return '';
        
        // Usar marked.js si está disponible, sino fallback a renderizado básico
        if (typeof marked !== 'undefined') {
            try {
                // Configurar marked para renderizado seguro
                marked.setOptions({
                    breaks: true,        // Convertir \n en <br>
                    gfm: true,           // GitHub Flavored Markdown
                    headerIds: false,    // No generar IDs en headers
                    mangle: false        // No codificar emails
                });
                
                return marked.parse(text);
            } catch (e) {
                console.error('Error renderizando Markdown:', e);
                return this.renderMarkdownBasic(text);
            }
        }
        
        return this.renderMarkdownBasic(text);
    }
    
    renderMarkdownBasic(text) {
        // Fallback: renderizado básico si marked.js no está disponible
        let html = text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`(.+?)`/g, '<code>$1</code>')
            .replace(/```([^`]+)```/g, '<pre><code>$1</code></pre>')
            .replace(/\n/g, '<br>');

        return html;
    }

    async saveQuestion() {
        try {
            this.showStatus('Guardando...', 'info');

            // Obtener formato de texto seleccionado (si existe el selector)
            const textFormatElem = document.getElementById('questiontext-format');
            const textFormat = textFormatElem ? textFormatElem.value : (this.currentQuestion.questiontext_format || 'html');

            // Recopilar datos del formulario
            const questionData = {
                type: this.currentQuestion.type,
                name: document.getElementById('question-name').value,
                questiontext: document.getElementById('question-text').value,
                questiontext_format: textFormat,
                generalfeedback: document.getElementById('general-feedback').value,
                defaultgrade: document.getElementById('default-grade').value,
                penalty: document.getElementById('penalty').value,
                tags: this.collectTags(),
            };

            // Respuestas y opciones propias del tipo
            Object.assign(questionData, this.collectRespuestas());
            document.querySelectorAll('#type-specific-options [data-campo]').forEach(e => {
                questionData[e.dataset.campo] = e.type === 'checkbox' ? (e.checked ? '1' : '0') : e.value;
            });

            // Enviar al servidor
            const response = await fetch(`/api/question/${this.currentFilepath}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(questionData)
            });

            const result = await response.json();

            if (result.error) {
                this.showStatus('Error: ' + result.error, 'error');
            } else {
                this.showStatus('✅ Guardado exitosamente', 'success');
                await this.loadTree();  // la cantidad de opciones o el nombre pueden haber cambiado
            }
        } catch (error) {
            this.showStatus('Error guardando: ' + error.message, 'error');
        }
    }

    collectTags() {
        const tags = [];
        document.querySelectorAll('.tag').forEach(tagElem => {
            const tagText = tagElem.textContent.trim().replace('×', '').trim();
            if (tagText) tags.push(tagText);
        });
        return tags;
    }

    cancelEdit() {
        if (confirm('¿Descartar cambios?')) {
            if (this.currentFilepath) {
                this.loadQuestion(this.currentFilepath);
            } else {
                this.showWelcome();
            }
        }
    }

    async handleSearch() {
        const query = document.getElementById('search-input').value;
        if (!query.trim()) return;

        try {
            this.showStatus('Buscando...', 'info');
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const results = await response.json();

            this.showSearchResults(results, query);
            this.showStatus(`Encontrados ${results.length} resultados`);
        } catch (error) {
            this.showStatus('Error en búsqueda: ' + error.message, 'error');
        }
    }

    showSearchResults(results, query) {
        const resultsDiv = document.getElementById('search-results');
        const resultsContainer = document.getElementById('results-container');
        const welcomeDiv = document.getElementById('welcome');
        const editorDiv = document.getElementById('editor');

        // Ocultar otras vistas
        welcomeDiv.style.display = 'none';
        editorDiv.style.display = 'none';
        resultsDiv.style.display = 'block';

        // Limpiar resultados anteriores
        resultsContainer.innerHTML = '';

        if (results.length === 0) {
            resultsContainer.innerHTML = '<p>No se encontraron resultados.</p>';
            return;
        }

        results.forEach(result => {
            const resultDiv = document.createElement('div');
            resultDiv.className = 'result-item';
            resultDiv.innerHTML = `
                <div class="result-name">${this.highlightQuery(result.name, query)}</div>
                <div class="result-category">📁 ${result.category} | ${this.getTypeIcon(result.type)} ${result.type}</div>
                <div class="result-preview">${this.highlightQuery(result.preview, query)}</div>
            `;
            resultDiv.addEventListener('click', () => {
                this.loadQuestion(result.path);
            });
            resultsContainer.appendChild(resultDiv);
        });
    }

    highlightQuery(text, query) {
        if (!text || !query) return text;
        const regex = new RegExp(`(${query})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }

    showEditor() {
        document.getElementById('welcome').style.display = 'none';
        document.getElementById('search-results').style.display = 'none';
        document.getElementById('editor').style.display = 'block';
        document.getElementById('navigation-bar').style.display = 'flex';
    }

    showWelcome() {
        document.getElementById('editor').style.display = 'none';
        document.getElementById('search-results').style.display = 'none';
        document.getElementById('welcome').style.display = 'block';
        document.getElementById('navigation-bar').style.display = 'none';
    }

    showStatus(message, type = 'info') {
        const statusMessage = document.getElementById('status-message');
        statusMessage.textContent = message;
        statusMessage.style.color = type === 'error' ? 'var(--danger-color)' : 
                                   type === 'success' ? 'var(--secondary-color)' : 
                                   'var(--text-muted)';
    }

    // Navigation methods
    buildQuestionsList(items, list = []) {
        items.forEach(item => {
            if (item.type === 'file') {
                list.push({
                    name: item.name,
                    path: item.path
                });
            } else if (item.type === 'directory' && item.children) {
                this.buildQuestionsList(item.children, list);
            }
        });
        return list;
    }

    updateNavigationBar() {
        const counter = document.getElementById('question-counter');
        if (this.allQuestions.length === 0) {
            counter.textContent = '0 / 0';
            ['first-btn', 'prev-btn', 'next-btn', 'last-btn'].forEach(id => {
                document.getElementById(id).disabled = true;
            });
            return;
        }

        const navName = document.getElementById('nav-question-name');
        const firstBtn = document.getElementById('first-btn');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const lastBtn = document.getElementById('last-btn');

        counter.textContent = `${this.currentIndex + 1} / ${this.allQuestions.length}`;
        
        if (this.currentIndex >= 0 && this.currentIndex < this.allQuestions.length) {
            navName.textContent = this.allQuestions[this.currentIndex].name;
        }

        // Habilitar/deshabilitar botones según posición
        firstBtn.disabled = this.currentIndex <= 0;
        prevBtn.disabled = this.currentIndex <= 0;
        nextBtn.disabled = this.currentIndex >= this.allQuestions.length - 1;
        lastBtn.disabled = this.currentIndex >= this.allQuestions.length - 1;
    }

    navigateToFirst() {
        if (this.allQuestions.length > 0) {
            this.navigateToIndex(0);
        }
    }

    navigateToPrevious() {
        if (this.currentIndex > 0) {
            this.navigateToIndex(this.currentIndex - 1);
        }
    }

    navigateToNext() {
        if (this.currentIndex < this.allQuestions.length - 1) {
            this.navigateToIndex(this.currentIndex + 1);
        }
    }

    navigateToLast() {
        if (this.allQuestions.length > 0) {
            this.navigateToIndex(this.allQuestions.length - 1);
        }
    }

    navigateToIndex(index) {
        if (index >= 0 && index < this.allQuestions.length) {
            const question = this.allQuestions[index];
            this.loadQuestion(question.path);
        }
    }

    // Fullwidth character conversion
    applyFullwidthConversion() {
        const textarea = document.getElementById('question-text');
        const text = textarea.value;
        
        // Diccionario de sustituciones: normal -> fullwidth
        const substitutions = {
            "==": "⩵",
            "=": "＝",
            ";": ";",
            "#": "＃",
            "{": "｛",
            "}": "｝",
            " ": " ",
            ">": "＞",
            "<": "＜",
            "[": "［",
            "]": "］",
            "(": "（",
            ")": "）",
            "*": "＊",
            '"': "＂",
            ":": "："
        };
        
        let converted = text;
        
        // PROTEGER guardas CDATA - guardar las guardas completas sin modificar
        const cdataStartPattern = /<!\[CDATA\[/g;
        const cdataEndPattern = /\]\]>/g;
        const cdataStarts = [];
        const cdataEnds = [];
        
        // Reemplazar guardas de inicio con placeholders
        converted = converted.replace(cdataStartPattern, (match) => {
            const placeholder = `__CDATA_START_${cdataStarts.length}__`;
            cdataStarts.push(match);
            return placeholder;
        });
        
        // Reemplazar guardas de cierre con placeholders
        converted = converted.replace(cdataEndPattern, (match) => {
            const placeholder = `__CDATA_END_${cdataEnds.length}__`;
            cdataEnds.push(match);
            return placeholder;
        });
        
        // PROTEGER sintaxis Markdown
        // IMPORTANTE: El orden importa - de más específico a más general
        const markdownBlocks = [];
        let mdIndex = 0;
        
        // 1. Proteger bloques de código primero (más específico)
        converted = converted.replace(/(```[\s\S]*?```)/g, (match) => {
            const placeholder = `__MD_CODE_BLOCK_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 2. Proteger código inline
        converted = converted.replace(/(`[^`\n]+`)/g, (match) => {
            const placeholder = `__MD_INLINE_CODE_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 3. Proteger blockquotes (líneas completas que empiezan con >)
        converted = converted.replace(/^(>\s+.*)$/gm, (match) => {
            const placeholder = `__MD_BLOCKQUOTE_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 4. Proteger headers (# al inicio de línea)
        converted = converted.replace(/^(#{1,6}\s+.*)$/gm, (match) => {
            const placeholder = `__MD_HEADER_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 5. Proteger listas (*, - al inicio de línea)
        converted = converted.replace(/^(\s*[*\-]\s+.*)$/gm, (match) => {
            const placeholder = `__MD_LIST_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 6. Proteger negrita/cursiva (**texto** o *texto*)
        converted = converted.replace(/(\*{1,2}[^\*\n]+?\*{1,2})/g, (match) => {
            const placeholder = `__MD_EMPHASIS_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // Aplicar sustituciones
        // Primero aplicar == para que no se confunda con =
        if (substitutions["=="]) {
            converted = converted.replace(/==/g, substitutions["=="]);
        }
        
        // Luego aplicar el resto de sustituciones
        for (const [normal, fullwidth] of Object.entries(substitutions)) {
            if (normal !== "==") {
                // Escapar caracteres especiales para regex
                const escapedNormal = normal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const regex = new RegExp(escapedNormal, 'g');
                converted = converted.replace(regex, fullwidth);
            }
        }
        
        // Restaurar bloques Markdown sin modificar
        markdownBlocks.forEach(({ placeholder, original }) => {
            converted = converted.replace(placeholder, original);
        });
        
        // Agregar ↵ al final de cada línea para hacer explícitos los saltos de línea
        converted = converted.replace(/\n/g, '↵\n');
        
        // Restaurar guardas CDATA sin modificar
        cdataStarts.forEach((guard, index) => {
            const placeholder = `__CDATA_START_${index}__`;
            converted = converted.replace(placeholder, guard);
        });
        
        cdataEnds.forEach((guard, index) => {
            const placeholder = `__CDATA_END_${index}__`;
            converted = converted.replace(placeholder, guard);
        });
        
        textarea.value = converted;
        this.updatePreview();
        this.showNotification('Conversión a fullwidth aplicada (saltos de línea marcados con ↵)', 'success');
    }

    undoFullwidthConversion() {
        const textarea = document.getElementById('question-text');
        const text = textarea.value;
        
        // Diccionario de sustituciones: fullwidth -> normal
        const reverseSubstitutions = {
            "⩵": "==",
            "＝": "=",
            ";": ";",
            "＃": "#",
            "｛": "{",
            "｝": "}",
            " ": " ",
            "＞": ">",
            "＜": "<",
            "［": "[",
            "］": "]",
            "（": "(",
            "）": ")",
            "＊": "*",
            "＂": '"',
            "：": ":",
            "↵": ""  // Eliminar marcadores de salto de línea
        };
        
        let converted = text;
        
        // PROTEGER guardas CDATA antes de revertir
        const cdataStartPattern = /<!\[CDATA\[/g;
        const cdataEndPattern = /\]\]>/g;
        const cdataStarts = [];
        const cdataEnds = [];
        
        // Reemplazar guardas de inicio con placeholders
        converted = converted.replace(cdataStartPattern, (match) => {
            const placeholder = `__CDATA_START_${cdataStarts.length}__`;
            cdataStarts.push(match);
            return placeholder;
        });
        
        // Reemplazar guardas de cierre con placeholders
        converted = converted.replace(cdataEndPattern, (match) => {
            const placeholder = `__CDATA_END_${cdataEnds.length}__`;
            cdataEnds.push(match);
            return placeholder;
        });
        
        // PROTEGER sintaxis Markdown (mismo orden que en apply)
        const markdownBlocks = [];
        let mdIndex = 0;
        
        // 1. Proteger bloques de código primero
        converted = converted.replace(/(```[\s\S]*?```)/g, (match) => {
            const placeholder = `__MD_CODE_BLOCK_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 2. Proteger código inline
        converted = converted.replace(/(`[^`\n]+`)/g, (match) => {
            const placeholder = `__MD_INLINE_CODE_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 3. Proteger blockquotes
        converted = converted.replace(/^(>\s+.*)$/gm, (match) => {
            const placeholder = `__MD_BLOCKQUOTE_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 4. Proteger headers
        converted = converted.replace(/^(#{1,6}\s+.*)$/gm, (match) => {
            const placeholder = `__MD_HEADER_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 5. Proteger listas
        converted = converted.replace(/^(\s*[*\-]\s+.*)$/gm, (match) => {
            const placeholder = `__MD_LIST_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // 6. Proteger negrita/cursiva
        converted = converted.replace(/(\*{1,2}[^\*\n]+?\*{1,2})/g, (match) => {
            const placeholder = `__MD_EMPHASIS_${mdIndex++}__`;
            markdownBlocks.push({ placeholder, original: match });
            return placeholder;
        });
        
        // Aplicar sustituciones reversas
        for (const [fullwidth, normal] of Object.entries(reverseSubstitutions)) {
            // Escapar caracteres especiales en fullwidth para regex
            const escapedFullwidth = fullwidth.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(escapedFullwidth, 'g');
            converted = converted.replace(regex, normal);
        }
        
        // Restaurar bloques Markdown sin modificar
        markdownBlocks.forEach(({ placeholder, original }) => {
            converted = converted.replace(placeholder, original);
        });
        
        // Restaurar guardas CDATA sin modificar
        cdataStarts.forEach((guard, index) => {
            const placeholder = `__CDATA_START_${index}__`;
            converted = converted.replace(placeholder, guard);
        });
        
        cdataEnds.forEach((guard, index) => {
            const placeholder = `__CDATA_END_${index}__`;
            converted = converted.replace(placeholder, guard);
        });
        
        textarea.value = converted;
        this.updatePreview();
        this.showNotification('Conversión fullwidth revertida', 'success');
    }

    showNotification(message, type = 'info') {
        // Crear elemento de notificación
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'success' ? '#4caf50' : type === 'error' ? '#f44336' : '#2196f3'};
            color: white;
            border-radius: 4px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        // Remover después de 3 segundos
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    // Resizer functionality
    setupResizer() {
        const resizer = document.getElementById('resizer');
        const sidebar = document.getElementById('sidebar');
        const editorArea = document.getElementById('editor-area');
        
        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            startX = e.clientX;
            startWidth = sidebar.offsetWidth;
            resizer.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const deltaX = e.clientX - startX;
            const newWidth = startWidth + deltaX;
            
            // Limites: 200px mínimo, 600px máximo
            const minWidth = 200;
            const maxWidth = 600;
            
            if (newWidth >= minWidth && newWidth <= maxWidth) {
                sidebar.style.width = newWidth + 'px';
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }

    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const resizer = document.getElementById('resizer');
        const floatingToggle = document.getElementById('floating-sidebar-toggle');
        const toggleBtn = document.getElementById('toggle-sidebar-btn');
        
        sidebar.classList.toggle('collapsed');
        
        if (sidebar.classList.contains('collapsed')) {
            resizer.classList.add('hidden');
            floatingToggle.classList.add('visible');
            toggleBtn.textContent = '▶';
        } else {
            resizer.classList.remove('hidden');
            floatingToggle.classList.remove('visible');
            toggleBtn.textContent = '◀';
        }
    }
}

// Initialize app
const app = new MxvizApp();
