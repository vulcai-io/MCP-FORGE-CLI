# Guide d'utilisation — petstore_api

Ce serveur MCP a été généré par **[mcp-forge](https://mcp-forge.vulcai.io)**.
Il expose 19 outil(s) via le protocole MCP (Model Context Protocol).

---

## 1. Lancement local

```bash
pip install -r requirements.txt
python server.py
```

Testez avec MCP Inspector :

```bash
mcp dev server.py
```

> Sans `MCP_SERVER_TOKEN`, le serveur est ouvert (mode développement local). Définissez `MCP_SERVER_TOKEN` pour sécuriser les connexions.

---

## 2. Déploiement remote (SSE)

Pour déployer le serveur et le connecter depuis Claude.ai / Cursor :

```bash
MCP_SERVER_URL=https://mon-serveur.exemple.com \
MCP_SERVER_TOKEN=mon_secret \
BEARER_TOKEN=votre_cle_api \
python server.py
```

### Variables d'environnement

| Variable | Rôle | Quand la définir |
|----------|------|-----------------|
| `MCP_SERVER_URL` | URL publique du serveur (ex: `https://mon-serveur.com`) | Toujours en remote |
| `MCP_SERVER_TOKEN` | Mot de passe pour se connecter au serveur MCP | Toujours en remote |
| `BEARER_TOKEN` | Clé API à utiliser pour appeler l'API downstream | **Mode partagé** : une seule clé pour tous |
| `OAUTH_ALLOWED_REDIRECT_HOSTS` | Whitelist des hôtes autorisés pour `redirect_uri` OAuth (ex: `claude.ai,cursor.sh`) | **Obligatoire en production** — voir ci-dessous |

> ⚠️ **Sécurité OAuth — `OAUTH_ALLOWED_REDIRECT_HOSTS` doit être défini en production.**
>
> Sans cette variable, le serveur n'autorise que `localhost` et `127.0.0.1` comme `redirect_uri`.
> En production, définissez-la avec les hôtes exacts de vos clients MCP :
>
> ```bash
> OAUTH_ALLOWED_REDIRECT_HOSTS=claude.ai,cursor.sh,app.monentreprise.com \
> MCP_SERVER_URL=https://mon-serveur.exemple.com \
> python server.py
> ```
>
> Une `redirect_uri` non autorisée retourne HTTP 400 `invalid_request` (prévention open redirect).

> **Mode proxy** (multi-utilisateurs) : si vous ne définissez pas `BEARER_TOKEN`, chaque utilisateur devra entrer sa propre clé API lors de la connexion OAuth. Chaque appel utilisera alors sa propre clé. Utile si chacun a son propre compte sur l'API.

**Connexion OAuth (recommandé)** — sans copier-coller de token :

1. Dans Claude.ai : **Paramètres → Connecteurs → +**
2. URL : `https://mon-serveur.exemple.com/sse`
3. Cliquez **Ajouter** → une page de login s'ouvre → entrez votre `MCP_SERVER_TOKEN`

**Connexion directe par token** :

URL : `https://mon-serveur.exemple.com/sse?token=<MCP_SERVER_TOKEN>`

---

## 3. Connexion depuis Claude.ai (local)

Dans Paramètres → Connecteurs → + :
- **URL** : `http://localhost:8000/sse?token=<votre_clé_api>`

---

## 4. Connexion depuis Cursor

Ajoutez dans `~/.cursor/mcp.json` (ou `.cursor/mcp.json` à la racine du projet) :

```json
{
  "mcpServers": {
    "petstore_api": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer <votre_clé_api>"
      }
    }
  }
}
```

---

## 5. Connexion depuis Claude Code (CLI)

```bash
claude mcp add petstore_api \
  --transport sse \
  --url "http://localhost:8000/sse" \
  --header "Authorization: Bearer <votre_clé_api>"
```

Ou ajoutez manuellement dans `.claude/settings.json` :

```json
{
  "mcpServers": {
    "petstore_api": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer <votre_clé_api>"
      }
    }
  }
}
```

---

## 6. Outils disponibles

### `update_pet`

Updates an existing pet in the store by ID. Use this to modify pet details such as name, category, photos, tags, or status.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | `int` | ✅ | Unique numeric identifier of the pet to update |
| `name` | `str` | ✅ | Name of the pet |
| `category` | `dict` | ✅ | Category object containing pet classification (e.g., {"id": 1, "name": "Dogs"}) |
| `photoUrls` | `list` | ✅ | Array of URLs pointing to pet photos (e.g., ["https://example.com/photo1.jpg"]) |
| `tags` | `list` | ✅ | Array of tag objects for organizing and filtering pets (e.g., [{"id": 1, "name": "friendly"}]) |
| `status` | `str` | ✅ | Current status of the pet in the store (e.g., "available", "pending", "sold") |

### `create_pet`

Adds a new pet to the store. Use this to register a pet with its details including name, category, photos, tags, and status.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | `int` | ✅ | Unique numeric identifier for the new pet |
| `name` | `str` | ✅ | Name of the pet |
| `category` | `dict` | ✅ | Category object containing pet classification (e.g., {"id": 1, "name": "Dogs"}) |
| `photoUrls` | `list` | ✅ | Array of URLs pointing to pet photos (e.g., ["https://example.com/photo1.jpg"]) |
| `tags` | `list` | ✅ | Array of tag objects for organizing and filtering pets (e.g., [{"id": 1, "name": "friendly"}]) |
| `status` | `str` | ✅ | Initial status of the pet in the store (e.g., "available", "pending", "sold") |

### `find_pets_by_status`

Retrieves pets filtered by status. Use this to search for pets with specific statuses (e.g., available, pending, sold) using comma-separated values.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `status` | `str` | ✅ | Comma-separated status values to filter by (e.g., "available,pending,sold") |

### `find_pets_by_tags`

Retrieves pets filtered by tags. Use this to search for pets matching one or more tags using comma-separated tag names.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `tags` | `list` | ✅ | Array of tag names to filter by (e.g., ["friendly", "vaccinated"]) |

### `get_pet_by_id`

Retrieves a single pet by its ID. Use this to fetch complete details of a specific pet.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `petId` | `int` | ✅ | Numeric ID of the pet to retrieve |

### `update_pet_with_form`

Update a pet's details using form data. Use this to modify a pet's name or status in the store.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `petId` | `int` | ✅ | Numeric ID of the pet to update |
| `name` | `str | None` | — | New name for the pet |
| `status` | `str | None` | — | New status for the pet (e.g., available, pending, sold) |

### `delete_pet`

Delete a pet from the store by ID. Use this to remove a pet record permanently.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `petId` | `int` | ✅ | Numeric ID of the pet to delete |
| `api_key` | `str | None` | — | API key for authentication (optional) |

### `upload_pet_image`

Upload an image for a pet. Use this to add or update a pet's photo in the store.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `petId` | `int` | ✅ | Numeric ID of the pet to associate with the image |
| `additionalMetadata` | `str | None` | — | Optional metadata describing the image |

### `get_inventory`

Retrieve pet inventory counts by status. Use this to see how many pets are available, pending, or sold.

### `create_order`

Create a new pet order in the store. Use this to place an order for one or more pets.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | `int | None` | — | Numeric order ID |
| `petId` | `int | None` | — | Numeric ID of the pet being ordered |
| `quantity` | `int | None` | — | Number of pets to order |
| `shipDate` | `str | None` | — | Scheduled ship date (ISO 8601 format) |
| `status` | `str | None` | — | Order status (e.g., placed, approved, delivered) |
| `complete` | `bool | None` | — | Whether the order is complete |

### `get_order_by_id`

Retrieve a purchase order by its numeric ID. Use this to fetch order details when you have a specific order identifier.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `orderId` | `int` | ✅ | Numeric ID of the order to retrieve. Valid values are integers ≤ 5 or > 10. |

### `delete_order`

Delete a purchase order by its numeric ID. Use this to remove an order from the system permanently.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `orderId` | `int` | ✅ | Numeric ID of the order to delete. Must be less than 1000. |

### `create_user`

Create a new user account. Use this to register a new user with provided credentials and profile information.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `id` | `int | None` | — | Unique numeric identifier for the user. |
| `username` | `str | None` | — | Login username for the user account. |
| `firstName` | `str | None` | — | User's first name. |
| `lastName` | `str | None` | — | User's last name. |
| `email` | `str | None` | — | User's email address. |
| `password` | `str | None` | — | User's password in clear text. |
| `phone` | `str | None` | — | User's phone number. |
| `userStatus` | `int | None` | — | Numeric status code indicating the user's account status. |

### `create_users_with_list_input`

Create multiple users in bulk from a list. Use this to register several users at once with a single request.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `body` | `list | None` | — | Array of user objects to create. Each object should contain user properties (id, username, email, password, etc.). |

### `login_user`

Authenticate a user and log them into the system. Use this to validate credentials and establish a user session.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `username` | `str | None` | — | Username for authentication. |
| `password` | `str | None` | — | Password for authentication in clear text. |

### `logout_user`

Logs out the currently authenticated user session. Use this when you need to terminate the user's active session.

### `get_user_by_name`

Retrieves a user resource by username. Use this to fetch detailed user information when you have the username.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `username` | `str` | ✅ | The username to fetch (e.g., 'user1') |

### `update_user`

Updates an existing user resource. Use this to modify user details like name, email, phone, or status. Only the logged-in user can update their own profile.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `username` | `str` | ✅ | The username of the user to update |
| `id` | `int | None` | — | Numeric user ID |
| `firstName` | `str | None` | — | User's first name |
| `lastName` | `str | None` | — | User's last name |
| `email` | `str | None` | — | User's email address |
| `password` | `str | None` | — | User's password |
| `phone` | `str | None` | — | User's phone number |
| `userStatus` | `int | None` | — | User status code (e.g., 1 for active, 0 for inactive) |

### `delete_user`

Deletes a user resource by username. Use this to remove a user account from the system. Only the logged-in user can delete their own profile.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `username` | `str` | ✅ | The username of the user to delete |

---

## 7. Pièges courants

- **0 tools générés** : fournissez l'URL de la spec OpenAPI (`/openapi.json`) plutôt que l'URL de base de l'API.
- **401 Unauthorized** : vérifiez que votre clé est bien passée (header `Authorization: Bearer <clé>` ou `?token=<clé>` dans l'URL).
- **Timeout** : les générations complexes peuvent prendre jusqu'à 2 minutes, c'est normal.

---

Généré avec ❤️ par [mcp-forge](https://mcp-forge.vulcai.io)
