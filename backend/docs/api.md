# SSSNL Backend API

Base URL: `http://<host>:5656`
Auth: Session-based via `/api/auth/login`. Some media endpoints accept `X-API-KEY` if `SSSNL_MEDIA_API_KEY` is set.

## Auth
- POST `/api/auth/signup`: Create user
  - Body: `{ "username": string, "password": string }`
  - 201/200: `{ ok: true, user: { username, role } }`
  - 400: `{ error: "username_password_required" }`
  - 409: `{ error: "user_exists" }`

- POST `/api/auth/login`: Login
  - Body: `{ "username": string, "password": string }`
  - 200: `{ ok: true, user: { username, role } }`
  - 401: `{ error: "invalid_credentials" }`
  - 404: `{ error: "not_found" }`

- GET `/api/auth/me`: Current user
  - 200: `{ user: { username, role } }`
  - 401: `{ error: "unauthenticated" }`

- POST `/api/auth/logout`: Logout
  - 200: `{ ok: true }`

## User
- POST `/api/user/change_password`
  - Body: `{ old_password?: string, new_password: string }`
  - 200: `{ ok: true }`
  - 401: `{ error: "unauthenticated" | "invalid_old_password" }`
  - 404: `{ error: "not_found" }`

- POST `/api/user/change_username`
  - Body: `{ new_username: string, password?: string }`
  - 200: `{ ok: true, user: { username } }`
  - 401: `{ error: "unauthenticated" }`
  - 404: `{ error: "not_found" }`, 409: `{ error: "user_exists" }`

## Admin
- GET `/api/admin/users`: List users
  - 200: `{ users: [{ id, username, role, created_at }] }`
  - 403: `{ error: "forbidden" }`

- POST `/api/admin/users`: Add user
  - Body: `{ username, password, role?: "user"|"admin" }`
  - 200: `{ ok: true }`, 409: `{ error: "user_exists" }`, 403

- DELETE `/api/admin/users/:username`: Delete
  - 200: `{ ok: true }`, 403

- POST `/api/admin/change_password`
  - Body: `{ username, password }`
  - 200: `{ ok: true }`, 404, 403

## Media (Blueprint `/api/media`)
- POST `/api/media/upload`
  - Form fields: `file` (one or many), `target=media`, optional `device_mac`
  - Requires session or `X-API-KEY`
  - 201: `{ saved: ["/static/..."] }`

- GET `/api/media/files`
  - Query: optional `device_mac`
  - 200: `{ files: [{ name, url, type }] }`

- POST `/api/media/delete`
  - Body: `{ filename, device_mac?: string }`
  - 200: `{ deleted: filename }`, 404

- POST `/api/media/fetch`
  - Body: `{ url, target?: "media" }`
  - 201: `{ saved: ["/static/..."] }`

- GET `/api/media/info`
  - 200: `{ allowed_targets, allowed_ext }`

## Playlist & Status
- GET `/playlist`
  - Requires session
  - 200: `{ playlist: [{ type: "video"|"image", src, duration_ms? }] }`

- GET `/status`
  - 200: `{ temp, hum, motion_status, motion_active, last_dht_time, last_dht_success, last_motion_raw, last_motion_change }`

## Diagnostics & Mocks
- GET `/dht-debug`
  - 200: `{ backend, read: { temp, hum, error? }, last_dht_* }`

- POST `/mock-motion`
  - Body: `{ active: boolean }` or query `?active=true|false`
  - 200: `{ ok, motion_active, override }`

- POST `/mock-motion/clear`
  - 200: `{ ok, override, motion_active }`

- POST `/mock-dht`
  - Body: `{ temp: number, hum: number }`
  - 200: `{ ok, override, temp, hum }`

- POST `/mock-dht/clear`
  - 200: `{ ok, override }

## Flutter Web Assets
- GET `/dashboard/` (serves `sssnl_app/build/web_dashboard`)
- GET `/media/` (serves `sssnl_media_controls/build/web_media`)
- GET `/dev/` (serves `sssnl_media_controls/build/web_dev`)
