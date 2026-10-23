# Validación y Formateo de Preguntas

Este documento detalla el uso de las herramientas de validación y formateo integradas en el CLI `voight`.

## 1. Validación (`voight health`)

Diseñado para asegurar la integridad estructural y el cumplimiento de las convenciones del repositorio.

### Uso
```bash
# Validar un directorio completo, con sus subdirectorios
uv run voight health ./preguntas -r

# Validar y generar un informe detallado en un archivo
uv run voight health ./preguntas -r --md informe.md

# Validación de un archivo único
uv run voight health pregunta.gift
```

### Qué valida:
- **Integridad Estructural:** Verifica que la sintaxis GIFT sea correcta mediante un parser PEG.
- **Preguntas Divididas:** Detecta si hay líneas en blanco accidentales dentro de una misma pregunta.
- **Caracteres Críticos:** Advierte sobre el uso incorrecto de dos puntos (`:`) sin escapar.
- **Duplicados:** `voight health similar` identifica preguntas con contenido idéntico o muy similar (umbral ajustable con `-s`) y `voight dedup` las elimina.

---

## 2. Formateo GIFT (`voight fix format`)

Estandariza la apariencia visual de los archivos GIFT para mejorar su legibilidad.

### Uso
```bash
# Formatear archivos (sobrescribe los originales)
uv run voight fix format ./preguntas

# Simulación (dry-run) para ver qué se cambiaría
uv run voight fix format ./preguntas --dry-run
```

### Estándar de Formato Aplicado:
1.  **Título:** En su propia línea inicial (`::Título::`).
2.  **Enunciado:** En la línea inmediatamente siguiente al título.
3.  **Bloque de Respuestas:** Las llaves `{` y `}` se sitúan en sus propias líneas.
4.  **Indentación:** Todas las respuestas se indentan con **4 espacios**.

---

## 3. Corrección de Bloques de Código (`voight fix`)

Especialmente útil para preguntas que contienen código fuente.

### Indentación de Código
```bash
# Reemplaza 4 espacios por caracteres especiales (····) dentro de bloques ```
uv run voight fix code-indent ./preguntas
```

### Conversión de Caracteres
```bash
# Convierte { } = # etc. a sus versiones fullwidth (｛ ｝ ＝ ＃) en bloques de código
uv run voight fix code-chars ./preguntas --to-fullwidth
```

---

## Guía para LLMs (Instrucciones de Contexto)

Si eres un modelo de lenguaje operando en este repositorio, sigue estas directrices:

### Para archivos GIFT
1.  **Sin Líneas en Blanco Internas:** No insertes líneas vacías entre el título, el enunciado y el bloque de respuestas `{ ... }`. En GIFT, una línea en blanco indica el fin de la pregunta.
2.  **Dos Puntos (`:`):** Nunca uses `:` dentro de enunciados o respuestas a menos que esté escapado (`\:`). Para separadores visuales, usa la versión fullwidth `：`.
3.  **Títulos:** Usa siempre la sintaxis `::Título::` al inicio.

### Flujo de Trabajo Sugerido
1. Genera la pregunta.
2. Ejecuta `uv run voight fix format <archivo>` para asegurar el estilo.
3. Ejecuta `uv run voight health <archivo>` para verificar errores estructurales.
4. Si hay errores, corrígelos y repite la validación hasta obtener `✅ Archivo válido`.
