output "api_log_group_name" {
  description = "CloudWatch log group name for API Lambda"
  value       = aws_cloudwatch_log_group.api.name
}

output "api_log_group_arn" {
  description = "CloudWatch log group ARN for API Lambda"
  value       = aws_cloudwatch_log_group.api.arn
}

output "orquestador_log_group_name" {
  description = "CloudWatch log group name for Orquestador Lambda"
  value       = aws_cloudwatch_log_group.orquestador.name
}

output "orquestador_log_group_arn" {
  description = "CloudWatch log group ARN for Orquestador Lambda"
  value       = aws_cloudwatch_log_group.orquestador.arn
}

output "scan_worker_log_group_name" {
  description = "CloudWatch log group name for Scan Worker Lambda"
  value       = aws_cloudwatch_log_group.scan_worker.name
}

output "scan_worker_log_group_arn" {
  description = "CloudWatch log group ARN for Scan Worker Lambda"
  value       = aws_cloudwatch_log_group.scan_worker.arn
}

output "scoring_worker_log_group_name" {
  description = "CloudWatch log group name for Scoring Worker Lambda"
  value       = aws_cloudwatch_log_group.scoring_worker.name
}

output "scoring_worker_log_group_arn" {
  description = "CloudWatch log group ARN for Scoring Worker Lambda"
  value       = aws_cloudwatch_log_group.scoring_worker.arn
}

output "notificador_log_group_name" {
  description = "CloudWatch log group name for Notificador Lambda"
  value       = aws_cloudwatch_log_group.notificador.name
}

output "notificador_log_group_arn" {
  description = "CloudWatch log group ARN for Notificador Lambda"
  value       = aws_cloudwatch_log_group.notificador.arn
}

output "alerts_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms"
  value       = aws_sns_topic.alerts.arn
}

output "alerts_topic_name" {
  description = "SNS topic name for CloudWatch alarms"
  value       = aws_sns_topic.alerts.name
}

output "lambda_errors_alarm_arn" {
  description = "Lambda errors alarm ARN"
  value       = aws_cloudwatch_metric_alarm.lambda_errors.arn
}

output "lambda_duration_alarm_arn" {
  description = "Lambda duration alarm ARN"
  value       = aws_cloudwatch_metric_alarm.lambda_duration.arn
}

output "billing_alarm_arn" {
  description = "Billing alarm ARN"
  value       = aws_cloudwatch_metric_alarm.billing_alarm.arn
}
