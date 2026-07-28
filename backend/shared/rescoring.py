"""
Rescoring detector functions for staleness detection and async re-enqueue.

Provides:
- is_score_stale: Pure function (no I/O) that detects profileVersion mismatch.
- enqueue_rescore: Publishes one ScoringMessage to SQS_Scoring (non-blocking).

Requirements: 18.1-18.6
"""

import json
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from backend.shared.logging_config import get_contextual_logger
from backend.shared.models import Perfiles, ScoringMessage, UsuarioVacante

logger = get_contextual_logger(__name__)


def is_score_stale(usuario_vacante: Optional[UsuarioVacante], perfil: Perfiles) -> bool:
    """
    Pure staleness-detection function.

    Returns True when the stored scoreProfileVersion does not match the user's
    current profileVersion, indicating the score needs recalculation.

    Returns False when:
    - usuario_vacante is None (no record to compare)
    - scoreProfileVersion equals perfil.profileVersion (score is current)

    Requirements: 18.1, 18.2
    - NO network I/O
    - NO SQS publish
    - NO mutation of any stored data
    """
    if usuario_vacante is None:
        return False

    return usuario_vacante.scoreProfileVersion != perfil.profileVersion


def enqueue_rescore(userId: str, vacancyId: str) -> bool:
    """
    Publish exactly one ScoringMessage to SQS_Scoring for async rescoring.

    Non-blocking: returns immediately after publish attempt.
    Returns True on success, False on error (logs error, never raises).

    Requirements: 18.3, 18.4, 18.5, 18.6
    """
    queue_url = os.environ.get("SQS_SCORING_QUEUE_URL", "")

    if not queue_url:
        logger.error(
            "enqueue_rescore_failed",
            context={
                "userId": userId,
                "vacancyId": vacancyId,
                "error": "SQS_SCORING_QUEUE_URL not set",
            },
        )
        return False

    message = ScoringMessage(userId=userId, vacancyId=vacancyId)

    try:
        sqs_client = boto3.client("sqs")
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=message.model_dump_json(),
        )
        logger.info(
            "enqueue_rescore_success",
            context={"userId": userId, "vacancyId": vacancyId},
        )
        return True

    except (ClientError, Exception) as e:
        logger.error(
            "enqueue_rescore_failed",
            context={
                "userId": userId,
                "vacancyId": vacancyId,
                "error": str(e)[:200],
            },
        )
        return False
