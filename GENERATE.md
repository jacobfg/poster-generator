# Generate

Spotify API ID/Key is required as `SPOTIFY_ID` and `SPOTIFY_SECRET` environment variables.

# Use 1Pass stored credentials

With 1Password credentials and xargs you can run all are once

```
op run --account <my account> --env-file="./.env" -- bash -c 'cat albums.txt | xargs python nfc-cards.py'
```