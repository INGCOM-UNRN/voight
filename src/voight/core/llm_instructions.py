VALIDATE_INSTRUCTIONS = r"""
# Instrucciones para LLM: Validación de Preguntas
`validate`, `analyze` y `health` aceptan GIFT y Moodle XML (también repositorios mixtos).
Al generar o corregir preguntas GIFT:
1. **Evita líneas en blanco internas**: No insertes líneas vacías entre el título, el enunciado y el bloque de respuestas. En GIFT, una línea en blanco termina la pregunta.
2. **Escapa los dos puntos**: No uses `:` en enunciados o respuestas a menos que lo escapes como `\:`. Para separadores visuales usa `：` (fullwidth).
3. **Títulos obligatorios**: Usa siempre `::Título::` al inicio para facilitar la organización.
4. **Resuelve duplicados**: Si el validador indica alta similitud, asegúrate de que la nueva pregunta aporte un valor distinto.
5. **Salud del banco** (`health`): la respuesta correcta no debe ser notablemente más larga que los distractores; incluye feedback en cada opción; usa al menos 3 opciones; los porcentajes parciales deben ser los que Moodle acepta (`%33.33333%`, no `%33.33%`).
6. **Redacción** (`health` la revisa): no uses «todas/ninguna de las anteriores» (se rompen al mezclar las opciones); resaltá las negaciones del enunciado (**NO**, **EXCEPTO**, **INCORRECTA**); los distractores deben ser plausibles y de largo parecido a la correcta; no pongas la correcta siempre primera.
7. **Código**: protegé el código (`format --fullwidth`), etiquetá su lenguaje (```c, ```java; `fix code-lang`) y no empieces líneas con `//` dentro del código sin proteger (GIFT las descarta como comentario).
8. **Revisión incremental**: `--desde origin/main` revisa sólo lo que cambió; `health --tui` recorre los hallazgos y aplica los arreglos automáticos.
"""

FORMAT_INSTRUCTIONS = r"""
# Instrucciones para LLM: Formato GIFT y Moodle XML
`format` formatea GIFT y Moodle XML (sangría de 2 espacios y `<text>` en CDATA).
Genera archivos GIFT siguiendo este estándar visual estricto:
1. **Título**: Primera línea, formato `::Título::`.
2. **Enunciado**: Siguiente línea inmediata, preferiblemente con prefijo `[markdown]`.
3. **Bloque de respuestas**: Abrir `{` en su propia línea, cerrar `}` en su propia línea.
4. **Indentación**: Usa exactamente 4 espacios para cada opción de respuesta (`=`, `~`, `#`).
5. **Sin espacios extra**: Evita líneas en blanco innecesarias dentro de la estructura.
6. **Verificar sin escribir**: `format --check` sale con código 1 si algún archivo cambiaría y `format --diff` muestra los cambios; usalos antes de dar por terminado un cambio.
7. **Código** (C/Java): `format --fullwidth` reemplaza `{ } = ~ # : \ //` (y `; < > [ ] ( ) * " &`) por formas fullwidth, marca la indentación con `·` (un punto por espacio) y cada fin de línea con `↵`. Una línea en blanco dentro del código debe quedar como `↵`.
"""

XML_INSTRUCTIONS = r"""
# Instrucciones para LLM: Mantenimiento XML
Al manipular archivos XML de Moodle:
1. **Secciones CDATA**: Envuelve SIEMPRE el contenido de los nodos `<text>` en `<![CDATA[ ... ]]>`.
2. **Atributo Format**: Asegúrate de que los bloques de texto tengan `format="markdown"` si el contenido lo requiere.
3. **Nombres de archivo**: Usa el subcomando `rename` para normalizar nombres basados en el título interno.
"""

CONVERT_INSTRUCTIONS = r"""
# Instrucciones para LLM: Conversión de Formatos
1. **HTML a Markdown**: Prefiere siempre el formato Markdown. Usa backticks (`) para código y negritas (**) para énfasis.
2. **Atributos de Formato**: Al convertir tags HTML, asegúrate de actualizar el atributo `format="html"` a `format="markdown"` en el XML resultante.
"""

