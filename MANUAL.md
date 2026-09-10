# Manual de operación — Sistema Esencias Gama

Este archivo es para ti, Hugo, cuando algo falle y no te acuerdes de cómo se hizo.
Está pensado para leerse a las 2 de la mañana. Todo lo que dice aquí está probado.

**Datos de esta instalación** (verificados el 2026-09-09):

| Cosa | Valor |
|---|---|
| Carpeta del proyecto | `C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama` |
| Base de datos | `db.sqlite3` dentro de esa carpeta |
| Python del proyecto | `venv\Scripts\python.exe` (Python 3.10.8) |
| Respaldos | `G:\RespaldosEsenciasGama` (disco WD de 3 TB, **físicamente distinto** al SSD del sistema) |
| Registro de errores | `logs\errores.log` |
| Registro de respaldos | `logs\respaldos.log` |
| Registro del servidor | `logs\servidor.log` |
| IP de esta PC | `192.168.1.64` (por DHCP, tarjeta "Ethernet 3") |
| MAC de esa tarjeta | `40-B0-76-43-5D-40` |
| Router / puerta de enlace | `192.168.1.254` |
| Dirección que teclean los demás | `http://192.168.1.64:8000` |

> En todos los comandos de abajo, cuando veas `cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"`,
> es para pararte en la carpeta del proyecto. Sin eso, `manage.py` no se encuentra.

---

## 1. Respaldos

### Cómo funciona

El comando `respaldar_bd` deja un archivo `respaldo-AAAA-MM-DD.db` en `G:\RespaldosEsenciasGama`,
conserva los 30 más recientes y borra los anteriores.

No hace una copia normal del archivo. Usa la **API de respaldo de SQLite**, que lee la base
página por página y produce una copia coherente aunque alguien esté capturando en ese momento.
Si la base está ocupada, espera hasta 60 segundos antes de rendirse (en vez de fallar al primer
intento). Al terminar **abre el respaldo recién hecho y lo verifica** (`PRAGMA integrity_check`
más un conteo de pedidos y clientes): si el archivo no sirviera, el comando falla ruidosamente
en vez de dejarte un respaldo inútil.

### Correrlo a mano

```
cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"
venv\Scripts\python.exe manage.py respaldar_bd
```

Opciones: `--carpeta "D:\otro\lugar"` y `--conservar 60`.

### Programarlo todos los días

Abre **PowerShell como administrador** (botón Inicio → escribe `powershell` → clic derecho →
"Ejecutar como administrador") y pega esto de un jalón:

```
schtasks /create /tn "Esencias Gama - Respaldo diario" /tr "\"C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama\herramientas\respaldar.bat\"" /sc daily /st 02:00 /ru SYSTEM /rl HIGHEST /f
```

Qué significa cada parte:

- `/sc daily /st 02:00` → todos los días a las 2 de la mañana (no hay nadie capturando).
- `/ru SYSTEM` → corre con la cuenta del sistema. Esto es importante por dos razones: **no
  necesita que tú hayas iniciado sesión**, y **no te pide guardar tu contraseña** (si algún día
  cambias tu contraseña de Windows, la tarea sigue funcionando). Ya verifiqué que la cuenta
  SYSTEM tiene acceso completo tanto a la carpeta del proyecto como a `G:\`.
- `/f` → si la tarea ya existía, la reemplaza.

Después, un ajuste que sí conviene hacer a mano en la ventana gráfica: abre el **Programador de
tareas** (Inicio → `Programador de tareas`), busca la tarea, clic derecho → **Propiedades** →
pestaña **Condiciones** y en **Configuración** marca:

- **"Ejecutar la tarea lo antes posible tras un inicio programado que no se realizó"** — así, si
  la PC estaba apagada a las 2 AM, el respaldo se hace al encenderla.

### Comprobar que el respaldo corrió

```
cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"
type logs\respaldos.log
dir G:\RespaldosEsenciasGama
```

Y para ver qué le pasó a la tarea programada:

```
Get-ScheduledTaskInfo -TaskName "Esencias Gama - Respaldo diario"
```

`LastTaskResult` en **0** significa que salió bien. Cualquier otro número, revisa `logs\respaldos.log`:
si el respaldo falla, ahí queda escrita la línea `*** EL RESPALDO FALLO - revisa este archivo ***`.

### Una copia fuera de esta PC (esto no es opcional)

Tener los respaldos en `G:` te protege de que se muera el SSD. **No te protege de** un incendio,
una inundación, un robo, un rayo que queme la fuente de poder con los dos discos adentro, ni de un
ransomware que cifre todas las unidades conectadas. Los dos discos están en el mismo gabinete: lo
que le pase al gabinete les pasa a los dos.

Lo mínimo razonable, sin comprar nada ni depender de internet: **una memoria USB que vivas
llevando a tu casa.** Una vez por semana (ponle recordatorio el viernes), conéctala y corre:

```
robocopy "G:\RespaldosEsenciasGama" "E:\RespaldosEsenciasGama" /MAXAGE:8 /NDL /NP
```

Cambia `E:` por la letra que le toque a la USB. `/MAXAGE:8` copia solo lo de los últimos 8 días,
así tarda segundos. Luego desconéctala y llévatela. Una USB desconectada es inmune al ransomware.

### Cómo restaurar un respaldo

Un respaldo que no sabes restaurar no sirve de nada. Esto es a propósito **manual**: restaurar es
raro y deliberado, y no quieres un script que lo haga solo por accidente.

**Paso 1 — Detén el servidor**, para que nadie escriba mientras cambias la base. En PowerShell
como administrador:

```
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

