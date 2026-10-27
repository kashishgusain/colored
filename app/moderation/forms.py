from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from ..models import Category


class StewardEditForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(3, 200)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(10, 1500)])
    category_id = SelectField("Category", coerce=int)
    tags = StringField("Tags", validators=[Optional(), Length(max=400)])
    body_text = TextAreaField("Written text", validators=[Optional(), Length(max=60000)])
    transcript_text = TextAreaField("Transcript", validators=[Optional(), Length(max=120000)])
    translation_hi = TextAreaField("Hindi translation", validators=[Optional(), Length(max=120000)])
    translation_en = TextAreaField("English translation", validators=[Optional(), Length(max=120000)])
    summary = TextAreaField("Summary", validators=[Optional(), Length(max=2000)])

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name)]


class DecisionForm(FlaskForm):
    decision = SelectField("Decision", choices=[("approve", "Approve"), ("revise", "Request corrections"),
                                                ("reject", "Reject"), ("comment", "Add a note only")])
    comment = TextAreaField("Note for the contributor and the review log", validators=[Optional(), Length(max=2000)])
