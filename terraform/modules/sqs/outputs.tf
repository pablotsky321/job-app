# SQS Module Outputs - Queue URLs for Lambda Environment Variables
#
# These outputs export the SQS queue URLs for use as Lambda environment variables.
# Lambda functions need these URLs to send/receive messages to/from the queues.
#
# References:
# - Requirements: 4, 16
# - Design: Lambda environment variable configuration

# Output: scan-dlq ARN
# Used for referencing the Dead Letter Queue in redrive policies and monitoring.
output "scan_dlq_arn" {
  description = "ARN of the scan-dlq (Dead Letter Queue)"
  value       = aws_sqs_queue.scan_dlq.arn
}

# Output: scan-queue URL
# Used by orquestador Lambda to send scan jobs.
# Used by scan-worker Lambda to receive scan jobs.
output "scan_queue_url" {
  description = "URL of the scan-queue for Lambda environment variables"
  value       = aws_sqs_queue.scan_queue.url
}

# Output: scan-queue ARN
# Used for IAM policy permissions and monitoring.
output "scan_queue_arn" {
  description = "ARN of the scan-queue"
  value       = aws_sqs_queue.scan_queue.arn
}

# Output: scoring-dlq ARN
# Used for referencing the Dead Letter Queue in redrive policies and monitoring.
output "scoring_dlq_arn" {
  description = "ARN of the scoring-dlq (Dead Letter Queue)"
  value       = aws_sqs_queue.scoring_dlq.arn
}

# Output: scoring-queue URL
# Used by scan-worker Lambda to send scoring jobs.
# Used by scoring-worker Lambda to receive scoring jobs.
output "scoring_queue_url" {
  description = "URL of the scoring-queue for Lambda environment variables"
  value       = aws_sqs_queue.scoring_queue.url
}

# Output: scoring-queue ARN
# Used for IAM policy permissions and monitoring.
output "scoring_queue_arn" {
  description = "ARN of the scoring-queue"
  value       = aws_sqs_queue.scoring_queue.arn
}