**Paso 2 — Aparta la base actual. NO la borres.** Aunque esté dañada, puede tener datos de hoy
que el respaldo de ayer no tiene, y quizá se puedan rescatar después:

```
cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"
ren db.sqlite3 db.sqlite3.apartada-2026-09-09
```

(Pon la fecha del día.)

**Paso 3 — Copia el respaldo que quieras** y ponle el nombre que el sistema espera:

```
copy "G:\RespaldosEsenciasGama\respaldo-2026-09-08.db" db.sqlite3
```

**Paso 4 — Verifica antes de dejar entrar a nadie:**

```
venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('db.sqlite3'); print('integridad:', c.execute('PRAGMA integrity_check').fetchone()[0]); print('pedidos:', c.execute('SELECT COUNT(*) FROM core_pedido').fetchone()[0]); print('clientes:', c.execute('SELECT COUNT(*) FROM core_cliente').fetchone()[0])"
venv\Scripts\python.exe manage.py showmigrations core
```

Debe decir `integridad: ok`, y todas las migraciones deben aparecer con `[X]`.

**Paso 5 — Levanta el servidor otra vez:**

```
schtasks /run /tn "Esencias Gama - Servidor"
```

Entra a `http://localhost:8000`, revisa que se vean los pedidos, y **avisa a tus compañeras hasta
qué momento quedaron los datos** — todo lo capturado después de la fecha del respaldo se perdió y
hay que recapturarlo.

> **Ensáyalo una vez, ahorita que no urge.** Haz los pasos 1 a 5 usando el respaldo de hoy.
> Si algo no sale como dice aquí, es mucho mejor descubrirlo un martes tranquilo.

---

## 2. Arranque automático del servidor

### Cómo funciona

`herramientas\iniciar_servidor.bat` levanta el servidor y manda todo lo que imprima a
`logs\servidor.log`. La tarea programada lo corre con la cuenta SYSTEM, así que **el proceso vive
en una sesión invisible: no hay ventana negra que alguien pueda cerrar por accidente**, y arranca
antes de que nadie inicie sesión en Windows.

Las opciones del comando, por si alguna vez lo tocas:

- `0.0.0.0:8000` → acepta conexiones de las otras computadoras, no solo de esta.
- `--noreload` → un solo proceso, más fácil de detener; y no se reinicia solo al tocar archivos.
- `--insecure` → sirve el CSS y el logo aunque `DEBUG` esté en `False`.

### Programarlo al encender

PowerShell **como administrador**:

```
schtasks /create /tn "Esencias Gama - Servidor" /tr "\"C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama\herramientas\iniciar_servidor.bat\"" /sc onstart /delay 0000:30 /ru SYSTEM /rl HIGHEST /f
```

`/delay 0000:30` espera 30 segundos después del arranque, para darle tiempo a la red.

Y un ajuste en la ventana gráfica que vale mucho la pena: **Programador de tareas** → la tarea →
**Propiedades** → pestaña **Configuración**:

- Marca **"Si la tarea no se realiza correctamente, reiniciar cada:"** → `1 minuto`, **Intento de
  reinicio hasta:** `3 veces`. Si el servidor se cae solo, se vuelve a levantar.
- En **"Si la tarea ya se está ejecutando..."** deja **"No iniciar una nueva instancia"**.
- Desmarca **"Detener la tarea si se ejecuta durante más de: 3 días"**. Si no lo desmarcas,
  Windows te mata el servidor cada 3 días.

