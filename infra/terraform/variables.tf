variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "Use separate staging and prod state and accounts."
  }
}
variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "certificate_arn" {
  type        = string
  description = "Validated regional ACM certificate for the API DNS name."
}
variable "image" {
  type        = string
  description = "Immutable ECR image URI including @sha256 digest."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "Deploy an immutable image digest."
  }
}
variable "bedrock_model_id" {
  type        = string
  default     = ""
  description = "Approved regional foundation model ID supporting Converse structured output. Empty disables AI."
}
variable "bedrock_model_arn" {
  type        = string
  default     = ""
  description = "Exact matching regional foundation model ARN for IAM. No inference profiles."
}
variable "diarizer_url" {
  type    = string
  default = ""
}
variable "transcribe_enabled" {
  type    = bool
  default = false
}
variable "api_count" {
  type    = number
  default = 2
}
variable "worker_count" {
  type    = number
  default = 2
}
variable "services_enabled" {
  type        = bool
  default     = false
  description = "Keep false during bootstrap. Enable after secrets and migrations succeed."
}
variable "database_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
variable "alarm_topic_arn" {
  type        = string
  description = "SNS topic with confirmed operational subscribers."
}
variable "collector_image" {
  type        = string
  description = "Pinned ADOT collector image URI including digest. Collector config is baked into the image."
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.collector_image))
    error_message = "Pin the reviewed collector image to a digest."
  }
}
