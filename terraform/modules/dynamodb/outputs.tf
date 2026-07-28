# Outputs for DynamoDB tables
# These outputs provide table names and ARNs for other modules to reference

output "empresas_table_name" {
  description = "Name of the Empresas table"
  value       = aws_dynamodb_table.empresas.name
}

output "empresas_table_arn" {
  description = "ARN of the Empresas table"
  value       = aws_dynamodb_table.empresas.arn
}

output "vacantes_table_name" {
  description = "Name of the Vacantes table"
  value       = aws_dynamodb_table.vacantes.name
}

output "vacantes_table_arn" {
  description = "ARN of the Vacantes table"
  value       = aws_dynamodb_table.vacantes.arn
}

output "usuario_vacante_table_name" {
  description = "Name of the UsuarioVacante table"
  value       = aws_dynamodb_table.usuario_vacante.name
}

output "usuario_vacante_table_arn" {
  description = "ARN of the UsuarioVacante table"
  value       = aws_dynamodb_table.usuario_vacante.arn
}

output "entradas_table_name" {
  description = "Name of the Entradas table"
  value       = aws_dynamodb_table.entradas.name
}

output "entradas_table_arn" {
  description = "ARN of the Entradas table"
  value       = aws_dynamodb_table.entradas.arn
}

output "perfiles_table_name" {
  description = "Name of the Perfiles table"
  value       = aws_dynamodb_table.perfiles.name
}

output "perfiles_table_arn" {
  description = "ARN of the Perfiles table"
  value       = aws_dynamodb_table.perfiles.arn
}

output "suscripciones_table_name" {
  description = "Name of the Suscripciones table"
  value       = aws_dynamodb_table.suscripciones.name
}

output "suscripciones_table_arn" {
  description = "ARN of the Suscripciones table"
  value       = aws_dynamodb_table.suscripciones.arn
}

output "scan_jobs_table_name" {
  description = "Name of the ScanJobs table"
  value       = aws_dynamodb_table.scan_jobs.name
}

output "scan_jobs_table_arn" {
  description = "ARN of the ScanJobs table"
  value       = aws_dynamodb_table.scan_jobs.arn
}

output "scan_jobs_table_stream_arn" {
  description = "ARN of the ScanJobs table DynamoDB Stream (NEW_AND_OLD_IMAGES), used to trigger the notificador Lambda"
  value       = aws_dynamodb_table.scan_jobs.stream_arn
}

# All table ARNs as a map for easy reference
output "all_table_arns" {
  description = "Map of all DynamoDB table ARNs"
  value = {
    empresas        = aws_dynamodb_table.empresas.arn
    vacantes        = aws_dynamodb_table.vacantes.arn
    usuario_vacante = aws_dynamodb_table.usuario_vacante.arn
    entradas        = aws_dynamodb_table.entradas.arn
    perfiles        = aws_dynamodb_table.perfiles.arn
    suscripciones   = aws_dynamodb_table.suscripciones.arn
    scan_jobs       = aws_dynamodb_table.scan_jobs.arn
  }
}

# All table names as a map for environment variables
output "all_table_names" {
  description = "Map of all DynamoDB table names for Lambda environment variables"
  value = {
    empresas        = aws_dynamodb_table.empresas.name
    vacantes        = aws_dynamodb_table.vacantes.name
    usuario_vacante = aws_dynamodb_table.usuario_vacante.name
    entradas        = aws_dynamodb_table.entradas.name
    perfiles        = aws_dynamodb_table.perfiles.name
    suscripciones   = aws_dynamodb_table.suscripciones.name
    scan_jobs       = aws_dynamodb_table.scan_jobs.name
  }
}