### Comprobar que está corriendo

Cualquiera de estas tres:

```
netstat -ano | findstr ":8000" | findstr LISTENING
```
```
Get-ScheduledTaskInfo -TaskName "Esencias Gama - Servidor"
```

O simplemente abre `http://localhost:8000` en el navegador de esta PC. Esa es la prueba de verdad.

### Detenerlo y reiniciarlo (para actualizar el código)

Como `--noreload` está activo, **si cambias código, el servidor no se entera hasta que lo
reinicies**. La secuencia completa, en PowerShell como administrador:

```
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"
venv\Scripts\python.exe manage.py migrate
schtasks /run /tn "Esencias Gama - Servidor"
```

(El `migrate` solo hace falta si el cambio tocó los modelos, pero correrlo de más no hace daño.)

Antes de actualizar código, **haz un respaldo manual** (`manage.py respaldar_bd`). Es un segundo y
te salva de una migración que salga mal.

---

## 3. Acceso desde las otras computadoras

### Qué quedó configurado

- `ALLOWED_HOSTS = ['*']` en `etiquetasgama\settings.py`. Con `DEBUG = False` Django exige saber
  a qué nombres responde; `'*'` acepta tanto `localhost` como la IP. Es razonable porque el
  sistema **no está publicado a internet**, solo vive en la red de la oficina.
- El servidor escucha en `0.0.0.0:8000`, o sea en todas las tarjetas de red. Ya lo probé: desde
  esta misma PC, entrando por `http://192.168.1.64:8000`, responde correctamente.

### Lo que falta: abrir el puerto en el Firewall

Windows bloquea el puerto 8000 desde afuera. Verifiqué que **no hay ninguna regla creada todavía**.

**Comando (PowerShell como administrador):**

```
netsh advfirewall firewall add rule name="Esencias Gama (8000)" dir=in action=allow protocol=TCP localport=8000 remoteip=192.168.1.0/24 profile=any
```

`remoteip=192.168.1.0/24` limita el permiso a las computadoras de la red de la oficina. No cuesta
nada y es mejor que abrirlo a todo.

**Los mismos pasos en la ventana gráfica**, si prefieres verlo:

1. Inicio → escribe `Firewall de Windows Defender con seguridad avanzada` → Enter.
2. Panel izquierdo: **Reglas de entrada**.
3. Panel derecho: **Nueva regla...**
4. Tipo de regla: **Puerto** → Siguiente.
5. **TCP**, **Puertos locales específicos**: `8000` → Siguiente.
6. **Permitir la conexión** → Siguiente.
7. Deja marcados **Dominio, Privada y Pública** → Siguiente.
8. Nombre: `Esencias Gama (8000)` → Finalizar.
9. (Recomendado) Doble clic en la regla recién creada → pestaña **Ámbito** → en **Dirección IP
   remota** elige **Estas direcciones IP** → Agregar → `192.168.1.0/24`.

**Detalle importante que encontré:** la red "Ethernet 3" está clasificada por Windows como
**Pública**, que es el perfil más restrictivo. Como es la red de tu oficina, conviene marcarla
como **Privada** (PowerShell como administrador):

```
Set-NetConnectionProfile -InterfaceAlias "Ethernet 3" -NetworkCategory Private
```

Con el `profile=any` del comando de arriba la regla funciona igual en cualquiera de los dos
perfiles, así que esto es higiene, no un requisito.

### La dirección que teclean tus compañeras

```
http://192.168.1.64:8000
```

Para volver a averiguar la IP en cualquier momento:

```
ipconfig
```

Busca el adaptador **Ethernet 3** y la línea **Dirección IPv4**.

Diles que la guarden en Favoritos. Y ojo: **es `http://`, no `https://`**, y el `:8000` no se puede
omitir.

### ¿Conviene fijar la IP? Sí

Ahorita la IP `192.168.1.64` te la da el router por DHCP. Eso significa que **puede cambiar** —
típicamente después de un apagón largo o si cambias el router de lugar. El día que cambie, el
favorito de tus compañeras deja de funcionar y no van a saber por qué.

Anotarla no basta: anotarla no evita que cambie, solo te ayuda a descubrir que ya cambió.

Tienes dos formas de fijarla. **Recomiendo la primera:**

**Opción A — Reserva DHCP en el router (la mejor).** El router sigue repartiendo IPs, pero siempre
le da la misma a esta PC. La ventaja es que si algún día cambias de router o de red, esta PC no se
queda incomunicada: simplemente vuelve a pedir una IP normal.

