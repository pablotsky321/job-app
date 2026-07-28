# DynamoDB Tables for job-search-assistant
# All tables use PAY_PER_REQUEST (on-demand) billing mode
# All tables have prevent_destroy lifecycle policy to protect critical data

# Table 1: Empresas
# Purpose: Store company/employer information
# PK: companyId (String)
resource "aws_dynamodb_table" "empresas" {
  name         = "Empresas"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "companyId"

  attribute {
    name = "companyId"
    type = "S"
  }

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "Empresas"
  }
}

# Table 2: Vacantes
# Purpose: Store job vacancy listings
# PK: companyId (String), SK: vacancyId (String)
# TTL: Automatic deletion of expired vacancies
resource "aws_dynamodb_table" "vacantes" {
  name         = "Vacantes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "companyId"
  range_key    = "vacancyId"

  attribute {
    name = "companyId"
    type = "S"
  }

  attribute {
    name = "vacancyId"
    type = "S"
  }

  # TTL for automatic cleanup of expired vacancies
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "Vacantes"
  }
}

# Table 3: UsuarioVacante
# Purpose: Store user-vacancy relationships (applications, matches, interactions)
# PK: userId (String), SK: sk (String) - sk format: "vacancy#{vacancyId}" or similar
# Holds all user-vacancy relationship state (critical data)
resource "aws_dynamodb_table" "usuario_vacante" {
  name         = "UsuarioVacante"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "sk"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "UsuarioVacante"
  }
}

# Table 4: Entradas
# Purpose: Store interview questions/entries - the project's innovation differentiator
# PK: pk (String), SK: entryId (String)
# This is critical data - prevents destroy is essential
resource "aws_dynamodb_table" "entradas" {
  name         = "Entradas"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "entryId"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "entryId"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "Entradas"
  }
}

# Table 5: Perfiles
# Purpose: Store user profiles with parsed CV data
# PK: userId (String)
# Holds parsed CVs - critical user data
resource "aws_dynamodb_table" "perfiles" {
  name         = "Perfiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "Perfiles"
  }
}

# Table 6: Suscripciones
# Purpose: Store user subscriptions to companies
# PK: userId (String), SK: companyId (String)
# GSI porEmpresa: Query subscriptions by company
# Holds all user relationship state - prevents destroy is essential
resource "aws_dynamodb_table" "suscripciones" {
  name         = "Suscripciones"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "companyId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "companyId"
    type = "S"
  }

  # Global Secondary Index for querying by company
  # Allows finding all users subscribed to a specific company
  global_secondary_index {
    name            = "porEmpresa"
    hash_key        = "companyId"
    range_key       = "userId"
    projection_type = "ALL"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "Suscripciones"
  }
}

# Table 7: ScanJobs
# Purpose: Store scanning job metadata and progress
# PK: jobId (String)
# TTL: Automatic deletion of completed/abandoned jobs after 24 hours
resource "aws_dynamodb_table" "scan_jobs" {
  name         = "ScanJobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "jobId"

  attribute {
    name = "jobId"
    type = "S"
  }

  # TTL for zombie cleanup (jobs running longer than expected)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # DynamoDB Streams — drives the notificador Lambda's detection of scan job
  # status transitions (e.g. RUNNING -> DONE). NEW_AND_OLD_IMAGES is required
  # (not just NEW_IMAGE) because notificador must compare old vs new status
  # to detect the transition, not just read the current value.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Table = "ScanJobs"
  }
}
