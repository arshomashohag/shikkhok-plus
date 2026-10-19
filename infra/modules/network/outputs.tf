output "vpc_id" {
  description = "The VPC id."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Both public subnets. RDS needs two AZs even Single-AZ."
  value       = aws_subnet.public[*].id
}
