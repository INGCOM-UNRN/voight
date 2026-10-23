# Mantenimiento XML

Herramientas de limpieza y mantenimiento de archivos Moodle XML. Viven en `voight fix`
junto con el resto de las correcciones; los nombres anteriores (`voight fix xml cdata`,
`fix xml clean-tags`, `fix xml rename`) siguen funcionando con un aviso.

## Comandos Incluidos

1. [`voight fix format`](#voight-fix-format) (antes `fix xml cdata`)
2. [`voight fix clean-tags`](#voight-fix-clean-tags) (antes `fix xml clean-tags`)
3. [`voight fix name-from-title`](#voight-fix-name-from-title) (antes `fix xml rename`)

---

## `voight fix format`

### Descripción

Formatea el XML (sangría de 2 espacios) y envuelve el contenido de cada bloque `<text>`
en una sección CDATA. Esto previene problemas con caracteres especiales XML como `<`, `>`, `&`, etc.

### Uso

```bash
# Procesar un directorio recursivamente
uv run voight fix format ./preguntas -r

# Ver qué cambiaría sin escribir
uv run voight fix format ./preguntas -r --diff
```

### Ejemplo de Transformación

**Antes:**
```xml
<text>Código con operador: x &lt; 10</text>
```

**Después:**
```xml
<text><![CDATA[Código con operador: x < 10]]></text>
```

---

## `voight fix clean-tags`

### Descripción

Elimina la sección `<tags>` de todos los archivos XML de preguntas de Moodle. Útil cuando se quiere reorganizar completamente el sistema de etiquetado.

### Uso

```bash
uv run voight fix clean-tags ./preguntas -r
```

---

## `voight fix name-from-title`

### Descripción

Renombra cada archivo (GIFT o XML) usando el título de la pregunta que contiene,
slugificado para que sea un nombre de archivo válido y descriptivo.

### Reglas de Sanitización

1. **Conversión a minúsculas**: `Estructuras` → `estructuras`
2. **Eliminación de acentos**: `función` → `funcion`
3. **Espacios a guiones bajos**: `Mi Pregunta` → `mi_pregunta`
4. **Solo caracteres válidos**: Mantiene solo `a-z`, `0-9`, `_`, `-`

### Uso

```bash
uv run voight fix name-from-title ./preguntas -r -n   # simular
uv run voight fix name-from-title ./preguntas -r
```

---

## Flujo de Trabajo Recomendado

### Limpieza de Banco de Preguntas

```bash
# 1. Formato y CDATA en todos los bloques de texto
uv run voight fix format ./banco -r

# 2. Eliminar tags obsoletos
uv run voight fix clean-tags ./banco -r

# 3. Renombrar archivos descriptivamente
uv run voight fix name-from-title ./banco -r
```

---

**Relacionado:**
- [README.md](../README.md): Documentación principal
- [QUICK_START.md](./QUICK_START.md): Guía rápida