AI_INSTRUCTIONS = r"""
# Instrucciones para LLM: Procesamiento con IA
1. **Modo Improve**: Mejora la gramática y precisión pedagógica sin alterar la estructura GIFT fundamental.
2. **Modo Multiply**: Crea variaciones que evalúen el mismo objetivo de aprendizaje pero con diferentes contextos o distractores.
3. **Salida Pura**: Devuelve únicamente el código GIFT, sin preámbulos ni explicaciones adicionales.
4. **GIFT y XML**: `ai` acepta ambos formatos; el modelo siempre recibe GIFT compacto (sin comentarios, categorías ni marcas `·`/`↵`, código en ASCII entre ``` o `...`) y la respuesta se aplica sobre el archivo original. `--dry-run` muestra el prompt sin llamar a la API.
5. **Clasificación** (`--mode classify`, con Jev de TypeSafe): agrega a cada pregunta `// [bloom:Bn-nivel] [dificultad-enunciado:x/5] [dificultad-respuestas:y/5] [clasificacion:…]`; no edites esa línea a mano (se reemplaza con `--reclasificar`). Las correcciones docentes (`--revisar`) quedan con clasificador `manual` y no se pisan; `--calibrar referencias.csv` mide la concordancia con una clasificación de referencia.
6. **Modos parciales**: `--mode feedback` completa sólo la retroalimentación que falta y `--mode distractors` agrega distractores hasta `--opciones`; en ambos el resto de la pregunta queda exactamente como estaba. Devolvé la pregunta completa en GIFT, con lo agregado.
7. **Proveedor y costo**: Gemini o Claude (`--proveedor`); antes de llamar se estima el costo (`--precio-entrada`, `--precio-salida`) y las respuestas quedan en caché (`--sin-cache` la desactiva).
"""

FIX_INSTRUCTIONS = r"""
# Instrucciones para LLM: Correcciones y Renombrado
1. **Indentación en Código**: En bloques de código (```), usa `·` por cada espacio de indentación (`····` = 4 espacios) y `↵` al final de cada línea salvo la última; vale igual para GIFT y XML.
2. **Slugificación**: Usa `fix slugify` para normalizar nombres de archivos a minúsculas y sin acentos.
3. **Sincronización de Nombres**:
   - `fix name-from-title`: Sincroniza el nombre del archivo con el título interno `::Título::`.
   - `fix title-from-name`: Actualiza el título interno `::Título::` basándose en el nombre del archivo.
   - `fix extension`: Renombra `.xml` ↔ `.gift` cuando el contenido es del otro formato (el resto de los comandos deduce el formato por la extensión). Corrélo antes que los demás en un banco heredado.
4. **Caracteres Especiales**: Convierte caracteres críticos a fullwidth dentro de bloques de código (`fix code-chars --to-fullwidth`, en GIFT y XML). Referencia: docs/caracteres_especiales.md.
5. **Lenguaje y formato del código**: `fix code-lang` etiqueta los bloques ``` sin lenguaje (C o Java) y `fix code-format` los formatea con clang-format (LLVM, sangría de 4).
6. **Simulá primero**: todos los subcomandos aceptan `-n/--dry-run`.
"""

GENERAL_INSTRUCTIONS = r"""
# Instrucciones Generales para LLM (Questions CLI)
- Prioriza siempre el formato GIFT por su legibilidad sobre el XML.
- Usa el CLI para validar cada cambio antes de dar por finalizada una tarea.
- Mantén la consistencia en el etiquetado (`// [tag:nombre]`) e identificadores (`// [id:id]`).
- `-r` es el flag para procesamiento recursivo en directorios, asegúrate de usarlo cuando trabajes con múltiples archivos.
"""

SPLIT_INSTRUCTIONS = r"""
# Instrucciones para LLM: Dividir Archivos GIFT
1. **Un solo archivo por pregunta**: El repositorio sigue la política de una pregunta por archivo. Usa `split` para desglosar bancos masivos.
2. **Nombres automáticos**: El comando usará el título `::Título::` para nombrar el nuevo archivo. Asegúrate de que los títulos sean descriptivos y únicos.
3. **Consistencia**: Al dividir, se mantiene el contenido exacto de cada bloque. Verifica que cada bloque resultante sea una pregunta GIFT válida e independiente.
"""

