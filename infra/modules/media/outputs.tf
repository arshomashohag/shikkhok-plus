output "media_bucket" {
  description = "The bucket's name: SHIKKHOKPLUS_MEDIA_BUCKET in the API's runtime env."
  value       = aws_s3_bucket.media.id
}

output "media_bucket_regional_domain" {
  description = <<-EOT
    The bucket's regional endpoint, <bucket>.s3.<region>.amazonaws.com: the
    site distribution's /m/* origin, and the one host the web and admin
    pages' CSP admit for uploads and presigned previews.
  EOT
  value       = local.regional_domain
}

output "media_role_arn" {
  description = "The role the app host assumes for the API container's media credentials."
  value       = aws_iam_role.media.arn
}
