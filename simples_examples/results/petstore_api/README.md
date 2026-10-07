# OpenAPI example

**Source:** [https://petstore3.swagger.io/api/v3/openapi.json](https://petstore3.swagger.io/api/v3/openapi.json)

**Score:** 8.5/10 (19 tools) — from mcp-forge's own quality evaluator, see `eval_report.json` in this folder.

Demonstrates OpenAPI/Swagger wrapping: tools are generated directly from the spec's paths, parameters and auth schemes, each one making a real HTTP call to the live API.

---

Manages a pet store catalog by creating, updating, and retrieving pet information through status or tag filters.

Généré par **mcp-forge**.

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
python server.py
```

## Test avec MCP Inspector

```bash
mcp dev server.py
```

## Tools disponibles (19)

### `update_pet`

Updates an existing pet in the store by ID. Use this to modify pet details such as name, category, photos, tags, or status.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `id` | `int` | yes | Unique numeric identifier of the pet to update |
| `name` | `str` | yes | Name of the pet |
| `category` | `dict` | yes | Category object containing pet classification (e.g., {"id": 1, "name": "Dogs"}) |
| `photoUrls` | `list` | yes | Array of URLs pointing to pet photos (e.g., ["https://example.com/photo1.jpg"]) |
| `tags` | `list` | yes | Array of tag objects for organizing and filtering pets (e.g., [{"id": 1, "name": "friendly"}]) |
| `status` | `str` | yes | Current status of the pet in the store (e.g., "available", "pending", "sold") |
---
### `create_pet`

Adds a new pet to the store. Use this to register a pet with its details including name, category, photos, tags, and status.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `id` | `int` | yes | Unique numeric identifier for the new pet |
| `name` | `str` | yes | Name of the pet |
| `category` | `dict` | yes | Category object containing pet classification (e.g., {"id": 1, "name": "Dogs"}) |
| `photoUrls` | `list` | yes | Array of URLs pointing to pet photos (e.g., ["https://example.com/photo1.jpg"]) |
| `tags` | `list` | yes | Array of tag objects for organizing and filtering pets (e.g., [{"id": 1, "name": "friendly"}]) |
| `status` | `str` | yes | Initial status of the pet in the store (e.g., "available", "pending", "sold") |
---
### `find_pets_by_status`

Retrieves pets filtered by status. Use this to search for pets with specific statuses (e.g., available, pending, sold) using comma-separated values.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `status` | `str` | yes | Comma-separated status values to filter by (e.g., "available,pending,sold") |
---
### `find_pets_by_tags`

Retrieves pets filtered by tags. Use this to search for pets matching one or more tags using comma-separated tag names.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `tags` | `list` | yes | Array of tag names to filter by (e.g., ["friendly", "vaccinated"]) |
---
### `get_pet_by_id`

Retrieves a single pet by its ID. Use this to fetch complete details of a specific pet.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `petId` | `int` | yes | Numeric ID of the pet to retrieve |
---
### `update_pet_with_form`

Update a pet's details using form data. Use this to modify a pet's name or status in the store.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `petId` | `int` | yes | Numeric ID of the pet to update |
| `name` | `str | None` | no | New name for the pet |
| `status` | `str | None` | no | New status for the pet (e.g., available, pending, sold) |
---
### `delete_pet`

Delete a pet from the store by ID. Use this to remove a pet record permanently.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `petId` | `int` | yes | Numeric ID of the pet to delete |
| `api_key` | `str | None` | no | API key for authentication (optional) |
---
### `upload_pet_image`

Upload an image for a pet. Use this to add or update a pet's photo in the store.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `petId` | `int` | yes | Numeric ID of the pet to associate with the image |
| `additionalMetadata` | `str | None` | no | Optional metadata describing the image |
---
### `get_inventory`

Retrieve pet inventory counts by status. Use this to see how many pets are available, pending, or sold.

---
### `create_order`

Create a new pet order in the store. Use this to place an order for one or more pets.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `id` | `int | None` | no | Numeric order ID |
| `petId` | `int | None` | no | Numeric ID of the pet being ordered |
| `quantity` | `int | None` | no | Number of pets to order |
| `shipDate` | `str | None` | no | Scheduled ship date (ISO 8601 format) |
| `status` | `str | None` | no | Order status (e.g., placed, approved, delivered) |
| `complete` | `bool | None` | no | Whether the order is complete |
---
### `get_order_by_id`

Retrieve a purchase order by its numeric ID. Use this to fetch order details when you have a specific order identifier.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `orderId` | `int` | yes | Numeric ID of the order to retrieve. Valid values are integers ≤ 5 or > 10. |
---
### `delete_order`

Delete a purchase order by its numeric ID. Use this to remove an order from the system permanently.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `orderId` | `int` | yes | Numeric ID of the order to delete. Must be less than 1000. |
---
### `create_user`

Create a new user account. Use this to register a new user with provided credentials and profile information.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `id` | `int | None` | no | Unique numeric identifier for the user. |
| `username` | `str | None` | no | Login username for the user account. |
| `firstName` | `str | None` | no | User's first name. |
| `lastName` | `str | None` | no | User's last name. |
| `email` | `str | None` | no | User's email address. |
| `password` | `str | None` | no | User's password in clear text. |
| `phone` | `str | None` | no | User's phone number. |
| `userStatus` | `int | None` | no | Numeric status code indicating the user's account status. |
---
### `create_users_with_list_input`

Create multiple users in bulk from a list. Use this to register several users at once with a single request.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `body` | `list | None` | no | Array of user objects to create. Each object should contain user properties (id, username, email, password, etc.). |
---
### `login_user`

Authenticate a user and log them into the system. Use this to validate credentials and establish a user session.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `username` | `str | None` | no | Username for authentication. |
| `password` | `str | None` | no | Password for authentication in clear text. |
---
### `logout_user`

Logs out the currently authenticated user session. Use this when you need to terminate the user's active session.

---
### `get_user_by_name`

Retrieves a user resource by username. Use this to fetch detailed user information when you have the username.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `username` | `str` | yes | The username to fetch (e.g., 'user1') |
---
### `update_user`

Updates an existing user resource. Use this to modify user details like name, email, phone, or status. Only the logged-in user can update their own profile.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `username` | `str` | yes | The username of the user to update |
| `id` | `int | None` | no | Numeric user ID |
| `firstName` | `str | None` | no | User's first name |
| `lastName` | `str | None` | no | User's last name |
| `email` | `str | None` | no | User's email address |
| `password` | `str | None` | no | User's password |
| `phone` | `str | None` | no | User's phone number |
| `userStatus` | `int | None` | no | User status code (e.g., 1 for active, 0 for inactive) |
---
### `delete_user`

Deletes a user resource by username. Use this to remove a user account from the system. Only the logged-in user can delete their own profile.

**Paramètres :**

| Nom | Type | Requis | Description |
|-----|------|--------|-------------|
| `username` | `str` | yes | The username of the user to delete |
---
