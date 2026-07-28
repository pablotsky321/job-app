"""Quick verification that new/updated models work correctly."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from backend.shared.models import Entrada, UsuarioVacante


class TestUsuarioVacanteUpdated:
    """Verify UsuarioVacante model with new fields."""

    def test_required_fields(self):
        uv = UsuarioVacante(
            userId="user-1",
            companyId="company-abc",
            vacancyId="vac-xyz",
            estado="nueva",
        )
        assert uv.userId == "user-1"
        assert uv.companyId == "company-abc"
        assert uv.vacancyId == "vac-xyz"
        assert uv.estado == "nueva"

    def test_optional_fields_default_none(self):
        uv = UsuarioVacante(
            userId="user-1",
            companyId="company-abc",
            vacancyId="vac-xyz",
            estado="vista",
        )
        assert uv.score is None
        assert uv.scoreDetalle is None
        assert uv.scoreProfileVersion is None
        assert uv.cvAtsTexto is None
        assert uv.cvGeneratedAt is None
        assert uv.appliedAt is None

    def test_all_estado_values_accepted(self):
        for estado in ("nueva", "vista", "aplicada", "filtered_out"):
            uv = UsuarioVacante(
                userId="u1", companyId="c1", vacancyId="v1", estado=estado
            )
            assert uv.estado == estado

    def test_aplicada_with_appliedAt(self):
        now = datetime(2024, 6, 15, 10, 0, 0)
        uv = UsuarioVacante(
            userId="u1",
            companyId="c1",
            vacancyId="v1",
            estado="aplicada",
            appliedAt=now,
        )
        assert uv.appliedAt == now

    def test_cv_ats_fields(self):
        now = datetime(2024, 6, 15, 10, 0, 0)
        uv = UsuarioVacante(
            userId="u1",
            companyId="c1",
            vacancyId="v1",
            estado="nueva",
            cvAtsTexto="Generated CV text...",
            cvGeneratedAt=now,
        )
        assert uv.cvAtsTexto == "Generated CV text..."
        assert uv.cvGeneratedAt == now

    def test_score_range_validation(self):
        with pytest.raises(ValidationError):
            UsuarioVacante(
                userId="u1", companyId="c1", vacancyId="v1", estado="nueva", score=101
            )
        with pytest.raises(ValidationError):
            UsuarioVacante(
                userId="u1", companyId="c1", vacancyId="v1", estado="nueva", score=-1
            )

    def test_extra_fields_ignored(self):
        uv = UsuarioVacante(
            userId="u1",
            companyId="c1",
            vacancyId="v1",
            estado="nueva",
            unknownField="should be ignored",
        )
        assert not hasattr(uv, "unknownField")

    def test_missing_companyId_fails(self):
        with pytest.raises(ValidationError):
            UsuarioVacante(userId="u1", vacancyId="v1", estado="nueva")


class TestEntradaModel:
    """Verify new Entrada model."""

    def test_basic_creation(self):
        e = Entrada(
            pk="user1#company1#vacancy1",
            entryId="01HWXYZ123ABC",
            tipo="preguntas",
            contenido="¿Cuál es la metodología de desarrollo?",
        )
        assert e.pk == "user1#company1#vacancy1"
        assert e.entryId == "01HWXYZ123ABC"
        assert e.tipo == "preguntas"
        assert e.contenido == "¿Cuál es la metodología de desarrollo?"
        assert isinstance(e.createdAt, datetime)

    def test_nota_entrevista_tipo(self):
        e = Entrada(
            pk="u1#c1#v1",
            entryId="01HWXYZ",
            tipo="nota_entrevista",
            contenido="Notas de la entrevista...",
        )
        assert e.tipo == "nota_entrevista"

    def test_extra_fields_ignored(self):
        e = Entrada(
            pk="u1#c1#v1",
            entryId="01HWXYZ",
            tipo="preguntas",
            contenido="test",
            unknownField="ignored",
        )
        assert not hasattr(e, "unknownField")

    def test_missing_required_field_fails(self):
        with pytest.raises(ValidationError):
            Entrada(pk="u1#c1#v1", entryId="01HWXYZ", tipo="preguntas")
