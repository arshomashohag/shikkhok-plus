output "repository_url" {
  description = "The image repository, without a tag."
  value       = aws_ecr_repository.backend.repository_url
}

output "repository_arn" {
  description = "For the instance role's pull policy."
  value       = aws_ecr_repository.backend.arn
}