1. Entra a `http://192.168.1.254` desde el navegador (usuario y contraseña suelen estar en una
   etiqueta pegada al router).
2. Busca la sección **DHCP** → **Reserva de direcciones** / **Address Reservation** / **DHCP
   estático** (el nombre cambia según la marca).
3. Agrega una entrada con:
   - MAC: `40-B0-76-43-5D-40` (algunos routers la piden con dos puntos: `40:B0:76:43:5D:40`)
   - IP: `192.168.1.64`
4. Guarda y reinicia el router.

**Opción B — IP fija en Windows.** Funciona, pero si alguien más se conecta a la red y el router
le reparte esa misma IP, chocan y se caen las dos. Solo si no puedes entrar al router:

Panel de control → Redes → Cambiar configuración del adaptador → clic derecho en **Ethernet 3** →
Propiedades → **Protocolo de Internet versión 4 (TCP/IPv4)** → Propiedades → **Usar la siguiente
dirección IP**:

- Dirección IP: `192.168.1.64`
- Máscara de subred: `255.255.255.0`
- Puerta de enlace: `192.168.1.254`
- DNS preferido: `192.168.1.254`

---

## 4. Usuarios y roles

### Cómo funciona

Hay dos grupos en Django, `admin` y `user`, y el rol es simplemente a cuál grupo pertenece la
persona. La función que decide está en `core\permisos.py`:

```python
def es_admin(user):
    return user.is_superuser or user.groups.filter(name='admin').exists()
```

Lo que **puede** el rol `user`: capturar y editar pedidos, capturar resultados de laboratorio,
imprimir etiquetas y certificados, y eliminar pedidos en borrador o con resultados.

Lo que **no puede** el rol `user`: entrar a Catálogos, entrar a Calibración, entrar al admin de
Django, y cancelar pedidos ya emitidos.

**La verificación está en el servidor, no en el menú.** Las vistas `calibracion` y
`pedido_cancelar` llevan el decorador `@solo_admin`, y el admin de Django está bloqueado en
`core\admin.py` sobreescribiendo `admin.site.has_permission`. Esconder el enlace en el menú es
solo cortesía visual: aunque alguien teclee la dirección directamente, no entra.

Lo probé con los cuatro casos que existen en la práctica:

| Usuario de prueba | `/admin/` | `/calibracion/` |
|---|---|---|
| grupo `admin`, "staff" desmarcado | entra | entra |
| superusuario sin grupo | entra | entra |
| grupo `user` | bloqueado | bloqueado |
| sin ningún grupo | bloqueado | bloqueado |

Sin iniciar sesión, todo manda a la pantalla de login.

### Crear las cuentas de tus dos compañeras

Hazlo desde el navegador, entrando con tu cuenta `hughost`:

1. Ve a `http://localhost:8000/admin/`
2. **Usuarios** → botón **Añadir usuario** (arriba a la derecha).
3. Nombre de usuario y contraseña (dos veces) → **Guardar y continuar editando**.
4. En la pantalla que sigue, llena Nombre y Apellidos (opcional, pero ayuda a identificarlas).
5. **Deja DESMARCADAS** las casillas "Es staff" y "Es superusuario". No hacen falta para nada.
6. Baja hasta **Grupos**, selecciona **`user`** en la lista de la izquierda y pícale a la flecha
   para pasarlo a la derecha.
7. **Guardar**.

Repite para la segunda compañera. Para darle a alguien rol de administradora, es el mismo
procedimiento pero eligiendo el grupo **`admin`** en el paso 6.

### Cambiar una contraseña olvidada

Mismo lugar: `/admin/` → Usuarios → clic en la persona → en el campo Contraseña hay un enlace que
dice **"Cambiar la contraseña usando este formulario"**.

Si el que olvida la contraseña eres tú y no puedes entrar al admin:

```
cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"
venv\Scripts\python.exe manage.py changepassword hughost
```

### Ver quién es quién en cualquier momento

```
cd "C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama"
venv\Scripts\python.exe -c "import os,django; os.environ['DJANGO_SETTINGS_MODULE']='etiquetasgama.settings'; django.setup(); from django.contrib.auth.models import User; [print(u.username, '->', [g.name for g in u.groups.all()] or ('superusuario' if u.is_superuser else 'SIN GRUPO')) for u in User.objects.all()]"
```

---

## 5. Dónde vive el proyecto

```
C:\Users\hugoc\Desktop\Esencias Gama\EtiquetasGama
```