UNIFY_INSTRUCTIONS = r"""
# Instrucciones para LLM: Unificar Árboles y Colecciones de Preguntas
1. **Opuesto a Split / Tree Export**: Recopila múltiples archivos individuales o directorios con preguntas en un solo archivo monolítico (.gift o .xml).
2. **Preservación de Categorías**: Deduce las categorías de la estructura de subdirectorios o directivas `$CATEGORY` / `<question type="category">` existentes.
3. **Soporte Biformato**: Funciona transparentemente para GIFT y Moodle XML deduciendo el formato por la extensión de salida o mediante `-f/--format`.
"""

DEDUP_INSTRUCTIONS = r"""
# Instrucciones para LLM: Eliminar Duplicados
1. **Simulá primero**: `dedup` sin `--aplicar` sólo muestra los grupos; revisalos antes de eliminar.
2. **Umbral**: `-s` (0–1, por defecto 0.95). Más bajo encuentra más duplicados y más falsos positivos; usá `analyze similar -s` para explorar.
3. **Qué se conserva**: de cada grupo, la pregunta más completa (feedback, título, opciones) o la primera (`--conservar primera`). Sólo se comparan preguntas del mismo tipo.
4. **Efecto**: en GIFT se quita el bloque (las `$CATEGORY` quedan), en XML el `<question>` con sus comentarios; un archivo sin preguntas se borra.
5. **Deshacer**: `--aplicar` guarda una copia de los originales en `dedup-respaldos/`; `dedup --restaurar ultimo` los devuelve sin pisar archivos editados después.
6. **Casos dudosos**: con umbrales bajos usá `--confirmar-jev`, que descarta los pares que no evalúan exactamente lo mismo; `--desde origin/main` informa sólo los duplicados de lo que cambió.
"""

VERIFY_INSTRUCTIONS = r"""
# Instrucciones para LLM: Verificar el Código de las Preguntas
1. **Qué hace**: `verify` compila y ejecuta el código C (gcc) y Java (javac) de las preguntas que piden la salida de un programa y compara lo que imprime con la respuesta correcta.
2. **Problemas**: `coincide_distractor` (la clave está mal: la salida es la de un distractor), `no_compila`, `error_ejecucion`, `tiempo` y `comportamiento_indefinido` (con `--sanitizar`). `revisar` no es un problema: pide una lectura humana (salida en prosa, archivos o entrada estándar, fragmentos).
3. **Al escribir preguntas de salida**: el programa debe ser completo y determinista (sin entrada del usuario, sin comportamiento indefinido) y la correcta debe ser exactamente lo que imprime.
4. **Estilo**: `--estilo` aplica las reglas de la cátedra al código C (ripley).
"""

MOODLE_INSTRUCTIONS = r"""
# Instrucciones para LLM: Subir a Moodle
1. **Requisito**: el sitio necesita el plugin `local_questions_importer_ws` y un token con permiso para importar preguntas en el curso.
2. **Probar primero**: `moodle subir preguntas/ --url … --curso N --dry-run` prepara el Moodle XML sin contactar al sitio; usá un curso de prueba antes del real.
3. **Categorías**: las carpetas del árbol se vuelven categorías del banco del curso.
"""

def get_instructions(command_name):
    mapping = {
        'validate': VALIDATE_INSTRUCTIONS,
        'analyze': VALIDATE_INSTRUCTIONS,
        'health': VALIDATE_INSTRUCTIONS,
        'format': FORMAT_INSTRUCTIONS,
        'xml': XML_INSTRUCTIONS,
        'convert': CONVERT_INSTRUCTIONS,
        'ai': AI_INSTRUCTIONS,
        'fix': FIX_INSTRUCTIONS,
        'split': SPLIT_INSTRUCTIONS,
        'dedup': DEDUP_INSTRUCTIONS,
        'verify': VERIFY_INSTRUCTIONS,
        'moodle': MOODLE_INSTRUCTIONS,
        'unify': UNIFY_INSTRUCTIONS,
    }
    return mapping.get(command_name, GENERAL_INSTRUCTIONS)
