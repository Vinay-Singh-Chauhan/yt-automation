output "trigger_topic" {
  value       = google_pubsub_topic.trigger.name
  description = "Pub/Sub topic for manual and scheduled run requests."
}

output "intake_url" {
  value       = google_cloud_run_v2_service.intake.uri
  description = "Internal Cloud Run intake service URL."
}

output "assets_bucket" {
  value       = google_storage_bucket.assets.name
  description = "Private temporary assets bucket; successful runs delete their prefix."
}

output "youtube_oauth_secret" {
  value       = google_secret_manager_secret.youtube_oauth.secret_id
  description = "Secret Manager secret ID; add the OAuth JSON payload before running."
}

output "scheduler_job" {
  value       = google_cloud_scheduler_job.trigger.name
  description = "Cloud Scheduler job (paused unless enable_scheduler is true)."
}
