from django.db import migrations


QUESTIONS = [
    # (text, type)  — first 6 are SHORT_TEXT
    ("Team Name", "SHORT_TEXT"),
    ("Tractor Name", "SHORT_TEXT"),
    ("Advisor's Name", "SHORT_TEXT"),
    ("Team Captain's Name", "SHORT_TEXT"),
    ("Driver 1 (100 lb.)", "SHORT_TEXT"),
    ("Driver 1 (600 lb.)", "SHORT_TEXT"),
    # remaining 20 are LONG_TEXT
    ("Team Motto", "LONG_TEXT"),
    ("What are the specifications of your team's tractor? (i.e. Type of Drivetrain, Steering System)", "LONG_TEXT"),
    ("What was/is the most challenging part of designing and/or building the tractor?", "LONG_TEXT"),
    ("What was/is the best part of designing and/or building the tractor or this competition?", "LONG_TEXT"),
    ("How long (weeks or hours) did it take to build the tractor?", "LONG_TEXT"),
    ("How many team members worked on your team's tractor?", "LONG_TEXT"),
    ("How many years has your school competed in the competition?", "LONG_TEXT"),
    ("If your team chose a theme song, what would it be?", "LONG_TEXT"),
    ("What 5 words would you use to describe your tractor?", "LONG_TEXT"),
    ("What is one unique thing about your tractor or team that people would be surprised to hear?", "LONG_TEXT"),
    ("If your advisor was a superhero, who would he/she be, and why?", "LONG_TEXT"),
    ("What is the coolest option you could get on the tractor (that may not be on the actual competition tractor)?", "LONG_TEXT"),
    ("What's the most ridiculous thing you've ever bought online for the tractor?", "LONG_TEXT"),
    ("What's the strangest talent or skill your team members possess?", "LONG_TEXT"),
    ("If you were stranded on a durability track and could have only one item, what would it be and why?", "LONG_TEXT"),
    ("If your team was a bunch of pirates, what would be your pirate flag and what would you keep in your treasure chest?", "LONG_TEXT"),
    ("If your team captain was a wizard, what would be their signature spell and how would they use it?", "LONG_TEXT"),
    ("What is the most played song or radio station in your team's shop?", "LONG_TEXT"),
    ("What is your team's go to shop snack?", "LONG_TEXT"),
    ("What is your team's favorite movie about or involving lawn mowers?", "LONG_TEXT"),
]


def seed_questions(apps, schema_editor):
    Question = apps.get_model('compforms', 'Question')
    CompForm = apps.get_model('compforms', 'CompForm')
    FormQuestion = apps.get_model('compforms', 'FormQuestion')

    questions = []
    for text, qtype in QUESTIONS:
        q = Question.objects.create(question_text=text, question_type=qtype)
        questions.append(q)

    form = CompForm.objects.create(
        name="Pre-Competition Form",
        description="Fun and informational questionnaire for teams before competition.",
    )

    for i, q in enumerate(questions, start=1):
        FormQuestion.objects.create(form=form, question=q, order=i, required=True)


def unseed_questions(apps, schema_editor):
    CompForm = apps.get_model('compforms', 'CompForm')
    Question = apps.get_model('compforms', 'Question')
    CompForm.objects.filter(name="Pre-Competition Form").delete()
    Question.objects.filter(question_text__in=[text for text, _ in QUESTIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('compforms', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_questions, unseed_questions),
    ]
