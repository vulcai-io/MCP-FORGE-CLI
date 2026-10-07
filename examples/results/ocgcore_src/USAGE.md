# Guide d'utilisation — ocgcore_src

Ce serveur MCP a été généré par **[mcp-forge](https://mcp-forge.vulcai.io)**.
Il expose 189 outil(s) via le protocole MCP (Model Context Protocol).

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
    "ocgcore_src": {
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
claude mcp add ocgcore_src \
  --transport sse \
  --url "http://localhost:8000/sse" \
  --header "Authorization: Bearer <votre_clé_api>"
```

Ou ajoutez manuellement dans `.claude/settings.json` :

```json
{
  "mcpServers": {
    "ocgcore_src": {
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

### `compare_effect_sort_id`

Compare two effects by their sort IDs to determine ordering. Use this for sorting effect collections or determining effect precedence.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `e1` | `str` | ✅ | Pointer to the first effect object (const effect*) |
| `e2` | `str` | ✅ | Pointer to the second effect object (const effect*) |

### `check_ocgcore_lua_api`

Validate OCGCore Lua API state and report errors. Use this when initializing or verifying Lua API compatibility.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (void*) |
| `error_message` | `str` | ✅ | Error message to report if validation fails (const char*) |

### `increment_stack_top`

Increment the Lua stack top pointer. Use this to reserve space on the Lua stack for new values.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer |

### `emit_lua_code`

Emit a Lua instruction to the function code stream. Use this during Lua code generation to add compiled instructions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Function state pointer (FuncState*) |
| `i` | `str` | ✅ | Lua instruction to emit (Instruction) |

### `emit_lua_code_abx`

Emit a Lua instruction with ABx format (opcode and two operands). Use this during code generation for instructions requiring register and large constant operands.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Function state pointer (FuncState*) |
| `o` | `str` | ✅ | Operation code to emit (OpCode) |
| `a` | `int` | ✅ | Register operand A (0-255) |
| `bx` | `int` | ✅ | Large constant operand Bx (0-262143) |

### `emit_lua_code_abck`

Emit a Lua bytecode instruction with ABC operands and a constant flag. Use when generating code for operations requiring three operands plus a constant qualifier.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; represents the current function compilation state |
| `o` | `str` | ✅ | OpCode enum value; the Lua bytecode operation to emit |
| `a` | `int` | ✅ | Register A operand (0-255); typically the destination register |
| `b` | `int` | ✅ | Register or constant B operand (0-511); source or auxiliary value |
| `c` | `int` | ✅ | Register or constant C operand (0-511); source or auxiliary value |
| `k` | `int` | ✅ | Constant flag (0 or 1); indicates if B and/or C operands reference constant table |

### `convert_expression_to_constant`

Convert a Lua expression descriptor into a compile-time constant value. Use when optimizing constant folding or resolving compile-time known values during code generation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; represents the current function compilation state |
| `e` | `str` | ✅ | Expression descriptor pointer (const expdesc); the expression to evaluate |
| `v` | `str` | ✅ | TValue pointer; output location for the constant value result |

### `fix_instruction_line`

Associate a line number with the most recently emitted instruction for debugging information. Use when generating code that requires accurate source line tracking.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; represents the current function compilation state |
| `line` | `int` | ✅ | Source code line number to attach to the current instruction |

### `emit_nil_initialization`

Generate bytecode to initialize a range of registers to nil. Use when initializing local variables or clearing register ranges in control flow.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; represents the current function compilation state |
| `from_` | `int` | ✅ | Starting register index (0-based); first register to initialize |
| `n` | `int` | ✅ | Count of consecutive registers to initialize; must be positive |

### `reserve_registers`

Reserve stack registers for temporary values during code generation. Use when allocating space for intermediate computation results or function arguments.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; represents the current function compilation state |
| `n` | `int` | ✅ | Number of registers to reserve; must be non-negative |

### `check_stack`

Verify and allocate stack space in a Lua function compilation context. Use this when you need to ensure sufficient stack capacity before emitting code.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `n` | `int` | ✅ | Number of stack slots to reserve (non-negative integer) |

### `emit_int`

Emit a Lua integer constant into a register during code generation. Use this to load an integer value into a specific register in the compiled function.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `reg` | `int` | ✅ | Target register index where the integer value will be stored |
| `n` | `int` | ✅ | Lua integer value to emit into the register |

### `discharge_vars`

Discharge pending variable assignments and convert expression state into executable code. Use this to finalize variable operations before proceeding with other code generation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `e` | `str` | ✅ | Expression descriptor pointer containing the variable state to be discharged |

### `convert_expr_to_register`

Convert an expression into any available register and return the register index. Use this when you need expression results in a register for further computation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `e` | `str` | ✅ | Expression descriptor pointer containing the expression to convert |

### `convert_expr_to_registerup`

Convert an expression into a register or upvalue and discharge the result. Use this when an expression result needs to be stored in a register or closure upvalue.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `e` | `str` | ✅ | Expression descriptor pointer containing the expression to convert |

### `emit_expression_to_register`

Emit code to convert an expression into the next available register. Use this when you need to materialize an expression result into a register for further operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Pointer to FuncState structure containing compilation state |
| `e` | `str` | ✅ | Pointer to expdesc structure representing the expression to convert |

### `emit_expression_to_value`

Emit code to convert an expression into a concrete value. Use this when an expression needs to be evaluated to a single value for use in operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Pointer to FuncState structure containing compilation state |
| `e` | `str` | ✅ | Pointer to expdesc structure representing the expression to convert |

### `emit_self_indexing`

Emit code for self-indexing operation (method call syntax). Use this when compiling object method calls with implicit self parameter.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Pointer to FuncState structure containing compilation state |
| `e` | `str` | ✅ | Pointer to expdesc structure representing the object expression |
| `key` | `str` | ✅ | Pointer to expdesc structure representing the method key |

### `emit_indexed_access`

Emit code for table indexing operation. Use this when compiling indexed table access expressions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Pointer to FuncState structure containing compilation state |
| `t` | `str` | ✅ | Pointer to expdesc structure representing the table expression |
| `k` | `str` | ✅ | Pointer to expdesc structure representing the index expression |

### `emit_conditional_jump_true`

Emit a conditional jump instruction that branches when expression evaluates to true. Use this when compiling boolean conditions in control flow.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Pointer to FuncState structure containing compilation state |
| `e` | `str` | ✅ | Pointer to expdesc structure representing the condition expression |

### `emit_lua_code_goiffalse`

Emit conditional jump bytecode when a boolean expression evaluates to false. Use this during code generation to handle false-branch control flow in Lua conditionals.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `e` | `str` | ✅ | expdesc pointer containing the expression descriptor to evaluate |

### `emit_lua_code_storevar`

Generate bytecode to store an expression value into a variable. Use this when assigning expression results to variables during code generation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `var` | `str` | ✅ | expdesc pointer describing the target variable location |
| `e` | `str` | ✅ | expdesc pointer containing the expression value to store |

### `emit_lua_code_setreturns`

Configure return value handling for an expression in the bytecode. Use this to specify how many values a function call or expression should return.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `e` | `str` | ✅ | expdesc pointer describing the expression with return values |
| `nresults` | `int` | ✅ | Number of return values expected (non-negative integer) |

### `emit_lua_code_setoneret`

Configure an expression to return exactly one value in the bytecode. Use this to enforce single-value semantics for expressions in contexts requiring exactly one result.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `e` | `str` | ✅ | expdesc pointer describing the expression to be single-valued |

### `emit_lua_code_jump`

Emit an unconditional jump instruction and return its position in the bytecode. Use this to create jump offsets for later patching in control flow structures.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |

### `emit_function_return`

Emit a return statement in the function being compiled. Use when finalizing a function to generate bytecode for returning values from the specified register.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; the compilation state of the current function |
| `first` | `int` | ✅ | Register index where return values start (0-based) |
| `nret` | `int` | ✅ | Number of return values to emit; -1 means all remaining values |

### `patch_jump_list`

Patch a list of jump instructions to target a specific bytecode address. Use when resolving forward jumps in control flow structures.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; the compilation state of the current function |
| `list` | `int` | ✅ | Head of the jump list to patch (instruction index); -1 indicates empty list |
| `target` | `int` | ✅ | Target bytecode address (instruction index) for all jumps in the list |

### `patch_jumps_here`

Patch a list of jump instructions to target the current code position. Use to resolve jumps when control flow reaches a specific point in compilation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; the compilation state of the current function |
| `list` | `int` | ✅ | Head of the jump list to patch (instruction index); -1 indicates empty list |

### `concat_jump_lists`

Concatenate two jump instruction lists into one. Use to merge multiple conditional branches or control flow paths during compilation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; the compilation state of the current function |
| `l2` | `int` | ✅ | Second jump list to concatenate (instruction index); will be appended to the first list |

### `get_code_label`

Get the current bytecode instruction index as a label. Use to mark positions in code for later jump patching and control flow resolution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer; the compilation state of the current function |

### `emit_prefix_operator`

Emit code for a unary prefix operator during expression compilation. Use when processing prefix operations like negation or logical NOT in Lua code.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `op` | `str` | ✅ | UnOpr operator type (e.g., OPR_NOT, OPR_MINUS, OPR_LEN, OPR_BNOT) |
| `v` | `str` | ✅ | expdesc pointer to the expression descriptor for the operand |
| `line` | `int` | ✅ | Source code line number for error reporting |

### `emit_infix_operator`

Process the infix operator and left operand during binary expression compilation. Use when encountering binary operators like +, -, *, / between two expressions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `op` | `str` | ✅ | BinOpr binary operator type (e.g., OPR_ADD, OPR_SUB, OPR_EQ, OPR_AND) |
| `v` | `str` | ✅ | expdesc pointer to the left operand expression descriptor |

### `emit_posfix_operator`

Emit code for a completed binary operation after right operand is processed. Use after both operands of a binary expression have been compiled to finalize the operation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `op` | `str` | ✅ | BinOpr binary operator type (e.g., OPR_ADD, OPR_SUB, OPR_EQ, OPR_AND) |
| `v1` | `str` | ✅ | expdesc pointer to the left operand expression descriptor |
| `v2` | `str` | ✅ | expdesc pointer to the right operand expression descriptor |
| `line` | `int` | ✅ | Source code line number for error reporting |

### `emit_table_size`

Emit code to set table size fields for array and hash portions. Use when finalizing table construction bytecode to specify the final table dimensions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `pc` | `int` | ✅ | Program counter (bytecode instruction index) to patch |
| `ra` | `int` | ✅ | Register index where table is allocated |
| `asize` | `int` | ✅ | Array portion size (number of sequential elements) |
| `hsize` | `int` | ✅ | Hash portion size (number of non-sequential key-value pairs) |

### `emit_list_elements`

Emit code to populate table list elements during table construction. Use when compiling table literal syntax to store multiple elements into a table in one operation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |
| `base` | `int` | ✅ | Register index of the table being constructed |
| `nelems` | `int` | ✅ | Total number of elements in the list |
| `tostore` | `int` | ✅ | Number of elements remaining to be stored in this operation |

### `emit_lua_finish`

Finalize code generation for a Lua function. Call this after all function body code has been emitted to complete function compilation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | FuncState pointer representing the current function compilation state |

### `emit_lua_semerror`

Report a semantic error during Lua parsing. Use when encountering invalid syntax or semantic violations that cannot be recovered.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ls` | `str` | ✅ | LexState pointer representing the current lexer/parser state |
| `msg` | `str` | ✅ | Error message text describing the semantic error |

### `check_lua_funcline`

Retrieve the source line number for a Lua function at a given program counter offset. Use to map bytecode positions back to source code locations for debugging or error reporting.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `f` | `str` | ✅ | Proto pointer to the Lua function prototype |
| `pc` | `int` | ✅ | Program counter offset (bytecode instruction index) |

### `emit_lua_typeerror`

Raise a type error exception during Lua execution. Use when a value has an unexpected type for the requested operation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua execution state |
| `o` | `str` | ✅ | TValue pointer to the value with incorrect type |
| `opname` | `str` | ✅ | Operation name (e.g., 'add', 'index') that triggered the type error |

### `emit_lua_callerror`

Raise a call error exception during Lua execution. Use when attempting to call a non-callable value.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua execution state |
| `o` | `str` | ✅ | TValue pointer to the value that is not callable |

### `emit_forerror`

Throw a Lua error for invalid operand types in operations. Use when an operation receives an operand that does not support that operation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `o` | `str` | ✅ | Operand value causing the error (const TValue *) |
| `what` | `str` | ✅ | Operation name or description (const char *) |

### `emit_concaterror`

Throw a Lua error for invalid concatenation operands. Use when string concatenation is attempted with non-string/non-number values.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `p2` | `str` | ✅ | Second operand value (const TValue *) |

### `emit_opinterror`

Throw a Lua error for invalid operands in binary operations. Use when a binary operation cannot be performed on the given operand types.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `p2` | `str` | ✅ | Second operand value (const TValue *) |
| `msg` | `str` | ✅ | Error message or operation identifier (const char *) |

### `emit_tointerror`

Throw a Lua error when converting operands to integers fails. Use when an operation requires integer conversion but receives incompatible types.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `p2` | `str` | ✅ | Second operand value (const TValue *) |

### `emit_ordererror`

Throw a Lua error for invalid comparison operands. Use when comparison operations (<, >, <=, >=) are attempted on incompatible types.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `p2` | `str` | ✅ | Second operand value (const TValue *) |

### `emit_lua_runerror`

Emit a runtime error in Lua with a formatted message. Use this to signal fatal errors during Lua execution that cannot be recovered.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `fmt` | `str` | ✅ | Format string for the error message (printf-style format, const char *) |

### `emit_lua_errormsg`

Emit the current error message from the Lua stack. Use this to propagate error information stored in the Lua state to the caller.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `check_lua_traceexec`

Check and execute Lua instruction tracing. Use this during VM execution to trigger debug hooks when tracing is enabled.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `pc` | `str` | ✅ | Pointer to current instruction (const Instruction *) |

### `check_lua_tracecall`

Check and execute Lua function call tracing. Use this when a function is called to trigger debug hooks if tracing is enabled.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `check_lua_stackaux`

Check and adjust Lua stack space with auxiliary operations. Use this to ensure sufficient stack space is available before operations that may grow the stack.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `n` | `str` | ✅ | Number of stack slots to reserve (integer count) |
| `p` | `int` | ✅ | Stack position saved for restoration (ptrdiff_t offset) |

### `emit_lua_error`

Trigger a fatal error in the Lua state. Use this when an unrecoverable error condition is detected and execution must terminate immediately.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `set_lua_error_object`

Set an error object on the Lua stack at a specific position. Use this to configure error information before propagating exceptions in protected contexts.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `errcode` | `int` | ✅ | Error code identifier (int) |
| `oldtop` | `str` | ✅ | Stack position to place error object (StkId) |

### `parse_lua_code_protected`

Parse Lua code from an input stream within a protected error handling context. Use this to safely compile untrusted code without crashing the Lua state on syntax errors.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `z` | `str` | ✅ | Input stream pointer (ZIO *) |
| `name` | `str` | ✅ | Chunk name for debug information (const char *) |
| `mode` | `str` | ✅ | Parse mode: 'b' for binary, 't' for text, 'bt' for both (const char *) |

### `emit_lua_hook`

Invoke a debug hook callback for a specific execution event. Use this to notify debug subscribers of VM events like line transitions or function calls.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `event` | `int` | ✅ | Hook event type identifier (int, e.g., LUA_HOOKCALL, LUA_HOOKLINE) |
| `line` | `int` | ✅ | Source line number for line-based events (int) |
| `ftransfer` | `int` | ✅ | Number of function return values being transferred (int) |
| `ntransfer` | `int` | ✅ | Number of stack slots involved in transfer (int) |

### `emit_lua_hook_call`

Trigger a call hook for the current function invocation. Use this to notify debuggers when a Lua function is about to execute.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `ci` | `str` | ✅ | Call information structure for the current invocation (CallInfo *) |

### `call_pretailcall`

Prepare and execute a tail call in the Lua VM by setting up the call context before the actual tail call occurs.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `ci` | `str` | ✅ | Current call info structure (CallInfo *) |
| `func` | `str` | ✅ | Stack ID of the function to call (StkId) |
| `narg1` | `int` | ✅ | Number of arguments plus one (int) |
| `delta` | `int` | ✅ | Stack offset adjustment for tail call (int) |

### `call_function`

Execute a Lua function on the stack and return the specified number of results. Use this for regular function calls that may yield.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `func` | `str` | ✅ | Stack ID of the function to call (StkId) |
| `nresults` | `int` | ✅ | Number of expected results from the function call (int) |

### `call_function_noyield`

Execute a Lua function without allowing yields or coroutine suspension. Use this for non-yieldable function calls in protected contexts.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `func` | `str` | ✅ | Stack ID of the function to call (StkId) |
| `nresults` | `int` | ✅ | Number of expected results from the function call (int) |

### `call_close_protected`

Close protected resources at a given stack level and propagate the error status. Use this to ensure cleanup occurs safely during exception handling.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `level` | `int` | ✅ | Stack level to close resources from (ptrdiff_t) |
| `status` | `int` | ✅ | Error status code to propagate (int) |

### `call_protected`

Execute a function in a protected context that catches errors and prevents VM crashes. Use this for calling potentially unsafe Lua code with error recovery.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `func` | `str` | ✅ | Protected function pointer to execute (Pfunc) |
| `u` | `str` | ✅ | User data pointer passed to the function (void *) |
| `oldtop` | `int` | ✅ | Previous stack top position for cleanup (ptrdiff_t) |
| `ef` | `int` | ✅ | Error function stack index (ptrdiff_t) |

### `handle_poscall`

Handle the return from a Lua function call by processing return values and updating the call stack state. Use this after a function execution completes to properly manage stack positions and return value counts.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *). The Lua execution context to operate on. |
| `ci` | `str` | ✅ | Call info pointer (CallInfo *). Metadata about the current function call being completed. |
| `nres` | `int` | ✅ | Number of return values (int). Count of values returned from the function call. |

### `reallocate_stack`

Reallocate the Lua stack to a new size. Use this to expand or contract the execution stack when the current size is insufficient or wasteful.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *). The Lua execution context to operate on. |
| `newsize` | `int` | ✅ | New stack size in slots (int). Target capacity for the reallocated stack. |
| `raiseerror` | `int` | ✅ | Error handling flag (int). Non-zero to raise an error on allocation failure, zero to fail silently. |

### `expand_stack`

Grow the Lua stack by the specified number of slots. Use this when the stack needs immediate expansion to accommodate additional values during execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *). The Lua execution context to operate on. |
| `n` | `int` | ✅ | Number of additional slots to allocate (int). Growth increment for the stack. |
| `raiseerror` | `int` | ✅ | Error handling flag (int). Non-zero to raise an error on allocation failure, zero to fail silently. |

### `shrink_stack`

Reduce the Lua stack size to reclaim unused memory. Use this during garbage collection or when the stack has excess capacity that can be freed.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *). The Lua execution context to operate on. |

### `increment_stack_top_2`

Increment the top-of-stack pointer by one position. Use this to allocate a new slot on the stack for pushing values.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *). The Lua execution context to operate on. |

### `throw_lua_error`

Throw a Lua error with the specified error code. Use when you need to signal an exception condition in the Lua execution state.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `errcode` | `int` | ✅ | Error code identifying the exception type |

### `execute_lua_protected`

Execute a protected Lua function with error handling. Use when you need to run a function safely without propagating exceptions directly.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `f` | `str` | ✅ | Function pointer to execute (Pfunc type) |
| `ud` | `str` | ✅ | User data pointer passed to the function (void *) |

### `initialize_closure_upvals`

Initialize upvalues for a Lua closure. Use when creating a new closure to set up its captured variables from the current scope.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `cl` | `str` | ✅ | Closure object pointer (LClosure *) |

### `create_tbc_upval`

Create a new to-be-closed upvalue at the given stack level. Use when an upvalue needs to be marked for finalization when it goes out of scope.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `level` | `str` | ✅ | Stack position for the upvalue (StkId type) |

### `close_upval`

Close an upvalue at the specified stack level. Use when an upvalue goes out of scope and needs to be finalized.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `level` | `str` | ✅ | Stack position of the upvalue to close (StkId type) |

### `close_lua_stack`

Close upvalues and resources up to a given stack level in a Lua state. Use when cleaning up stack frames or handling exceptions in Lua execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `level` | `str` | ✅ | Stack index to close up to (StkId) |
| `status` | `int` | ✅ | Status code indicating execution result (0 for success, non-zero for error) |
| `yy` | `int` | ✅ | Additional status or yield flag |

### `unlink_upvalue`

Unlink an upvalue from the Lua GC system. Use when removing upvalue references during garbage collection or function closure cleanup.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `uv` | `str` | ✅ | Upvalue pointer to unlink (UpVal *) |

### `free_proto`

Free a Lua function prototype and its associated resources. Use during garbage collection or when unloading compiled Lua code.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `f` | `str` | ✅ | Function prototype to free (Proto *) |

### `check_memory_change`

Verify memory state change between pre and post states under given Lua context. Use for memory validation and debugging allocation issues.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer context |
| `pre` | `str` | ✅ | Memory state before operation |
| `pos` | `str` | ✅ | Memory state after operation |

### `fix_gc_object`

Mark a GC object as fixed to prevent garbage collection. Use to protect critical objects from being collected during Lua execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `o` | `str` | ✅ | GC object to fix (GCObject *) |

### `free_lua_objects`

Free all garbage-collected objects in a Lua state. Use this to perform complete cleanup and release all memory associated with a Lua VM instance.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `step_lua_gc`

Execute one incremental garbage collection step. Use this to perform garbage collection in small increments rather than blocking full collection cycles.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `run_lua_gc_until_state`

Run the garbage collector until reaching a specific state. Use this to advance the GC to a particular phase (mark, sweep, finalize, etc.) defined by the state mask.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `statesmask` | `int` | ✅ | Bitmask defining target GC state(s) to reach |

### `run_lua_fullgc`

Execute a complete garbage collection cycle on the Lua state. Use this for thorough cleanup, optionally in emergency mode to reclaim all possible memory.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `isemergency` | `int` | ✅ | Flag (0 or 1) indicating whether to run in emergency mode for aggressive memory reclamation |

### `check_lua_gc_barrier`

Check and update the write barrier for garbage collection. Use this when assigning a GC object to another GC object to maintain correctness of incremental collection.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `o` | `str` | ✅ | Parent GC object being written to (GCObject *) |
| `v` | `str` | ✅ | Child GC object being assigned (GCObject *) |

### `check_barrierback`

Check and update the write barrier for a garbage-collected object in the Lua state. Use this when an object is being written to and needs barrier protection to maintain GC invariants.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua execution state |
| `o` | `str` | ✅ | GCObject pointer to the garbage-collected object requiring barrier update |

### `check_finalizer`

Check if a garbage-collected object has a finalizer metamethod and register it if needed. Use this when an object is assigned a metatable to ensure finalizers are properly tracked.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua execution state |
| `o` | `str` | ✅ | GCObject pointer to the object being checked for finalization |
| `mt` | `str` | ✅ | Table pointer to the metatable being assigned to the object |

### `change_gc_mode`

Change the garbage collection mode of the Lua state. Use this to switch between different GC strategies (incremental, generational, etc.) during runtime.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua execution state |
| `newmode` | `int` | ✅ | Integer flag specifying the new garbage collection mode |

### `fetch_vm_instruction`

Fetch the next virtual machine instruction in the execution loop. Use this internally during VM bytecode interpretation to advance to the next opcode.

### `initialize_lexer`

Initialize the lexical scanner for a Lua state. Use this to prepare the lexer subsystem when setting up a new Lua environment.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua execution state to initialize |

### `initialize_lexer_input`

Initialize lexer input state with a source file or string. Use this to set up the lexical analyzer before tokenizing Lua code.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `ls` | `str` | ✅ | Lexer state pointer (LexState *) to initialize |
| `z` | `str` | ✅ | Input stream pointer (ZIO *) for reading source |
| `source` | `str` | ✅ | Source name identifier (TString *), typically filename or chunk name |
| `firstchar` | `int` | ✅ | First character to process; initial byte value for lexer input |

### `advance_lexer_token`

Advance lexer to the next token in the input stream. Use this during tokenization to move through Lua source code.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ls` | `str` | ✅ | Lexer state pointer (LexState *) to advance |

### `check_lexer_lookahead`

Peek at the next token without advancing the lexer position. Use this for lookahead parsing when making context-dependent tokenization decisions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ls` | `str` | ✅ | Lexer state pointer (LexState *) to peek from |

### `emit_syntax_error`

Raise a syntax error at the current lexer position. Use this to report parsing failures with contextual information about the error location.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ls` | `str` | ✅ | Lexer state pointer (LexState *) indicating error location |
| `s` | `str` | ✅ | Error message text (const char *) describing the syntax problem |

### `check_thread_yield`

Check if the current thread should yield control. Use this in tight loops to allow Lua coroutines to pause execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) to check for yield condition |

### `check_memory_toobig`

Raise a memory allocation error when a requested allocation exceeds the Lua VM's memory limits. Call when memory size validation fails.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `free_memory_block`

Deallocate a memory block previously allocated by the Lua memory manager. Call during garbage collection or when releasing resources.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `block` | `str` | ✅ | Pointer to memory block to deallocate (void *) |
| `osize` | `int` | ✅ | Original size of the memory block in bytes (size_t) |

### `check_liveness`

Verify that a Lua object is still alive and has not been garbage collected. Call before accessing object references.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `io1` | `str` | ✅ | Object reference to validate (GCObject *) |

### `encode_utf8_escape`

Encode a Unicode codepoint as a UTF-8 escape sequence into a buffer. Call when converting Unicode values to UTF-8 representation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `buff` | `str` | ✅ | Buffer pointer to write UTF-8 escape sequence (char *) |
| `x` | `int` | ✅ | Unicode codepoint value to encode (unsigned long) |

### `compute_ceillog2`

Calculate the ceiling of the logarithm base 2 of an unsigned integer. Call when determining hash table sizes or power-of-2 allocations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `x` | `int` | ✅ | Unsigned integer value (unsigned int) |

### `compute_raw_arithmetic`

Perform a raw arithmetic operation on two Lua values and store the result. Use when you need to execute arithmetic operations (add, subtract, multiply, etc.) at the Lua VM level with type coercion.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `op` | `int` | ✅ | Arithmetic operation code (int): operation type identifier |
| `p1` | `str` | ✅ | First operand as TValue pointer (const TValue *) |
| `p2` | `str` | ✅ | Second operand as TValue pointer (const TValue *) |
| `res` | `str` | ✅ | Result storage as TValue pointer (TValue *) |

### `compute_arithmetic`

Perform an arithmetic operation on two Lua values and push the result onto the stack. Use when you need to execute arithmetic operations and store results on the Lua stack.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `op` | `int` | ✅ | Arithmetic operation code (int): operation type identifier |
| `p1` | `str` | ✅ | First operand as TValue pointer (const TValue *) |
| `p2` | `str` | ✅ | Second operand as TValue pointer (const TValue *) |
| `res` | `str` | ✅ | Stack position for result (StkId) |

### `convert_string_to_number`

Convert a string representation to a numeric Lua value. Use when you need to parse a string into a number and store it in a TValue.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `s` | `str` | ✅ | String to convert (const char *) |
| `o` | `str` | ✅ | TValue pointer to store the numeric result (TValue *) |

### `convert_hexadecimal_digit`

Convert a single hexadecimal character to its numeric value. Use when parsing hexadecimal literals or performing hex-to-decimal conversion.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `c` | `int` | ✅ | Hexadecimal digit character code (int, typically ASCII value 0-9, a-f, A-F) |

### `convert_value_to_string`

Convert a Lua value to its string representation on the stack. Use when you need to coerce a TValue to a string in the Lua state.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `obj` | `str` | ✅ | TValue pointer to convert to string (TValue *) |

### `format_chunk_id`

Format a Lua chunk identifier string. Use this to generate a human-readable chunk name from source code metadata, typically for debug output or error messages.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `out` | `str` | ✅ | Output buffer to store the formatted chunk identifier (char *) |
| `source` | `str` | ✅ | Source code identifier or filename (const char *) |
| `srclen` | `int` | ✅ | Length of the source string in bytes (size_t) |

### `get_varstack_count`

Retrieve the number of variables currently on the stack in a Lua function state. Use this to query the current variable stack depth during compilation or analysis.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `fs` | `str` | ✅ | Pointer to the function compilation state (FuncState *) |

### `set_memory_debt`

Set the memory debt value for garbage collection in the Lua global state. Use this to adjust memory pressure tracking and trigger collection cycles when needed.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `g` | `str` | ✅ | Pointer to the global Lua state (global_State *) |
| `debt` | `int` | ✅ | Memory debt value to set (l_mem) |

### `free_thread`

Free and deallocate a Lua thread state. Use this to properly clean up a child thread and release its resources within the parent thread context.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Pointer to the parent Lua state context (lua_State *) |
| `l1` | `str` | ✅ | Pointer to the thread to be freed (lua_State *) |

### `shrink_call_info`

Shrink the call information stack to reduce memory usage. Use this during garbage collection or state cleanup to reclaim unused call stack capacity.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Pointer to the Lua state (lua_State *) |

### `check_cstack`

Check the C stack of a Lua state for overflow conditions. Use this to validate that the C stack has sufficient space before performing operations that require stack allocation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `increment_cstack`

Increment the C stack counter for a Lua state. Use this when entering a function boundary that requires tracking of C stack depth.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `emit_warning`

Emit a warning message for a Lua state. Use this to report non-fatal issues during execution while optionally continuing the message.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `msg` | `str` | ✅ | Warning message text (const char *) |
| `tocont` | `int` | ✅ | Flag indicating whether the warning continues (non-zero) or is complete (0) |

### `emit_warning_error`

Emit a warning with error context information for a Lua state. Use this to report warnings with location details about where the error occurred.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `where` | `str` | ✅ | Location or context string describing where the warning originated (const char *) |

### `reset_thread`

Reset a Lua thread to a specified status state. Use this to restore a thread to a clean state after an error or to reinitialize thread execution context.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `status` | `int` | ✅ | Status code to reset the thread to (int, typically 0 for success or error code) |

### `compute_hash_string`

Compute a hash value for a string using a seed. Use when you need to hash a raw character buffer for string interning or table lookups in Lua.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `str` | `str` | ✅ | Character buffer to hash |
| `l` | `int` | ✅ | Length of the string buffer in bytes |
| `seed` | `int` | ✅ | Seed value for hash computation (unsigned integer) |

### `compute_hash_longstr`

Compute a hash value for a long Lua string object. Use when you need to hash an existing TString structure for table operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ts` | `str` | ✅ | TString pointer referencing the Lua string object to hash |

### `compare_longstr_equality`

Compare two long Lua string objects for equality. Use when you need to check if two TString objects are the same string.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `a` | `str` | ✅ | First TString pointer to compare |
| `b` | `str` | ✅ | Second TString pointer to compare |

### `resize_stringtable`

Resize the Lua string interning table to a new size. Use when you need to adjust the string table capacity for performance optimization.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer referencing the Lua state |
| `newsize` | `int` | ✅ | New size for the string table (positive integer) |

### `clear_stringcache`

Clear the string cache in the global state. Use when you need to flush cached string references for memory management or after significant state changes.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `g` | `str` | ✅ | global_State pointer referencing the global Lua state |

### `initialize_lua_strings`

Initialize the Lua string table for a given Lua state. Use this when setting up a new Lua environment to prepare string interning and management.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `remove_lua_string`

Remove an interned string from the Lua string table. Use this to deallocate a specific string and free its memory in the string pool.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `ts` | `str` | ✅ | String to remove from the table (TString *) |

### `set_lua_table_int`

Set an integer-keyed value in a Lua table. Use this to assign a value to a table entry indexed by a numeric key.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Target table pointer (Table *) |
| `key` | `int` | ✅ | Integer key for the table entry (lua_Integer) |
| `value` | `str` | ✅ | Value to set in the table (TValue *) |

### `set_lua_table`

Set a generic-keyed value in a Lua table. Use this to assign a value to a table entry with a non-integer key (string, table, etc).

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Target table pointer (Table *) |
| `key` | `str` | ✅ | Key value for the table entry (const TValue *) |
| `value` | `str` | ✅ | Value to set in the table (TValue *) |

### `finish_lua_table_set`

Finalize a table value assignment after locating its slot. Use this to complete a deferred table assignment operation with a known slot reference.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Target table pointer (Table *) |
| `key` | `str` | ✅ | Key value for the table entry (const TValue *) |
| `slot` | `str` | ✅ | Pre-located slot reference in the table (const TValue *) |
| `value` | `str` | ✅ | Value to assign to the slot (TValue *) |

### `resize_lua_table`

Resize a Lua table's array and hash parts to specified sizes. Use when you need to adjust table capacity for both array and hash components.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Table pointer (Table *) to resize |
| `nasize` | `int` | ✅ | New array size (unsigned int, number of array elements) |
| `nhsize` | `int` | ✅ | New hash size (unsigned int, number of hash buckets) |

### `resize_lua_table_array`

Resize only the array part of a Lua table. Use when you need to adjust array capacity without affecting the hash part.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Table pointer (Table *) to resize |
| `nasize` | `int` | ✅ | New array size (unsigned int, number of array elements) |

### `free_lua_table`

Deallocate memory for a Lua table. Use when you need to free a table and its associated data structures.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Table pointer (Table *) to free |

### `get_lua_table_next`

Retrieve the next key-value pair from a Lua table during iteration. Use when traversing table contents sequentially.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t` | `str` | ✅ | Table pointer (Table *) to iterate |
| `key` | `str` | ✅ | Stack index (StkId) of the current key for iteration |

### `get_lua_table_length`

Get the length of a Lua table's array part. Use when you need to determine the number of sequential elements.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `t` | `str` | ✅ | Table pointer (Table *) to query |

### `check_table_real_size`

Get the real allocated size of a Lua table. Use this to inspect memory allocation details of a table object for debugging or optimization purposes.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `t` | `str` | ✅ | Pointer to a Lua Table object (const Table *) |

### `check_memory`

Validate memory integrity of a Lua state. Use this during debugging to detect memory corruption or inconsistencies in the Lua virtual machine.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `emit_lua_object`

Print or output a Lua garbage-collected object for inspection. Use this for debugging to visualize the contents and properties of GC-managed objects.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `o` | `str` | ✅ | Pointer to a garbage-collected object (struct GCObject *) |

### `emit_tests_library`

Register and open the Lua test library for the given state. Use this to enable built-in testing utilities and debug functions in a Lua environment.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `emit_required_library`

Require and load a Lua library or module by name. Use this to dynamically import libraries into a Lua state during initialization or runtime.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `luab_opentests` | `str` | ✅ | Library name or module identifier to require (string) |

### `pop_lua_stack`

Remove and discard the top element from the Lua stack. Use this when you need to clean up stack values after operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `initialize_lua_tags`

Initialize Lua tag system for metamethod and type handling. Call this once during Lua state setup to enable tag-based operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |

### `call_lua_metamethod`

Invoke a Lua metamethod with three operands. Use this to execute operator overloads or special object behaviors defined in metatables.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `f` | `str` | ✅ | Metamethod function pointer (const TValue *) |
| `p1` | `str` | ✅ | First operand value pointer (const TValue *) |
| `p2` | `str` | ✅ | Second operand value pointer (const TValue *) |
| `p3` | `str` | ✅ | Third operand value pointer (const TValue *) |

### `call_lua_metamethod_result`

Invoke a Lua metamethod with three operands and store the result on the stack. Use this when you need the metamethod's return value for further processing.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `f` | `str` | ✅ | Metamethod function pointer (const TValue *) |
| `p1` | `str` | ✅ | First operand value pointer (const TValue *) |
| `p2` | `str` | ✅ | Second operand value pointer (const TValue *) |
| `p3` | `str` | ✅ | Stack position for result storage (StkId) |

### `call_lua_binary_metamethod`

Attempt to invoke a binary operator metamethod between two values. Use this to handle arithmetic or comparison operations with custom object behavior.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `p1` | `str` | ✅ | First operand value pointer (const TValue *) |
| `p2` | `str` | ✅ | Second operand value pointer (const TValue *) |
| `res` | `str` | ✅ | Stack position for result storage (StkId) |
| `event` | `str` | ✅ | Metamethod event identifier (TMS), e.g., add, sub, mul |

### `call_concat_metamethod`

Invoke the concatenation metamethod (__concat) for Lua values. Use when handling concatenation operations that require metamethod resolution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state context (lua_State *) |

### `call_binary_associative_metamethod`

Invoke a binary associative metamethod (__add, __mul, __pow, etc.) on two Lua values. Use when executing binary operations that support metamethod dispatch and operator precedence.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state context (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `p2` | `str` | ✅ | Second operand value (const TValue *) |
| `inv` | `int` | ✅ | Inversion flag: 0 for normal order, non-zero to attempt reverse operand order |
| `res` | `str` | ✅ | Stack location for result storage (StkId) |
| `event` | `str` | ✅ | Metamethod event type identifier (TMS) |

### `call_binary_integer_metamethod`

Invoke a binary metamethod between a Lua value and an integer. Use for optimized integer-value operations avoiding full TValue allocation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state context (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `i2` | `int` | ✅ | Second operand as integer (lua_Integer) |
| `inv` | `int` | ✅ | Inversion flag: 0 for normal order, non-zero to attempt reverse operand order |
| `res` | `str` | ✅ | Stack location for result storage (StkId) |
| `event` | `str` | ✅ | Metamethod event type identifier (TMS) |

### `call_ordering_metamethod`

Invoke an ordering metamethod (__lt, __le, etc.) to compare two Lua values. Use for relational operations requiring metamethod resolution, returns comparison result.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state context (lua_State *) |
| `p1` | `str` | ✅ | First value to compare (const TValue *) |
| `p2` | `str` | ✅ | Second value to compare (const TValue *) |
| `event` | `str` | ✅ | Ordering metamethod event type identifier (TMS) |

### `call_ordering_integer_metamethod`

Invoke an ordering metamethod between a Lua value and an integer. Use for optimized integer comparisons with metamethod dispatch.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state context (lua_State *) |
| `p1` | `str` | ✅ | First operand value (const TValue *) |
| `v2` | `int` | ✅ | Second operand as integer value |
| `inv` | `int` | ✅ | Inversion flag: 0 for normal order, non-zero to reverse operand order |
| `isfloat` | `int` | ✅ | Float flag: non-zero if second operand should be treated as floating-point |
| `event` | `str` | ✅ | Ordering metamethod event type identifier (TMS) |

### `adjust_varargs`

Adjust variable arguments in a Lua function call. Use when preparing varargs parameters for a function with fixed parameters before execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `nfixparams` | `int` | ✅ | Number of fixed parameters in the function |
| `ci` | `str` | ✅ | Call information structure pointer (struct CallInfo *) |
| `p` | `str` | ✅ | Function prototype pointer (const Proto *) |

### `get_varargs`

Retrieve variable arguments from a function call. Use when extracting varargs values into the Lua stack for a specific number of wanted arguments.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `ci` | `str` | ✅ | Call information structure pointer (struct CallInfo *) |
| `where` | `str` | ✅ | Target stack location for varargs (StkId) |
| `wanted` | `int` | ✅ | Number of varargs values to retrieve |

### `undump_lua_code`

Deserialize compiled Lua bytecode from a binary stream. Use when loading pre-compiled Lua chunks from persistent storage or binary data.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `z` | `str` | ✅ | Input stream pointer for reading bytecode (ZIO *) |
| `name` | `str` | ✅ | Chunk name for debugging and error messages (const char *) |

### `dump_lua_code`

Serialize compiled Lua bytecode to binary format. Use when saving compiled Lua functions or chunks for caching or distribution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `f` | `str` | ✅ | Function prototype to serialize (const Proto *) |
| `w` | `str` | ✅ | Custom writer function for output (lua_Writer) |
| `data` | `str` | ✅ | User data pointer passed to writer function (void *) |
| `strip` | `int` | ✅ | Strip debug information flag (non-zero to strip) |

### `check_values_equal`

Compare two Lua values for equality. Use when determining if two TValue objects are equal according to Lua semantics.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `t1` | `str` | ✅ | First value to compare (const TValue *) |
| `t2` | `str` | ✅ | Second value to compare (const TValue *) |

### `compare_lua_lessthan`

Compare two Lua values to determine if the left operand is strictly less than the right operand. Use this to evaluate Lua's less-than comparison operator with proper type coercion.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `r` | `str` | ✅ | Right operand as Lua value pointer (const TValue *) |

### `compare_lua_lessequal`

Compare two Lua values to determine if the left operand is less than or equal to the right operand. Use this to evaluate Lua's less-than-or-equal comparison operator with proper type coercion.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `r` | `str` | ✅ | Right operand as Lua value pointer (const TValue *) |

### `convert_lua_tonumber`

Convert a Lua value to a floating-point number with automatic type coercion. Use this when you need to extract or validate a numeric value from a Lua object.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `obj` | `str` | ✅ | Source Lua value pointer (const TValue *) |
| `n` | `str` | ✅ | Output pointer to store converted number (lua_Number *) |

### `convert_lua_tointeger`

Convert a Lua value to an integer with specified rounding mode. Use this when you need strict integer conversion with control over truncation or rounding behavior.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `obj` | `str` | ✅ | Source Lua value pointer (const TValue *) |
| `p` | `str` | ✅ | Output pointer to store converted integer (lua_Integer *) |
| `mode` | `str` | ✅ | Rounding mode for float-to-integer conversion (F2Imod enum) |

### `convert_lua_tointegerns`

Convert a Lua value to an integer without string coercion, using specified rounding mode. Use this for stricter integer conversion that rejects string operands.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `obj` | `str` | ✅ | Source Lua value pointer (const TValue *) |
| `p` | `str` | ✅ | Output pointer to store converted integer (lua_Integer *) |
| `mode` | `str` | ✅ | Rounding mode for float-to-integer conversion (F2Imod enum) |

### `convert_float_to_integer`

Convert a floating-point number to an integer using a specified rounding mode. Use this when you need to cast Lua numbers to integers with control over rounding behavior (floor, ceil, truncate).

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `n` | `float` | ✅ | Floating-point number (lua_Number) to convert |
| `p` | `int` | ✅ | Pointer to lua_Integer output variable where the converted result is stored |
| `mode` | `str` | ✅ | Rounding mode (F2Imod): 'floor', 'ceil', or 'truncate' |

### `finish_table_get`

Complete a table value retrieval operation, handling metamethods and complex lookup scenarios. Use this to finalize __index metamethod calls and resolve table element access.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state (lua_State *) context for the operation |
| `t` | `str` | ✅ | Target table value (const TValue *) being indexed |
| `key` | `str` | ✅ | Key value (TValue *) used for table lookup |
| `val` | `str` | ✅ | Stack slot (StkId) where the retrieved value is placed |
| `slot` | `str` | ✅ | Cached table slot (const TValue *) for optimization |

### `finish_table_set`

Complete a table value assignment operation, handling metamethods and complex assignment scenarios. Use this to finalize __newindex metamethod calls and resolve table element assignment.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state (lua_State *) context for the operation |
| `t` | `str` | ✅ | Target table value (const TValue *) being assigned to |
| `key` | `str` | ✅ | Key value (TValue *) for table assignment |
| `val` | `str` | ✅ | Value (TValue *) to assign to the table |
| `slot` | `str` | ✅ | Cached table slot (const TValue *) for optimization |

### `finish_operation`

Complete execution of a VM operation, handling any pending side effects or metamethod calls. Use this to finalize complex operations that span multiple VM cycles.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state (lua_State *) context for operation completion |

### `execute_vm_bytecode`

Execute Lua bytecode instructions for a function call. Use this to run the main VM instruction loop for a specific function activation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state (lua_State *) managing execution |
| `ci` | `str` | ✅ | Call information (CallInfo *) for the current function frame |

### `concat_lua_stack`

Concatenate multiple values on the Lua stack into a single string. Use when you need to combine stack elements into a concatenated result.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `total` | `int` | ✅ | Number of stack elements to concatenate |

### `compute_lua_idiv`

Perform integer division on two Lua integers. Use when you need floor division with proper Lua semantics.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `x` | `int` | ✅ | Dividend (lua_Integer) |
| `y` | `int` | ✅ | Divisor (lua_Integer) |

### `compute_lua_mod`

Compute the modulo operation on two Lua integers. Use when you need the remainder of integer division with Lua semantics.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `x` | `int` | ✅ | Dividend (lua_Integer) |
| `y` | `int` | ✅ | Divisor (lua_Integer) |

### `compute_lua_modf`

Compute the floating-point modulo operation on two Lua numbers. Use when you need remainder with floating-point precision.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `x` | `float` | ✅ | Dividend (lua_Number) |
| `y` | `float` | ✅ | Divisor (lua_Number) |

### `compute_lua_shiftl`

Perform bitwise left shift on a Lua integer. Use when you need to shift bits to the left by a specified amount.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `x` | `int` | ✅ | Value to shift (lua_Integer) |
| `y` | `int` | ✅ | Shift amount (lua_Integer) |

### `get_object_length`

Calculate the length of a Lua object using the '#' operator. Use this when you need to determine the size of a table, string, or other object type in a Lua state.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `ra` | `str` | ✅ | Stack index for the result (StkId) |
| `rb` | `str` | ✅ | Pointer to the value to measure (const TValue *) |

### `initialize_input_stream`

Initialize a Lua input stream (ZIO) with a reader function and associated data. Use this to set up buffered input for parsing Lua code or chunks.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State *) |
| `z` | `str` | ✅ | Input stream structure to initialize (ZIO *) |
| `reader` | `str` | ✅ | Reader function callback (lua_Reader) |
| `data` | `str` | ✅ | User-supplied opaque data passed to reader function (void *) |

### `read_input_stream`

Read bytes from a Lua input stream (ZIO) into a buffer. Use this to consume data from an initialized input stream.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `z` | `str` | ✅ | Input stream pointer (ZIO *) |
| `b` | `str` | ✅ | Destination buffer pointer (void *) |
| `n` | `int` | ✅ | Number of bytes to read (size_t) |

### `fill_input_buffer`

Refill the internal buffer of a Lua input stream. Use this to retrieve the next chunk of data from the underlying reader function.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `z` | `str` | ✅ | Input stream pointer (ZIO *) |

### `get_ocgcore_version`

Retrieve the version information of the OCG core library. Use this to check the current OCG core version.

### `create_duel`

Initialize a new OCG duel instance with specified options. Call this first to set up a duel before adding cards or starting gameplay.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `out_ocg_duel` | `str` | ✅ | Output pointer to OCG_Duel structure that will hold the duel instance |
| `options_ptr` | `str` | ✅ | Pointer to OCG_DuelOptions structure containing duel configuration settings |

### `destroy_duel`

Terminate and clean up an OCG duel instance. Call this when finished with a duel to free resources.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | OCG_Duel instance to destroy |

### `add_duel_card`

Add a new card to an active duel with specified properties. Call this to populate player decks before starting the duel.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | OCG_Duel instance to add the card to |
| `info_ptr` | `str` | ✅ | Pointer to OCG_NewCardInfo structure containing card details and zone information |

### `start_duel`

Begin gameplay on an initialized duel. Call this after setup is complete to transition from configuration to active duel state.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | OCG_Duel instance to start |

### `process_duel`

Advance duel state and retrieve pending events or decisions. Call this repeatedly during duel to handle game logic and player interactions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | OCG_Duel instance to process |

### `get_duel_message`

Retrieve the next pending message or action from an active duel. Use this to process duel state updates and determine required player actions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | Duel instance identifier (OCG_Duel handle) |

### `set_duel_response`

Submit a player response or action to an active duel. Use this to process player decisions and advance the duel state.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | Duel instance identifier (OCG_Duel handle) |
| `buffer` | `str` | ✅ | Binary response data buffer containing encoded action or decision |
| `length` | `int` | ✅ | Size of the response buffer in bytes (uint32_t) |

### `load_duel_script`

Load and compile Lua script code into a duel instance for card effects and rules. Use this to initialize duel scripting environment with card logic.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | Duel instance identifier (OCG_Duel handle) |
| `buffer` | `str` | ✅ | Lua script source code to compile and load |
| `length` | `int` | ✅ | Length of the script buffer in bytes (uint32_t) |
| `name` | `str` | ✅ | Identifier or filename for the loaded script |

### `query_duel_count`

Count cards in a specific location and team within a duel. Use this to query the number of cards in zones like hand, field, or graveyard.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | Duel instance identifier (OCG_Duel handle) |
| `team` | `int` | ✅ | Team/player index (0 or 1 typically, uint8_t) |
| `loc` | `int` | ✅ | Card location/zone identifier as bitmask (uint32_t, e.g., hand, field, graveyard) |

### `query_duel_info`

Retrieve detailed information about specific cards or zones in a duel. Use this to fetch card attributes, positions, and game state details.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | Duel instance identifier (OCG_Duel handle) |
| `info_ptr` | `str` | ✅ | Query parameters structure containing card/zone filters (OCG_QueryInfo pointer) |

### `query_duel_location`

Query location information from an OCG duel instance. Use this when you need to retrieve spatial or positional data about cards or game elements within a duel.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | OCG_Duel handle representing the active duel instance |
| `info_ptr` | `str` | ✅ | Pointer to OCG_QueryInfo structure containing query parameters |

### `query_duel_field`

Query the field state of an OCG duel instance. Use this when you need to retrieve information about the current game field, zones, or card positions.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ocg_duel` | `str` | ✅ | OCG_Duel handle representing the active duel instance |

### `push_card_lib`

Push the card library into a Lua runtime environment. Use this to initialize card-related functions and data structures in a Lua state for card queries and operations.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua runtime environment |

### `push_effect_lib`

Push the effect library into a Lua runtime environment. Use this to initialize effect-related functions and data structures in a Lua state for effect handling and execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua runtime environment |

### `push_group_lib`

Push the group library into a Lua runtime environment. Use this to initialize group-related functions and data structures in a Lua state for card group manipulation.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | lua_State pointer representing the Lua runtime environment |

### `push_duel_lib`

Push the duel library onto the Lua stack to expose duel-related functions and data structures to Lua code.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) representing the Lua execution environment |

### `push_debug_lib`

Push the debug library onto the Lua stack to enable debugging utilities and introspection functions in Lua.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) representing the Lua execution environment |

### `check_action_permission`

Verify whether the current action is permitted under game rules and player authorization constraints.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) representing the Lua execution environment |

### `push_return_cards`

Push card return operation results onto the Lua stack and return the continuation status for resuming Lua execution.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) representing the Lua execution environment |
| `status` | `int` | ✅ | Status code (int32_t) indicating the result of the card return operation |
| `ctx` | `str` | ✅ | Lua continuation context (lua_KContext) for resuming execution in C-to-Lua calls |

### `is_deleted_object`

Check whether the object referenced on the Lua stack has been deleted or is no longer valid.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) representing the Lua execution environment |

### `check_param_count`

Validate that the Lua stack has the expected number of parameters. Use this when a Lua function needs to enforce strict argument count requirements.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) |
| `count` | `int` | ✅ | Expected parameter count (int32_t) |

### `get_lua_type_name`

Retrieve the type name of a value at a specific stack position in Lua. Use this to inspect or validate the type of stack values for debugging or dynamic type checking.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) |
| `index` | `int` | ✅ | Stack position index (int32_t, 1-based or negative for relative indexing) |

### `get_lua_string_or_empty`

Extract a string value from the Lua stack, returning an empty string if the value is not a string. Use this for safe string retrieval without type errors.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) |
| `idx` | `int` | ✅ | Stack position index (int, 1-based or negative for relative indexing) |

### `pop_lua_stack_2`

Remove one element from the top of the Lua stack. Use this to clean up stack entries after processing values.

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `l` | `str` | ✅ | Lua state pointer (lua_State*) |

---

## 7. Pièges courants

- **0 tools générés** : fournissez l'URL de la spec OpenAPI (`/openapi.json`) plutôt que l'URL de base de l'API.
- **401 Unauthorized** : vérifiez que votre clé est bien passée (header `Authorization: Bearer <clé>` ou `?token=<clé>` dans l'URL).
- **Timeout** : les générations complexes peuvent prendre jusqu'à 2 minutes, c'est normal.

---

Généré avec ❤️ par [mcp-forge](https://mcp-forge.vulcai.io)
