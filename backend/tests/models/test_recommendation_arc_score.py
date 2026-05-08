from sqlalchemy.dialects.postgresql import JSONB

from app.models.recommendation import Recommendation


def test_recommendation_has_arc_score_json_column():
    column = Recommendation.__table__.c.arc_score_json

    assert isinstance(column.type, JSONB)
    assert column.nullable is False
