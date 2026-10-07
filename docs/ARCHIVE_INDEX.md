# Índice del Proyecto voight (antes Moodle Toolbox)

Guía rápida de navegación para todos los archivos del proyecto.

## 🎯 Inicio Rápido

**Nuevo usuario?** Empieza aquí:
1. Lee README.md - Visión general del proyecto
2. Identifica qué tipo de tarea necesitas realizar
3. Ve a la sección correspondiente más abajo

## 📂 Estructura del Proyecto

```
moodle_toolbox/
├── 📄 README.md                    # Documentación principal
├── 📄 INDEX.md                     # Este archivo - índice de navegación
│
├── 🔧 Scripts de Conversión
│   ├── convert_xml_gift.py                    # XML ↔ GIFT
│   ├── convert_code_blocks_chars.py           # Caracteres especiales
│   ├── convert_html_to_markdown.py            # HTML fullwidth → MD
│   └── convert_xml_html_to_markdown.py        # HTML normal → MD
│
├── 🔍 Scripts de Análisis
│   ├── find_similar_questions.py              # Detectar duplicados
│   └── evaluate_questions_directory.py        # Evaluación exhaustiva
│
├── 🛠️ Scripts de Mantenimiento
│   ├── ensure_cdata_in_text_blocks.py         # Wrapper CDATA
│   ├── remove_tags_from_xml.py                # Eliminar tags
│   └── rename_xml_files_by_question_name.py   # Renombrar archivos
│
└── 📚 Documentación
    ├── README_convert_xml_gift.md             # Doc: XML ↔ GIFT
    ├── README_convert_code_blocks_chars_fix.md # Doc: Chars especiales
    ├── README_scripts.md                      # Doc: Análisis
    ├── README_html_to_markdown.md             # Doc: HTML → MD
    ├── README_xml_maintenance.md              # Doc: Mantenimiento
    ├── caracteres_especiales.md               # Referencia chars
    └── DUPLICATES_ANALYSIS.md                 # Análisis duplicados
```

## 🗺️ Navegación por Tarea

### Quiero convertir entre formatos

| Desde | Hasta | Script | Documentación |
|-------|-------|--------|---------------|
| XML | GIFT | convert_xml_gift.py | README_convert_xml_gift.md |
| GIFT | XML | convert_xml_gift.py | README_convert_xml_gift.md |
| HTML | Markdown | convert_xml_html_to_markdown.py | README_html_to_markdown.md |
| HTML fullwidth | Markdown | convert_html_to_markdown.py | README_html_to_markdown.md |
| Chars normales | Fullwidth | convert_code_blocks_chars.py | README_convert_code_blocks_chars_fix.md |

### Quiero analizar mi banco de preguntas

