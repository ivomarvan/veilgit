# Cifrado retroactivo: eliminar texto plano del historial de git

## Problema

`veil_setup.py` detectó que archivos que coinciden con tus patrones ya existen en el
historial de git como texto plano. Esto significa que cualquier persona con acceso al
repositorio puede leerlos, incluso después de configurar el cifrado.

Cifrar a partir de este momento solo protege los commits **futuros**. Para eliminar el
texto plano del historial pasado, debes reescribir el historial de git con `git filter-repo`.

> **⚠ Advertencia:** La reescritura del historial es irreversible y afecta a todos los
> colaboradores. Todos los clones existentes deben volver a clonarse después del force-push.

---

## Requisitos previos

Instala `git filter-repo`:

```bash
pip install git-filter-repo
# Alternativa para macOS:
brew install git-filter-repo
```

Verificación: `git filter-repo --version`

---

## Instrucciones paso a paso

### Paso 1 — Hacer una copia de seguridad de los archivos

Copia los archivos sensibles **fuera** del repositorio antes de que `filter-repo` los elimine:

```bash
cp -r ruta/a/sensibles/ /tmp/veilgit_backup/
```

### Paso 2 — Eliminar archivos de todo el historial de git

```bash
git filter-repo --path ruta/a/sensibles/ --invert-paths
```

Para múltiples rutas, repite `--path`:

```bash
git filter-repo \
  --path docs/private/ \
  --path secrets/ \
  --invert-paths
```

Después de este comando, los archivos desaparecen del directorio de trabajo **y** de cada
commit en el historial.

### Paso 3 — Verificar la eliminación

```bash
git log --all --oneline -- ruta/a/sensibles/
# no debe producir ninguna salida
```

### Paso 4 — Restaurar los archivos al directorio de trabajo

```bash
cp -r /tmp/veilgit_backup/ ruta/a/sensibles/
```

### Paso 5 — Reinicializar los filtros de veilgit

`git filter-repo` reinicia `.git/config`. Vuelve a registrar los filtros de veilgit:

```bash
python veil_setup.py . --reinit
```

### Paso 6 — Añadir al índice la configuración y los archivos cifrados

```bash
# Primero, añadir la configuración de veilgit
git add .gitattributes .veil/

# Añadir los archivos restaurados — el filtro clean los cifra durante git add
git add ruta/a/sensibles/

git commit -m "chore: cifrar retroactivamente archivos sensibles"
```

### Paso 7 — Force-push del historial reescrito

```bash
git push --force-with-lease origin main
```

`--force-with-lease` es más seguro que `--force`: falla si el repositorio remoto tiene
commits que no tienes localmente, evitando sobreescrituras accidentales.

### Paso 8 — Notificar a los colaboradores

Todos los clones existentes divergen después del force-push. Cada colaborador debe
volver a clonar el repositorio:

```bash
git clone <url_del_repo>
cd <repo>
bash .veil/setup_veil.sh /ruta/a/su_clave_privada.txt
```

---

## Verificar el cifrado

Después del commit, confirma que git almacena solo contenido cifrado:

```bash
git show HEAD:ruta/a/sensibles/archivo.md | xxd | head -3
# los primeros bytes deben mostrar la cabecera de cifrado age, no texto plano
```

---

## Notas sobre las cachés de GitHub

GitHub puede retener objetos en caché que referencian el historial antiguo durante un
breve período. Para máxima seguridad (p. ej., antes de hacer el repositorio público),
contacta con el [soporte de GitHub](https://support.github.com) para solicitar una purga
de caché después del force-push.

---

*Generado por veilgit. Para más información consulta el README del proyecto.*
