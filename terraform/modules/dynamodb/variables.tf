# Variables for DynamoDB module
# This module does not currently require any input variables as all table
# configurations are static. This file is provided for future extensibility.

# Potential future variables (commented out for now):
#
# variable "table_billing_mode" {
#   description = "Billing mode for DynamoDB tables (PAY_PER_REQUEST or PROVISIONED)"
#   type        = string
#   default     = "PAY_PER_REQUEST"
# }
#
# variable "enable_ttl" {
#   description = "Whether to enable TTL on tables that support it"
#   type        = bool
#   default     = true
# }
