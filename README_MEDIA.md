Media management and uploader

This project now includes a simple media content manager that saves media to `static/media` and a single-screen dashboard that plays that media when motion is detected.

API key
- A default API key has been generated and embedded in `media_uploader.py` for convenience.
- You should override it by exporting an environment variable before starting the app:

  ```bash
  export SSSNL_MEDIA_API_KEY='YOUR_STRONG_SECRET_HERE'
  ```

Default key (only for local/dev):

N7k8J3mX9sVqLp2bYfDz6wR0uT1eGh

(Replace it with your own secret for production.)

How it works
- `media_uploader.py` is a Flask blueprint mounted at `/media`.
  - POST `/media/upload` - multipart upload; default `target=media` (form field permitted); requires API key.
  - POST `/media/fetch` - fetch remote URL and save into target; requires API key.
  - GET `/media/files` - returns JSON list of files in `static/media`; requires API key.
  - POST `/media/delete` - JSON {filename, api_key} to delete a file; requires API key.
  - GET `/media/manage` - simple browser-based UI for upload/list/delete; the page will prompt you for the API key (it is not required in the URL anymore).

- `app.py` now registers the blueprint and at startup moves media from various candidate folders into `static/media` and builds a playlist from there.

Quick start
1. (optional) Set your API key to override the embedded default:

```bash
export SSSNL_MEDIA_API_KEY='a_long_random_secret'
```

2. Start the app:

```bash
python3 app.py
```

3. Open the dashboard (single-screen autoplay):

http://127.0.0.1:5000/

4. Open the media manager (browser will prompt for the API key):

http://127.0.0.1:5000/media/manage

5. Use the upload form or the "Refresh List" button to manage files.

Using curl to upload:

```bash
curl -X POST -H "X-API-KEY: N7k8J3mX9sVqLp2bYfDz6wR0uT1eGh" \
  -F "target=media" -F "file=@/path/to/photo.jpg" \
  http://127.0.0.1:5000/media/upload
```

Security notes
- The manage UI prompts for the API key in the browser and keeps it in-memory for that page only. This is convenient for local use but not recommended for public exposure.
- For remote access, prefer SSH tunnels, ngrok, or Cloudflare Tunnel.
- If you expose the app publicly, always set a strong API key via `SSSNL_MEDIA_API_KEY` and use HTTPS (reverse proxy or cloud tunnel) and firewall rules.

If you want, I can:
- Change the default key to be read-only from a `.env` file or prompt you to set it interactively at first run.
- Add basic authentication to the manage UI and restrict access by IP.
- Add logging of uploads and deletes to a file.

