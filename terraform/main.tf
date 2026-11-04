locals {
  required_services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "firestore.googleapis.com",
    "iamcredentials.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "texttospeech.googleapis.com",
    "workflowexecutions.googleapis.com",
    "workflows.googleapis.com",
  ])
  common_env = {
    GOOGLE_CLOUD_PROJECT   = var.project_id
    REGION                 = var.region
    VERTEX_AI_LOCATION     = var.vertex_ai_location
    ASSETS_BUCKET          = var.bucket_name
    YOUTUBE_OAUTH_SECRET   = var.youtube_secret_name
    YOUTUBE_PRIVACY_STATUS = var.youtube_privacy_status
    GEMINI_MODEL           = var.gemini_model
    GEMINI_IMAGE_MODEL     = var.gemini_image_model
    TTS_VOICE              = var.tts_voice
    TTS_LANGUAGE           = var.tts_language
    MIN_VIDEO_SECONDS      = tostring(var.min_video_seconds)
    MAX_VIDEO_SECONDS      = tostring(var.max_video_seconds)
    WORK_DIR               = "/tmp/yt-short"
  }
}

resource "google_project_service" "apis" {
  for_each           = local.required_services
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "assets" {
  name                        = var.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age            = 1
      matches_prefix = ["runs/"]
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_firestore_database" "pipeline" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

resource "google_secret_manager_secret" "youtube_oauth" {
  project   = var.project_id
  secret_id = var.youtube_secret_name
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repository
  description   = "Container images for the YouTube Shorts pipeline"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "google_pubsub_topic" "trigger" {
  name       = "yt-trigger-topic"
  depends_on = [google_project_service.apis]
}

resource "google_service_account" "pipeline" {
  account_id   = "yt-pipeline-runtime"
  display_name = "YouTube Shorts pipeline runtime"
}

resource "google_service_account" "workflow" {
  account_id   = "yt-pipeline-workflow"
  display_name = "YouTube Shorts workflow executor"
}

resource "google_service_account" "pubsub_push" {
  account_id   = "yt-pubsub-push"
  display_name = "Pub/Sub push identity for pipeline intake"
}

resource "google_project_iam_member" "pipeline_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/serviceusage.serviceUsageConsumer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_assets" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_secret_manager_secret_iam_member" "pipeline_secret" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.youtube_oauth.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "intake_invokes_workflow" {
  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_cloud_run_v2_service" "intake" {
  name                = "yt-pipeline-intake"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.pipeline.email
    timeout         = "60s"
    containers {
      image = var.app_image
      env {
        name  = "WORKFLOW_NAME"
        value = google_workflows_workflow.pipeline.name
      }
      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_job" "worker" {
  name                = "yt-pipeline-worker"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.pipeline.email
      timeout         = "3600s"
      max_retries     = 1
      containers {
        name    = "pipeline"
        image   = var.app_image
        command = ["python"]
        args    = ["-m", "app.worker"]
        dynamic "env" {
          for_each = local.common_env
          content {
            name  = env.key
            value = env.value
          }
        }
        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_workflows_workflow" "pipeline" {
  name            = "yt-pipeline-workflow"
  region          = var.region
  description     = "Starts a Cloud Run Job to generate and publish one YouTube Short."
  service_account = google_service_account.workflow.id
  source_contents = templatefile("${path.module}/workflow.yaml", {
    project_id = var.project_id
    region     = var.region
    job_name   = google_cloud_run_v2_job.worker.name
  })
  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "workflow_run_jobs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_service_account_iam_member" "workflow_run_as_pipeline" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.workflow.email}"
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.intake.location
  name     = google_cloud_run_v2_service.intake.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

resource "google_pubsub_subscription" "push" {
  name  = "yt-trigger-push"
  topic = google_pubsub_topic.trigger.id
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.intake.uri}/pubsub"
    oidc_token {
      service_account_email = google_service_account.pubsub_push.email
      audience              = google_cloud_run_v2_service.intake.uri
    }
  }
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }
  depends_on = [
    google_cloud_run_v2_service_iam_member.pubsub_invoker,
    google_service_account_iam_member.pubsub_token_creator,
  ]
}

resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.pubsub_push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  depends_on         = [google_project_service.apis]
}

resource "google_pubsub_topic_iam_member" "scheduler_publish" {
  topic  = google_pubsub_topic.trigger.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

data "google_project" "project" {
  project_id = var.project_id
}

resource "google_cloud_scheduler_job" "trigger" {
  name             = "yt-short-schedule"
  region           = var.region
  description      = "Scheduled request to generate one YouTube Short."
  schedule         = var.scheduler_cron
  time_zone        = var.scheduler_timezone
  paused           = !var.enable_scheduler
  attempt_deadline = "30s"

  pubsub_target {
    topic_name = google_pubsub_topic.trigger.id
    data = base64encode(jsonencode({
      topic            = var.scheduler_topic
      language         = var.tts_language
      duration_seconds = 20
    }))
  }
  depends_on = [
    google_project_service.apis,
    google_pubsub_topic_iam_member.scheduler_publish,
  ]
}
