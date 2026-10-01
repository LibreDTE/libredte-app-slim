LibreDTE Slim
=============

LibreDTE es un proyecto cuyo objetivo es proveer Facturación Electrónica Libre para Chile.

Esta es una aplicación Django de facturación electrónica (DTE) para Chile. Toda la lógica de negocio y orquestación de DTE (construcción, timbrado, firma, envío al SII, renderizado) es delegada al SDK ``libredte_lib_sdk``. Esta app solo maneja la vista, autenticación y persistencia, y no reimplementa esa lógica.

Revisa el `sitio web de LibreDTE Slim <https://slim.libredte.cl>`_ para más información, características y detalles de uso.

Términos y condiciones de uso
-----------------------------

Al utilizar este proyecto, total o parcialmente, se aceptan automáticamente los `términos y condiciones de uso <https://slim.libredte.cl/legal>`_ que rigen LibreDTE. La `Licencia Pública General Affero de GNU (AGPL) <https://raw.githubusercontent.com/libredte/libredte-app-slim/master/COPYING>`_ solo aplica para quienes respeten estos términos y condiciones. No existe una licencia comercial de LibreDTE Slim, por lo tanto no es posible usar el proyecto si no aceptas cumplir los términos establecidos.

A continuación, el resumen de los términos y condiciones de uso de LibreDTE que permiten la utilización del proyecto:

#. Tienes la libertad de usar, estudiar, distribuir y modificar LibreDTE.
#. Si utilizas LibreDTE en tu software, el código fuente de ese software debe ser liberado públicamente bajo licencia AGPL.
#. Si realizas cambios a LibreDTE, debes liberar públicamente el código fuente de dichos cambios bajo licencia AGPL.
#. Debes mencionar de forma pública en tu software el proyecto y autor original de LibreDTE, tanto si usas LibreDTE sin modificar como si realizas cambios al código.

Es obligación de quienes deseen usar el proyecto leer y aceptar por completo los `términos y condiciones de uso <https://slim.libredte.cl/legal>`_.

Estructura
----------

.. code-block:: text

    libredte-slim/
    ├── apps/                 # apps Django del proyecto
    │   ├── core/             # plataforma (dashboard, perfil, Configuración)
    │   ├── libredte/         # base de la aplicación
    │   ├── public/           # páginas públicas
    │   ├── billing/          # facturación electrónica (DTE)
    │   ├── accounting/       # contabilidad
    │   └── human_resources/  # RR.HH.
    ├── config/               # configuración del proyecto (settings, urls, wsgi/asgi)
    └── manage.py

Las apps bajo ``apps/`` se importan con su ruta completa (ej.
``apps.billing``, no ``billing``).

Desarrollo
----------

.. code-block:: bash

    cp .env.example .env   # ajustar valores si hace falta (ver .env.example)
    make install-dev
    make migrate
    make seed              # catálogos SII (obligatorio, usa la API)
    make check             # ruff + mypy + tests
    make run               # runserver

Con la base vacía, ``make run`` pide crear el primer usuario y
contribuyente desde el navegador.

Datos de prueba (opcional)
~~~~~~~~~~~~~~~~~~~~~~~~~~

Solo si se necesitan datos de demostración. Reemplaza el paso
``seed`` de arriba (lo corre internamente) y crea el usuario
``demo`` / ``Slim123%`` con un contribuyente, certificado y CAF
ficticios y DTE de ejemplo. Requiere la base vacía (sin usuarios).

.. code-block:: bash

    make seed-demo

Tareas en segundo plano
~~~~~~~~~~~~~~~~~~~~~~~

La emisión masiva necesita Redis (``CELERY_BROKER_URL`` en ``.env``) y
el worker corriendo aparte.

.. code-block:: bash

    docker run -d --rm -p 6379:6379 --name slim-redis redis:7-alpine
    make worker
