## Autenticación

Cada llamada va con un token personal en la cabecera `Authorization`:

```http
GET /api/v1/emitidos/ HTTP/1.1
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

El token se genera en **Mi perfil → API**. Es uno solo por usuario: al
generar uno nuevo, el anterior deja de funcionar de inmediato.

Trátalo como una contraseña. Permite entrar a la cuenta sin el código
de verificación en dos pasos, así que no debe quedar en un repositorio
ni en el código de un cliente que se distribuya.

Sin token, o con uno que no existe, la respuesta es `401`.

Todos los recursos son del contribuyente activo: no hay permisos por
usuario ni por documento, así que cualquier token válido ve lo mismo.
