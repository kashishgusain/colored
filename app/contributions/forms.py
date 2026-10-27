from flask_wtf import FlaskForm
from flask_wtf.file import FileField, MultipleFileField
from wtforms import BooleanField, RadioField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from ..models import Category, LANGUAGES, UTTARAKHAND_DISTRICTS


class RecordFormBase(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(3, 200)])
    description = TextAreaField("Short description", validators=[DataRequired(), Length(10, 1500)])
    category_id = SelectField("Cultural category", coerce=int, validators=[DataRequired()])
    language = SelectField("Language or dialect", choices=LANGUAGES, validators=[DataRequired()])
    district = SelectField("District", validators=[Optional()])
    village = StringField("Village or town (optional)", validators=[Optional(), Length(max=100)])
    tags = StringField("Cultural tags (comma separated)", validators=[Optional(), Length(max=400)])
    attribution = SelectField("How should we credit you?", choices=[
        ("named", "Show my name"), ("anonymous", "Keep me anonymous"), ("community", "Credit my community")])
    is_public = RadioField("Publication preference", choices=[
        ("1", "Public archive: may appear in search and the Ask LOKVAANI AI assistant once approved"),
        ("0", "Private archive: preserved for the community, never shown publicly")], default="1")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.category_id.choices = [(c.id, c.name) for c in Category.query.filter_by(is_active=True).order_by(Category.name)]
        self.district.choices = [("", "Not sure / other")] + [(d, d) for d in UTTARAKHAND_DISTRICTS]


class NewRecordForm(RecordFormBase):
    submission_type = RadioField("What are you sharing?", choices=[
        ("text", "A written story, recipe or description"),
        ("media", "An audio or video recording")], default="text")
    body_text = TextAreaField("Written text", validators=[Optional(), Length(max=60000)])
    media_file = FileField("Audio or video file")
    photos = MultipleFileField("Photographs (optional)")
    document = FileField("Supporting document (optional, PDF or TXT)")
    consent_given = BooleanField(
        "I confirm that I have the right to share this, that anyone recorded has agreed, and that I understand "
        "nothing is published until a Community Steward approves it.", validators=[DataRequired(
            message="Consent is required before we can store your contribution.")])

    def validate_body_text(self, field):
        if self.submission_type.data == "text" and len((field.data or "").strip()) < 50:
            raise ValidationError("Please write at least 50 characters, or choose the recording option.")


class EditRecordForm(RecordFormBase):
    body_text = TextAreaField("Written text", validators=[Optional(), Length(max=60000)])
    transcript_text = TextAreaField("Transcript (correct any mistakes)", validators=[Optional(), Length(max=120000)])
    translation_hi = TextAreaField("Hindi translation", validators=[Optional(), Length(max=120000)])
    translation_en = TextAreaField("English translation", validators=[Optional(), Length(max=120000)])
    summary = TextAreaField("Summary", validators=[Optional(), Length(max=2000)])
    is_public = RadioField("Publication preference", choices=[("1", "Public archive"), ("0", "Private archive")])