Nota: Estas herramientas están pensadas para trabajar con repositorios en las que hay una pregunta por archivo, como lo que genera
[Reorganizer](https://github.com/INGCOM-UNRN/moodle-reorganizer)

| Objetivo | Script | Documentación |
|----------|--------|---------------|
| Encontrar duplicados en 1 archivo | find_similar_questions.py | README_scripts.md |
| Evaluar directorio completo | evaluate_questions_directory.py | README_scripts.md |
| Ver estadísticas por tipo | evaluate_questions_directory.py | README_scripts.md |
| Obtener comandos para resolver duplicados | evaluate_questions_directory.py | README_scripts.md |

### Quiero limpiar/mantener archivos XML

| Objetivo | Script | Documentación |
|----------|--------|---------------|
| Asegurar CDATA en bloques | ensure_cdata_in_text_blocks.py | [README_xml_maintenance.md](README_xml_maintenance.md#ensure_cdata_in_text_blockspy) |
| Eliminar tags | remove_tags_from_xml.py | [README_xml_maintenance.md](README_xml_maintenance.md#remove_tags_from_xmlpy) |
| Renombrar por nombre de pregunta | rename_xml_files_by_question_name.py | [README_xml_maintenance.md](README_xml_maintenance.md#rename_xml_files_by_question_namepy) |

## 📖 Documentación por Script

### Scripts de Conversión

#### convert_xml_gift.py
- **Función:** Conversión bidireccional XML ↔ GIFT
- **Doc completa:** README_convert_xml_gift.md
- **Casos de uso:** Editar preguntas en formato GIFT (más simple), conversión masiva
- **Características:** Preserva estructura de directorios, tags, feedback

#### convert_code_blocks_chars.py
- **Función:** Convierte caracteres especiales en bloques de código
- **Doc completa:** README_convert_code_blocks_chars_fix.md
- **Casos de uso:** Escapar caracteres GIFT (`{`, `}`, `=`, `#`)
- **Características:** Bidireccional, solo procesa código, no corrompe XML

#### convert_html_to_markdown.py
- **Función:** Convierte HTML fullwidth a Markdown
- **Doc completa:** README_html_to_markdown.md
- **Casos de uso:** Archivos con ＜code＞ fullwidth
- **Características:** Cambia format="html" a format="markdown"

#### convert_xml_html_to_markdown.py
- **Función:** Convierte HTML normal a Markdown (RECOMENDADO)
- **Doc completa:** README_html_to_markdown.md
- **Casos de uso:** Archivos con `<code>` HTML estándar
- **Características:** Procesa CDATA, preserva estructura

### Scripts de Análisis

#### find_similar_questions.py
- **Función:** Encuentra preguntas similares/duplicadas
- **Doc completa:** README_scripts.md
- **Casos de uso:** Detección de duplicados, análisis de similitud
- **Características:** Threshold ajustable, TF-IDF, modo verbose

#### evaluate_questions_directory.py
- **Función:** Evaluación exhaustiva de bancos de preguntas
- **Doc completa:** README_scripts.md
- **Casos de uso:** Auditoría de calidad, detección de problemas
- **Características:** Estadísticas, duplicados, comandos Meld, recomendaciones

### Scripts de Mantenimiento

#### ensure_cdata_in_text_blocks.py
- **Función:** Asegura CDATA en bloques `<text>`
- **Doc completa:** [README_xml_maintenance.md](README_xml_maintenance.md)
- **Casos de uso:** Prevenir errores XML con caracteres especiales
- **Características:** Backups, dry-run, recursivo

#### remove_tags_from_xml.py
- **Función:** Elimina sección `<tags>` de XMLs
- **Doc completa:** [README_xml_maintenance.md](README_xml_maintenance.md)
- **Casos de uso:** Reorganización de tags, limpieza
- **Características:** Backups, dry-run, recursivo

#### rename_xml_files_by_question_name.py
- **Función:** Renombra archivos por nombre de pregunta
- **Doc completa:** [README_xml_maintenance.md](README_xml_maintenance.md)
- **Casos de uso:** Organización, nombres descriptivos
- **Características:** Sanitización, manejo de colisiones, dry-run

## 🔄 Flujos de Trabajo Comunes

### 1. Crear Banco de Preguntas Nuevo

```bash
# Paso 1: Crear en GIFT (más fácil)
vim preguntas.gift

# Paso 2: Convertir a XML
./convert_xml_gift.py -i preguntas.gift -o preguntas.xml

# Paso 3: Asegurar CDATA
./ensure_cdata_in_text_blocks.py -f preguntas.xml

# Paso 4: Escapar caracteres especiales
./convert_code_blocks_chars.py -f preguntas.xml --to-fullwidth
```

**Documentación:** README.md - Flujo de Trabajo

### 2. Limpiar Banco Existente

```bash
# Paso 1: Evaluar estado
./evaluate_questions_directory.py ./banco -o informe.txt

# Paso 2: Resolver duplicados
grep "^meld" informe.txt | bash

# Paso 3: Estandarizar nombres
./rename_xml_files_by_question_name.py -d ./banco
```

**Documentación:** README.md - Mantenimiento

### 3. Convertir HTML a Markdown

```bash
# Paso 1: Convertir HTML
python3 convert_xml_html_to_markdown.py -d ./preguntas

# Paso 2: Asegurar CDATA
./ensure_cdata_in_text_blocks.py -d ./preguntas

# Paso 3: Verificar
./evaluate_questions_directory.py ./preguntas
```

**Documentación:** README_html_to_markdown.md - Flujo

### 4. Migración XML → GIFT → XML

```bash
# Paso 1: Convertir a GIFT
./convert_xml_gift.py -d ./xml_original -o ./gift --to-gift

# Paso 2: Editar
vim ./gift/**/*.gift

# Paso 3: Reconvertir a XML
./convert_xml_gift.py -d ./gift -o ./xml_nuevo --to-xml

# Paso 4: Evaluar cambios
./evaluate_questions_directory.py ./xml_nuevo -o informe.txt
```

**Documentación:** README.md - Conversión Masiva

## 🔍 Búsqueda Rápida

### Por Palabra Clave

- **XML**: convert_xml_gift.py, ensure_cdata_in_text_blocks.py, remove_tags_from_xml.py
- **GIFT**: convert_xml_gift.py, README_convert_xml_gift.md
- **HTML**: convert_html_to_markdown.py, convert_xml_html_to_markdown.py
- **Markdown**: convert_html_to_markdown.py, convert_xml_html_to_markdown.py
- **Duplicados**: find_similar_questions.py, evaluate_questions_directory.py
- **Análisis**: find_similar_questions.py, evaluate_questions_directory.py
- **Caracteres especiales**: convert_code_blocks_chars.py, [caracteres_especiales.md](caracteres_especiales.md)
- **CDATA**: ensure_cdata_in_text_blocks.py
- **Tags**: remove_tags_from_xml.py
- **Renombrar**: rename_xml_files_by_question_name.py

### Por Problema

- **"Archivos XML corruptos"** → README_convert_code_blocks_chars_fix.md
- **"Encontrar preguntas duplicadas"** → find_similar_questions.py, README_scripts.md
- **"Evaluar calidad de banco"** → evaluate_questions_directory.py, README_scripts.md
- **"Convertir HTML a Markdown"** → README_html_to_markdown.md
- **"Editar preguntas más fácilmente"** → convert_xml_gift.py, README_convert_xml_gift.md
- **"Caracteres { } = # en código"** → convert_code_blocks_chars.py
- **"Nombres de archivo descriptivos"** → rename_xml_files_by_question_name.py

## 📊 Comparación de Scripts

### ¿Qué script usar para...?

#### Convertir formatos

| Necesidad | Script Recomendado | Alternativa |
|-----------|-------------------|-------------|
| XML a GIFT | convert_xml_gift.py | - |
| GIFT a XML | convert_xml_gift.py | - |
| HTML a Markdown | convert_xml_html_to_markdown.py | convert_html_to_markdown.py (fullwidth) |

**Más info:** DUPLICATES_ANALYSIS.md

#### Analizar banco

| Necesidad | Script Recomendado | Cuándo usar |
|-----------|-------------------|-------------|
| Duplicados en 1 archivo | find_similar_questions.py | Análisis rápido |
| Análisis completo | evaluate_questions_directory.py | Auditoría exhaustiva |

**Más info:** README_scripts.md

## 🆘 Solución de Problemas

| Problema | Dónde buscar |
|----------|--------------|
| Archivos XML corruptos | README_convert_code_blocks_chars_fix.md |
| Duplicados no detectados | README_scripts.md - Troubleshooting |
| Caracteres especiales no convierten | README_convert_code_blocks_chars_fix.md |
| HTML no se convierte a Markdown | README_html_to_markdown.md - Solución de Problemas |
| Colisiones al renombrar | [README_xml_maintenance.md - Manejo de Colisiones](README_xml_maintenance.md#manejo-de-colisiones) |

**General:** README.md - Resolución de Problemas

## 📝 Notas Importantes

### Scripts con Funcionalidad Similar

- **convert_html_to_markdown.py** vs **convert_xml_html_to_markdown.py**
  - Ver análisis completo: DUPLICATES_ANALYSIS.md
  - Resumen: Uno usa fullwidth (＜＞), otro HTML normal (`<>`)

### Backups Automáticos

La mayoría de scripts crean backups `.bak` automáticamente:

```bash
# Restaurar desde backup
cp archivo.xml.bak archivo.xml

# Limpiar backups después de verificar
find . -name "*.bak" -delete
```

### Modo Dry-Run

Scripts de mantenimiento soportan `--dry-run` para previsualizar cambios:

```bash
./script.py -d ./preguntas --dry-run  # Ver qué haría
./script.py -d ./preguntas            # Aplicar cambios
```

## 🔗 Enlaces Rápidos

- **Documentación Principal:** README.md
- **Análisis de Duplicados:** DUPLICATES_ANALYSIS.md
- **Referencia de Caracteres:** [caracteres_especiales.md](caracteres_especiales.md)

## 📅 Mantenimiento del Índice

Este índice debe actualizarse cuando:
- ✅ Se agregue un nuevo script
- ✅ Se cree nueva documentación
- ✅ Se deprece o elimine un script
- ✅ Se modifique significativamente la funcionalidad

---

**Última actualización:** Diciembre 2025  
**Versión del índice:** 1.0
