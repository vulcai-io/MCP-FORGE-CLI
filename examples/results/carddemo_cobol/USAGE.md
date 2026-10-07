# Guide d'utilisation — carddemo_cobol

Ce serveur MCP a été généré par **[mcp-forge](https://mcp-forge.vulcai.io)**.
Il expose 6 outil(s) via le protocole MCP (Model Context Protocol).

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
    "carddemo_cobol": {
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
claude mcp add carddemo_cobol \
  --transport sse \
  --url "http://localhost:8000/sse" \
  --header "Authorization: Bearer <votre_clé_api>"
```

Ou ajoutez manuellement dans `.claude/settings.json` :

```json
{
  "mcpServers": {
    "carddemo_cobol": {
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

### `call_cobdatft`

Call the COBDATFT external program to process date/time formatting operations. Use this when date transformation or time-related processing is required.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `codatecn_rec` | `str` | ✅ | Date/time control record (alphanumeric string, max 100 chars) |

### `call_cee3abd`

Call the CEE3ABD external program to handle abort/termination operations with code and timing parameters. Use this when conditional program termination or error handling is needed.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `abcode` | `str` | ✅ | Abort/error code (numeric string or alphanumeric identifier) |
| `timing` | `str` | ✅ | Timing indicator or delay value (numeric string in milliseconds or time unit) |

### `call_cbstm03b`

Call the CBSTM03B external program to process statement-related data. Use this when handling statement formatting or generation operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ws_m03b_area` | `str` | ✅ | Working storage area for M03B processing (structured data buffer, may contain multiple fields) |

### `call_mvswait`

Call the MVSWAIT external program to introduce a wait or delay period. Use this when synchronization, polling, or scheduled delays are required.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `mvswait_time` | `str` | ✅ | Wait duration (numeric string in seconds or milliseconds) |

### `call_csutldtc`

Call the CSUTLDTC subprogram to convert and format dates according to a specified format. Use this when date transformation or localization is needed.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `date` | `str` | ✅ | Input date value (10-character alphanumeric string, format determined by date_format parameter) |
| `date_format` | `str` | ✅ | Target date format specification (10-character alphanumeric string, e.g., 'YYYY-MM-DD') |

### `call_ceedays`

Call the CEEDAYS external program to validate and convert dates between different formats or calculate Lillian day numbers. Use this when you need to test date validity, convert date formats, or obtain Lillian calendar calculations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ws_date_to_test` | `str` | ✅ | The date string to validate or convert (format specified by ws_date_format parameter) |
| `ws_date_format` | `str` | ✅ | The format specification of the input date (e.g., 'YYYYMMDD', 'DD/MM/YYYY') |
| `output_lillian` | `str` | ✅ | Flag or format specification for Lillian day number output (e.g., 'Y' for yes, or output format code) |
| `feedback_code` | `str` | ✅ | Variable name or code reference where the operation result or status feedback will be stored |

---

## 7. Pièges courants

- **0 tools générés** : fournissez l'URL de la spec OpenAPI (`/openapi.json`) plutôt que l'URL de base de l'API.
- **401 Unauthorized** : vérifiez que votre clé est bien passée (header `Authorization: Bearer <clé>` ou `?token=<clé>` dans l'URL).
- **Timeout** : les générations complexes peuvent prendre jusqu'à 2 minutes, c'est normal.

---

Généré avec ❤️ par [mcp-forge](https://mcp-forge.vulcai.io)
