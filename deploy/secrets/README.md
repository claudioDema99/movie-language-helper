# Runtime secret files

For the provider-free private profile, create `private_access_token` with mode
`0600` and a long random URL-safe value. This credential is used only between
the edge proxy and backend. Also create `web_basic_auth_hash` containing a
Caddy-compatible password hash, generated interactively with `docker run --rm
-it caddy:2-alpine caddy hash-password`. The browser login username
defaults to `movie-helper` and can be changed with `MLH_BASIC_AUTH_USERNAME`.

When the provider gates are approved and `compose.providers.yaml` is explicitly
included, also create non-empty `openai_api_key` and `subdl_api_key` files.

Never commit secret values. A production platform secret manager should replace
these local Compose files.
