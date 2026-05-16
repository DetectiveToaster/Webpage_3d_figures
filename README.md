# Webpage_3d_figures

Quick setup (dev/test)
- Create and activate a virtualenv, then `pip install -r requirements.txt`.
- Export `SECRET_KEY=$(python - <<'PY'\nimport secrets; print(secrets.token_urlsafe(64))\nPY)` before running the API.
- Set `DATABASE_URL`, e.g. `postgresql://user:pass@localhost:5433/3d_test`.
- To auto-create an admin on startup, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`; otherwise the seed is skipped.
- Manual checkout is the default. Configure `BIZUM_PHONE`, `BANK_TRANSFER_IBAN`, `BANK_TRANSFER_BENEFICIARY`, and rough shipping envs (`MANUAL_SHIPPING_DEFAULT_COST`, `MANUAL_SHIPPING_PER_ITEM_COST`, `MANUAL_SHIPPING_PER_KG_COST`, `MANUAL_SHIPPING_FREE_MIN_SUBTOTAL`) or admin shipping rules.
- Optional integrations are disabled by default. Set `ENABLE_PAYPAL=true` plus PayPal envs, or `ENABLE_CARRIER_SHIPPING=true` plus carrier envs, only when those accounts exist.
- Set `CORS_ORIGINS` as a comma-separated list for the frontend, e.g. `http://localhost:3000,http://your-ec2-host:3000`.
- Product media uploads support images, GLTF/GLB, PDF, and STL files. Browsers often send STL as `application/octet-stream`; `.stl` uploads are normalized to `model/stl`. Set `MAX_UPLOAD_BYTES=157286400` for a 150 MiB limit, which covers typical 20-120 MiB STL files.
- New deployments should run `alembic upgrade head`; the baseline migration creates tables from an empty database.
