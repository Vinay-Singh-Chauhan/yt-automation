variable "project_id" {
  type        = string
  description = "Google Cloud project ID."
}

variable "region" {
  type        = string
  description = "Region for Cloud Run, Workflows, and Cloud Scheduler."
  default     = "us-central1"
}

variable "app_image" {
  type        = string
  description = "Built container image URI in Artifact Registry."
}

variable "artifact_repository" {
  type        = string
  description = "Artifact Registry repository name for the application image."
  default     = "yt-pipeline"
}

variable "bucket_name" {
  type        = string
  description = "Globally unique bucket name for temporary assets."
}

variable "scheduler_cron" {
  type        = string
  description = "Cron schedule for Shorts generation."
  default     = "0 9 * * *"
}

variable "scheduler_timezone" {
  type        = string
  description = "IANA timezone for the scheduler."
  default     = "Etc/UTC"
}

variable "scheduler_topic" {
  type        = string
  description = "Topic prompt sent by the scheduler."
  default     = "Create an original, useful YouTube Short for the channel audience."
}

variable "enable_scheduler" {
  type        = bool
  description = "Enable recurring generation after the first manually reviewed test."
  default     = false
}

variable "youtube_privacy_status" {
  type        = string
  description = "Default YouTube visibility; private is recommended for the pilot."
  default     = "private"
  validation {
    condition     = contains(["private", "unlisted", "public"], var.youtube_privacy_status)
    error_message = "youtube_privacy_status must be private, unlisted, or public."
  }
}

variable "youtube_secret_name" {
  type        = string
  description = "Secret Manager secret containing YouTube OAuth JSON."
  default     = "yt-oauth-credentials"
}

variable "gemini_model" {
  type        = string
  description = "Vertex AI Gemini model ID used for Shorts content generation."
  default     = "gemini-3.8-flash"
}

variable "gemini_image_model" {
  type        = string
  description = "Vertex AI Gemini model ID used to generate vertical video backgrounds."
  default     = "gemini-3.1-flash-image"
}

variable "vertex_ai_location" {
  type        = string
  description = "Vertex AI location for Gemini requests; use global when the model is not available regionally."
  default     = "global"
}

variable "tts_voice" {
  type        = string
  description = "Cloud Text-to-Speech voice name."
  default     = "en-US-Neural2-F"
}

variable "tts_language" {
  type        = string
  description = "Cloud Text-to-Speech language code."
  default     = "en-US"
}

variable "min_video_seconds" {
  type        = number
  description = "Minimum accepted rendered narration duration."
  default     = 10
}

variable "max_video_seconds" {
  type        = number
  description = "Maximum accepted rendered narration duration."
  default     = 30
}
