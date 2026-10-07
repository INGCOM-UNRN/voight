# Mantenimiento XML

Documentación para las herramientas de limpieza y mantenimiento de archivos XML de Moodle integradas en el comando `voight xml`.

## Comandos Incluidos

1. [`voight fix xml cdata`](#voight-fix-xml-cdata)
2. [`voight fix xml clean-tags`](#voight-fix-xml-clean-tags)
3. [`voight fix xml rename`](#voight-fix-xml-rename)

---

## `voight fix xml cdata`

### Descripción

Asegura que todos los bloques `<text>` con contenido tengan su contenido envuelto en secciones CDATA. Esto previene problemas con caracteres especiales XML como `<`, `>`, `&`, etc.

### Uso

```bash
# Procesar directorio recursivamente
uv run voight fix xml cdata ./preguntas

# Procesar solo en el directorio actual (no recursivo)
uv run voight fix xml cdata ./preguntas --no-recursive
```

### Ejemplo de Transformación

**Antes:**
```xml
<text>Código con operador: x < 10</text>
```

**Después:**
```xml
<text><![CDATA[Código con operador: x < 10]]></text>
```

---

## `voight fix xml clean-tags`

### Descripción

Elimina recursivamente la sección `<tags>` de todos los archivos XML de preguntas de Moodle. Útil cuando se quiere reorganizar completamente el sistema de etiquetado.

### Uso

```bash
# Procesar directorio recursivamente
uv run voight fix xml clean-tags ./preguntas
```

---

## `voight fix xml rename`

### Descripción

Renombra archivos XML usando el nombre de la pregunta contenida en el XML. Sanitiza el nombre para crear nombres de archivo válidos y descriptivos.

### Reglas de Sanitización

1. **Conversión a minúsculas**: `Estructuras` → `estructuras`
2. **Eliminación de acentos**: `función` → `funcion`
3. **Espacios a guiones bajos**: `Mi Pregunta` → `mi_pregunta`
4. **Solo caracteres válidos**: Mantiene solo `a-z`, `0-9`, `_`, `-`

### Uso

```bash
# Renombrar todos los archivos en un directorio
uv run voight fix xml rename ./preguntas/*.xml
```

---

## Flujo de Trabajo Recomendado

### Limpieza de Banco de Preguntas

```bash
# 1. Asegurar CDATA en todos los bloques de texto
uv run voight fix xml cdata ./banco

# 2. Eliminar tags obsoletos
uv run voight fix xml clean-tags ./banco

# 3. Renombrar archivos descriptivamente
uv run voight fix xml rename ./banco/*.xml
```

---

**Relacionado:**
- [README.md](../README.md): Documentación principal
- [QUICK_START.md](./QUICK_START.md): Guía rápida
