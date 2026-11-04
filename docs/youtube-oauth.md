# YouTube OAuth setup

YouTube uploads require user-authorized OAuth. A YouTube API key is not enough
to upload to a channel.

1. In Google Cloud Console, enable YouTube Data API v3 for the project.
2. Configure the OAuth consent screen for your intended audience and complete
   any verification/testing requirements presented by Google.
3. Create an OAuth client suitable for the one-time authorization flow. Keep
   the client secret private.
4. Perform the OAuth authorization with the scope
   `https://www.googleapis.com/auth/youtube.upload`, using the Google account
   that owns or manages the target channel. Request offline access so a refresh
   token is issued. This is the only YouTube scope the current pipeline needs:
   it uploads the video and thumbnail and uses the video ID returned by the
   upload response rather than calling `videos.list`.
5. Store a JSON object in Secret Manager with this shape:

   ```json
   {
     "client_id": "OAUTH_CLIENT_ID",
     "client_secret": "OAUTH_CLIENT_SECRET",
     "refresh_token": "OAUTH_REFRESH_TOKEN",
     "token_uri": "https://oauth2.googleapis.com/token"
   }
   ```

6. Add the JSON as a secret version named by `YOUTUBE_OAUTH_SECRET`. The
   pipeline runtime service account receives access to that secret only.
7. Test a private upload and inspect the target channel before enabling the
   Scheduler.

Do not place OAuth files in Git, container build contexts, logs, or Terraform
variables. Refresh tokens can be revoked; if uploads begin failing with an
authorization error, re-authorize the channel and add a new secret version.

The YouTube API project may have upload quotas or verification restrictions.
Check the current API Console quota and YouTube API policies for the project;
API access approval is independent of this code deployment.

The upload response confirms that YouTube accepted the video and returned an
ID; it does not confirm that YouTube's transcoding is finished. Check the
video in YouTube Studio for processing status. A separate `videos.list` status
check would require an additional read scope and a newly authorized refresh
token; the pipeline intentionally avoids that broader permission.