**Está en el Escritorio, pero NO en un Escritorio sincronizado con OneDrive.** Lo verifiqué en el
registro de Windows: la carpeta de Escritorio apunta a `C:\Users\hugoc\Desktop`, es una carpeta
real (no un vínculo a OneDrive), y OneDrive ni siquiera está corriendo. Así que hoy no hay
problema.

**Pero hay un riesgo latente, y quiero que lo tengas presente:** la carpeta
`C:\Users\hugoc\OneDrive\Desktop` **existe**. Si algún día abres OneDrive y aceptas la opción de
"hacer copia de seguridad de tus carpetas" (Escritorio, Documentos, Imágenes), Windows movería tu
Escritorio adentro de OneDrive **con el proyecto adentro**.

Por qué eso sería malo: OneDrive sube el archivo mientras el sistema lo está usando, y puede
subirlo a medias o intentar bloquearlo justo cuando SQLite necesita escribir. El resultado típico
es una base corrupta o errores de "database is locked" a media captura. Ninguna base de datos en
uso debe vivir dentro de una carpeta que se sincroniza sola.

**Qué hacer si eso llega a pasar:** mueve la carpeta del proyecto a un lugar fuera de OneDrive,
por ejemplo `C:\EsenciasGama`. Después edita la línea `set PROYECTO=` en los dos archivos de
`herramientas\` y vuelve a crear las dos tareas programadas con la ruta nueva. Nada más.

Si prefieres curarte en salud desde ahorita, mover el proyecto a `C:\EsenciasGama` elimina el
riesgo de raíz y son los mismos tres pasos.

---

## Lista de verificación

Después de hacer los pasos de arriba, comprueba en este orden:

- [ ] `venv\Scripts\python.exe manage.py respaldar_bd` termina diciendo `integridad ok`.
- [ ] Existe el archivo del día en `G:\RespaldosEsenciasGama`.
- [ ] `Get-ScheduledTaskInfo -TaskName "Esencias Gama - Respaldo diario"` existe y, al día
      siguiente, muestra `LastTaskResult: 0`.
- [ ] Reinicias la PC, **no inicias sesión**, y desde otra computadora entra
      `http://192.168.1.64:8000`. (Esta prueba sola valida el arranque automático, el firewall y
      el acceso por red de un solo golpe.)
- [ ] No hay ninguna ventana negra de consola en el escritorio.
- [ ] Entras con una cuenta de rol `user` y **no** ves "Catálogos" ni "Calibración" en el menú.
- [ ] Con esa misma cuenta tecleas `http://192.168.1.64:8000/calibracion/` a mano y te rebota a la
      lista de pedidos con un mensaje de "No tienes permiso".
- [ ] Con esa misma cuenta, un pedido emitido **no** ofrece el botón de cancelar.
- [ ] Los estilos y el logo se ven bien (o sea, `--insecure` está haciendo su trabajo).
- [ ] Ensayaste una restauración completa siguiendo los pasos de la sección 1.

---

## Si algo se cae y tú no estás

Deja esta hoja impresa junto a la PC. Lo que tus compañeras pueden hacer **sin romper nada**:

**Si nadie puede entrar al sistema:**

1. Que revisen que la PC de la oficina esté encendida. Si está apagada, encenderla y esperar dos
   minutos. **No hace falta iniciar sesión en Windows**: el sistema arranca solo.
2. Si sigue sin abrir, reiniciar esa PC y esperar dos minutos.
3. Si sigue sin abrir, que te llamen. Nada más. **Que no borren archivos, ni muevan carpetas, ni
   desinstalen nada.**

**Lo más importante que deben saber:** los datos están en `db.sqlite3` y hay un respaldo de cada
día en `G:\`. Mientras nadie borre esos archivos, no se pierde nada, por feo que se vea el error.

**Cuando llegues tú**, en este orden:

1. `type logs\errores.log` — ahí queda anotado cualquier error del sistema.
2. `type logs\servidor.log` — ahí ves si el servidor arrancó y por qué se detuvo.
3. `Get-ScheduledTaskInfo -TaskName "Esencias Gama - Servidor"` — si `LastTaskResult` no es 0, la
   tarea ni siquiera arrancó; revisa que la ruta del `.bat` siga siendo correcta.
4. Si el problema es de datos, restaura siguiendo la sección 1 — y acuérdate: **aparta la base
   dañada, no la borres.**

Si necesitas ver el detalle técnico de un error, en `etiquetasgama\settings.py` pon `DEBUG = True`
un rato, reinicia el servidor, reproduce el error, y **acuérdate de regresarlo a `False`**.
