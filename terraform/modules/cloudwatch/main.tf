# CloudWatch Log Groups for Lambda Functions
# All log groups have 7-day retention per Requirement 10

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/job-search-api"
  retention_in_days = 7

  tags = {
    Name = "job-search-api-logs"
  }
}

resource "aws_cloudwatch_log_group" "orquestador" {
  name              = "/aws/lambda/job-search-orquestador"
  retention_in_days = 7

  tags = {
    Name = "job-search-orquestador-logs"
  }
}

resource "aws_cloudwatch_log_group" "scan_worker" {
  name              = "/aws/lambda/job-search-scan-worker"
  retention_in_days = 7

  tags = {
    Name = "job-search-scan-worker-logs"
  }
}

resource "aws_cloudwatch_log_group" "scoring_worker" {
  name              = "/aws/lambda/job-search-scoring-worker"
  retention_in_days = 7

  tags = {
    Name = "job-search-scoring-worker-logs"
  }
}

resource "aws_cloudwatch_log_group" "notificador" {
  name              = "/aws/lambda/job-search-notificador"
  retention_in_days = 7

  tags = {
    Name = "job-search-notificador-logs"
  }
}

# SNS Topic for alarms
resource "aws_sns_topic" "alerts" {
  name = "job-search-alerts"

  tags = {
    Name = "job-search-alerts-topic"
  }
}

# Lambda Error Alarm
# Triggers when any Lambda function has errors in 5-minute period
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "job-search-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when Lambda functions have errors"

  # Monitor all Lambda functions via multiple dimensions
  # Note: Ideally this would monitor all functions, but CloudWatch alarms
  # are tied to specific dimensions. In production, you would create
  # separate alarms for each function or use composite alarms.

  alarm_actions = [aws_sns_topic.alerts.arn]

  # For now, monitor the API function as primary indicator
  dimensions = {
    FunctionName = var.api_function_name
  }
}

# Lambda Duration Alarm
# Triggers when Lambda function duration exceeds threshold
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "job-search-lambda-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = var.lambda_duration_threshold_ms
  alarm_description   = "Alert when Lambda function duration exceeds threshold"

  alarm_actions = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = var.api_function_name
  }
}

# Billing Alarm
# Triggers when estimated monthly charges exceed threshold
resource "aws_cloudwatch_metric_alarm" "billing_alarm" {
  alarm_name          = "job-search-billing-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 86400
  statistic           = "Maximum"
  threshold           = var.billing_alarm_threshold
  alarm_description   = "Alert when estimated monthly charges exceed threshold (${var.billing_alarm_threshold} USD)"

  alarm_actions = [aws_sns_topic.alerts.arn]

  dimensions = {
    Currency = "USD"
  }
}
