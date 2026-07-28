# SQS Module - Message Queues for Scan and Scoring Workers
#
# This module creates 4 SQS queues with Dead Letter Queues (DLQs):
# - scan-dlq: Dead Letter Queue for failed scan messages
# - scan-queue: Main queue for scan jobs (visibility timeout: 540s = 6 × 90s Lambda timeout)
# - scoring-dlq: Dead Letter Queue for failed scoring messages
# - scoring-queue: Main queue for scoring jobs (visibility timeout: 180s = 6 × 30s Lambda timeout)
#
# Both main queues use maxReceiveCount = 3 before routing to their respective DLQs.
#
# References:
# - Requirements: 4, 16
# - Design: "SQS Queue Configuration & Visibility Timeout Formulas"
# - Backend-scan-y-scoring design: Lambda timeout values for visibility timeout calculation
#   * scan-worker Lambda timeout: 90s → scan-queue visibility timeout: 540s
#   * scoring-worker Lambda timeout: 30s → scoring-queue visibility timeout: 180s

# DLQ 1: scan-dlq
# Dead Letter Queue for scan-queue. Receives messages that fail processing after 3 retries.
# No redrive policy needed (it's a DLQ itself).
resource "aws_sqs_queue" "scan_dlq" {
  name = "scan-dlq"

  # Standard SQS settings
  message_retention_seconds = 1209600 # 14 days
  delay_seconds             = 0
  receive_wait_time_seconds = 10

  # Tags from root module (applied via default_tags in provider)
  tags = {
    Purpose = "Dead Letter Queue for scan jobs"
  }
}

# Main Queue 1: scan-queue
# Main queue for scan jobs. Messages are processed by scan-worker Lambda (90s timeout).
# After 3 failed deliveries, messages are routed to scan-dlq.
resource "aws_sqs_queue" "scan_queue" {
  name = "scan-queue"

  # Visibility timeout = 6 × Lambda timeout (scan-worker: 90s)
  # Formula: 6 × 90s = 540s (9 minutes)
  # This ensures the message stays invisible long enough for the Lambda to complete
  # plus retries without SQS re-delivering the message prematurely.
  visibility_timeout_seconds = 540

  # Standard SQS settings
  message_retention_seconds = 1209600 # 14 days
  delay_seconds             = 0
  receive_wait_time_seconds = 10

  # Redrive policy: route failed messages to scan-dlq after 3 delivery attempts
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scan_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Purpose = "Main queue for scan jobs"
  }
}

# DLQ 2: scoring-dlq
# Dead Letter Queue for scoring-queue. Receives messages that fail processing after 3 retries.
# No redrive policy needed (it's a DLQ itself).
resource "aws_sqs_queue" "scoring_dlq" {
  name = "scoring-dlq"

  # Standard SQS settings
  message_retention_seconds = 1209600 # 14 days
  delay_seconds             = 0
  receive_wait_time_seconds = 10

  tags = {
    Purpose = "Dead Letter Queue for scoring jobs"
  }
}

# Main Queue 2: scoring-queue
# Main queue for scoring jobs. Messages are processed by scoring-worker Lambda (30s timeout).
# After 3 failed deliveries, messages are routed to scoring-dlq.
resource "aws_sqs_queue" "scoring_queue" {
  name = "scoring-queue"

  # Visibility timeout = 6 × Lambda timeout (scoring-worker: 30s)
  # Formula: 6 × 30s = 180s (3 minutes)
  # This ensures the message stays invisible long enough for the Lambda to complete
  # plus retries without SQS re-delivering the message prematurely.
  visibility_timeout_seconds = 180

  # Standard SQS settings
  message_retention_seconds = 1209600 # 14 days
  delay_seconds             = 0
  receive_wait_time_seconds = 10

  # Redrive policy: route failed messages to scoring-dlq after 3 delivery attempts
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scoring_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Purpose = "Main queue for scoring jobs"
  }
}
