# Guide d'utilisation — python_utils

Ce serveur MCP a été généré par **[mcp-forge](https://mcp-forge.vulcai.io)**.
Il expose 4 outil(s) via le protocole MCP (Model Context Protocol).

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
    "python_utils": {
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
claude mcp add python_utils \
  --transport sse \
  --url "http://localhost:8000/sse" \
  --header "Authorization: Bearer <votre_clé_api>"
```

Ou ajoutez manuellement dans `.claude/settings.json` :

```json
{
  "mcpServers": {
    "python_utils": {
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

### `check_prime`

Use this tool to determine if a given integer is a prime number. Returns true only if the number is greater than 1 and has no divisors other than 1 and itself.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `n` | `int` | ✅ | The integer to test for primality. |

### `compute_factorial`

Use this tool to calculate the factorial of a non-negative integer. Returns the product of all positive integers less than or equal to n.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `n` | `int` | ✅ | The non-negative integer for which to compute the factorial. |

### `reverse_string`

Use this tool to get the characters of a string in reverse order. Ideal for quickly inverting text without manual logic.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `s` | `str` | ✅ | The string to be reversed. |

### `sum_list`

Use this tool to calculate the total sum of all numeric values in a provided list. Returns the aggregate of the array's elements.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `numbers` | `list` | ✅ | An array of numeric values (integers or floating-point numbers) to be summed. |

---

## 7. Pièges courants

- **0 tools générés** : fournissez l'URL de la spec OpenAPI (`/openapi.json`) plutôt que l'URL de base de l'API.
- **401 Unauthorized** : vérifiez que votre clé est bien passée (header `Authorization: Bearer <clé>` ou `?token=<clé>` dans l'URL).
- **Timeout** : les générations complexes peuvent prendre jusqu'à 2 minutes, c'est normal.

---

Généré avec ❤️ par [mcp-forge](https://mcp-forge.vulcai.io)
